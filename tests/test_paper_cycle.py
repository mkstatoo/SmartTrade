"""End-to-end Paper cycle through the HTTP API: bar ingestion -> signal -> entry -> stop/target -> costs -> PnL log.
Runs against BOTH the memory store and real PostgreSQL (skipped without TEST_DATABASE_URL).
Bars are engine-test fixtures (deterministic prices to check accounting), not market data."""
import pytest
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.main import create_app
from app.store import MemoryStore, PostgresStore

from conftest import H, KEY, MIN, T0, bar, signal

TOK = "0xtoken1"
KEY1 = f"base:{TOK}"
FILL = 100 * 1.003            # entry fill at market 100, 30 bps slippage


def paper(c):
    return c.get("/paper").json()


def enter_at_100(c, t=T0, stop=2.0, target=5.0, token=TOK):
    bar(c, token, t, 100, 100.5, 99.5, 100)
    r = signal(c, token, t + MIN, stop_loss_pct=stop, target_return_pct=target)
    assert r["action"] == "ENTER", r
    return r


def expected_pnl(level, qty, cost):
    proceeds = qty * level * 0.997
    return proceeds - proceeds * 0.003 - 2 - cost


def test_scenario_target_with_gap_up(client):
    r = enter_at_100(client)
    assert r["entry"] == pytest.approx(FILL) and r["entry_ts"] == T0 + MIN
    bar(client, TOK, T0 + MIN, 100, 101, 99.9, 100.5)                 # holding
    assert paper(client)["portfolio"]["open_positions"] == 1
    out = bar(client, TOK, T0 + 2 * MIN, 108, 109, 107, 108)          # gaps over the 105.3 target -> fills at open
    ev = out["bar_evaluation"]
    assert ev["reason"] == "target" and ev["market_level"] == 108
    assert ev["pnl_usd"] == pytest.approx(expected_pnl(108, r["qty"], r["cost"]))
    p = paper(client)
    assert p["portfolio"]["open_positions"] == 0
    assert p["portfolio"]["cash_usd"] == pytest.approx(10000 + ev["pnl_usd"], abs=0.01)
    assert p["closed_trades"][0]["pnl_usd"] == pytest.approx(ev["pnl_usd"])
    assert {f["side"] for f in p["fills"]} == {"BUY", "SELL"}


def test_scenario_stop_then_cooldown_then_reentry(client):
    enter_at_100(client)
    out = bar(client, TOK, T0 + MIN, 100, 100, 95, 96)               # stop level 98.294 touched intra-bar
    assert out["bar_evaluation"]["reason"] == "stop"
    assert out["bar_evaluation"]["market_level"] == pytest.approx(FILL * 0.98)
    stop_end = T0 + 2 * MIN
    r = signal(client, TOK, stop_end)
    assert r["action"] == "WAIT" and r["status"] == "cooldown"
    t = stop_end
    while t < stop_end + 3600:                                        # advance data clock through the cooldown
        bar(client, TOK, t, 96, 96.2, 95.9, 96)
        t += MIN
    r = signal(client, TOK, t, stop_loss_pct=2, target_return_pct=5)
    assert r["action"] == "ENTER"
    assert len(paper(client)["closed_trades"]) == 1


def test_scenario_stop_and_target_same_bar_is_stop(client):
    enter_at_100(client)
    out = bar(client, TOK, T0 + MIN, 100, 120, 90, 100)
    assert out["bar_evaluation"]["reason"] == "stop"


def test_scenario_gap_down_fills_at_open(client):
    r = enter_at_100(client)
    out = bar(client, TOK, T0 + MIN, 90, 91, 89, 90)
    ev = out["bar_evaluation"]
    assert ev["market_level"] == 90
    assert ev["pnl_usd"] == pytest.approx(expected_pnl(90, r["qty"], r["cost"]))


def test_lookahead_bar_before_entry_cannot_trigger_exit(client):
    bar(client, TOK, T0, 100, 100, 80, 100)                           # violent bar, already formed at signal time
    r = signal(client, TOK, T0 + MIN, stop_loss_pct=2, target_return_pct=5)
    assert r["action"] == "ENTER"
    assert paper(client)["portfolio"]["open_positions"] == 1
    assert bar(client, TOK, T0, 100, 100, 80, 100, expect=200)["status"] == "duplicate"
    assert paper(client)["portfolio"]["open_positions"] == 1


def test_stale_price_waits(client):
    bar(client, TOK, T0, 100, 100, 100, 100)
    for i in range(1, 12):                                            # another token advances the data clock 11 min
        bar(client, "0xother", T0 + i * MIN, 5, 5, 5, 5)
    r = signal(client, TOK, T0 + 12 * MIN)
    assert r["action"] == "WAIT" and "no_fresh_trusted_market_price" in r["reasons"]
    assert paper(client)["portfolio"]["open_positions"] == 0


def test_signal_for_token_without_any_bar_waits(client):
    bar(client, "0xother", T0, 5, 5, 5, 5)
    r = signal(client, TOK, T0 + MIN)
    assert r["action"] == "WAIT" and "no_fresh_trusted_market_price" in r["reasons"]


def test_duplicate_out_of_order_conflicting_and_misaligned_bars(client):
    bar(client, TOK, T0, 100, 101, 99, 100)
    assert bar(client, TOK, T0, 100, 101, 99, 100)["status"] == "duplicate"
    bar(client, TOK, T0, 100, 102, 99, 100, expect=409)               # conflicting duplicate
    bar(client, TOK, T0 + MIN, 100, 101, 99, 100)
    bar(client, TOK, T0, 100, 101, 99, 100, expect=409)               # out of order (older than last)
    bar(client, TOK, T0 + 2 * MIN + 7, 100, 101, 99, 100, expect=422)  # not aligned
    r = client.post("/paper/replay/bar", headers=H, json={"chain": "base", "token": TOK, "ts": T0 + 2 * MIN,
                    "timeframe": "5m", "open": 1, "high": 1, "low": 1, "close": 1, "volume_usd": 0})
    assert r.status_code == 422


def test_auth(client, monkeypatch):
    body = {"chain": "base", "token": TOK, "ts": T0, "open": 1, "high": 1, "low": 1, "close": 1, "volume_usd": 0}
    assert client.post("/paper/replay/bar", json=body, headers={"X-Research-Key": ""}).status_code == 401
    assert client.post("/paper/replay/bar", json=body, headers={"X-Research-Key": "wrong"}).status_code == 401
    monkeypatch.setenv("PAPER_API_KEY", "")
    assert client.post("/paper/replay/bar", json=body, headers=H).status_code == 503
    assert KEY not in client.get("/config").text


def test_manual_exit_exact_and_validation(client):
    r = enter_at_100(client)
    bar(client, TOK, T0 + MIN, 100, 101, 99.9, 101)
    assert client.post(f"/paper/exit/base/{TOK}?reason=stop", headers=H).status_code == 422
    assert client.post("/paper/exit/base/nothere", headers=H).status_code == 404
    ev = client.post(f"/paper/exit/base/{TOK}?reason=manual", headers=H).json()
    assert ev["pnl_usd"] == pytest.approx(expected_pnl(101, r["qty"], r["cost"]))


def test_exposure_cap_across_tokens_and_reconciliation(client):
    toks = ["0xa1", "0xa2", "0xa3", "0xa4"]
    for t in toks:
        bar(client, t, T0, 10, 10, 10, 10)
    res = [signal(client, t, T0 + MIN, stop_loss_pct=50, target_return_pct=50) for t in toks]
    assert [r["action"] for r in res] == ["ENTER"] * 3 + ["WAIT"]
    snap = paper(client)["portfolio"]
    assert snap["exposure_usd"] / snap["equity_usd"] <= 0.15 + 1e-6
    # close everything manually, then the ledger must reconcile
    for t in toks[:3]:
        client.post(f"/paper/exit/base/{t}", headers=H)
    p = paper(client)
    assert p["portfolio"]["open_positions"] == 0
    total = sum(x["pnl_usd"] for x in p["closed_trades"])
    assert total == pytest.approx(p["portfolio"]["realized_pnl_usd"], abs=0.01)
    assert p["portfolio"]["cash_usd"] == pytest.approx(10000 + total, abs=0.01)
    assert len(p["fills"]) == 6


def test_state_survives_restart(store):
    with TestClient(create_app(store, ReplayClock()), headers=H) as c1:
        r = enter_at_100(c1)
        before = paper(c1)
    store2 = store if isinstance(store, MemoryStore) else PostgresStore(store.dsn)
    with TestClient(create_app(store2, ReplayClock()), headers=H) as c2:
        after = paper(c2)
        assert after["positions"].keys() == before["positions"].keys()
        assert after["price_book"] == before["price_book"]
        assert after["portfolio"]["cash_usd"] == before["portfolio"]["cash_usd"]
        out = bar(c2, TOK, T0 + MIN, 100, 100, 95, 96)                # stop still armed after restart
        assert out["bar_evaluation"]["reason"] == "stop"
        assert out["bar_evaluation"]["qty"] == pytest.approx(r["qty"], rel=1e-12)
        bar(c2, TOK, T0 + MIN, 100, 100, 95, 96)                      # duplicate detected across restart too


def test_health_and_wait_is_recorded(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/status").json()["clock"] == "replay"
    bar(client, "0xother", T0, 5, 5, 5, 5)
    r = signal(client, TOK, T0 + MIN)                                 # no price -> WAIT, still audited
    assert r["action"] == "WAIT" and isinstance(r["signal_id"], int)


def test_signal_before_any_data_is_rejected_by_replay_clock(client):
    assert signal(client, TOK, T0 + MIN, expect=422)["detail"].startswith("signal_ts")
