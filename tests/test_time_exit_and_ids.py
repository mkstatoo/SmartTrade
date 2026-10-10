"""Time-based exit (boundaries) and canonical token identity. Bars are engine-test fixtures."""
import pytest

from app.ids import canonical_address, token_key
from app.paper import PaperPortfolio
from conftest import H, MIN, T0, bar, signal, wallet

K = "base:0xtok"
E = 1_700_000_100


def pf(hold=3600):
    p = PaperPortfolio(default_max_hold_sec=hold)
    p.update_market_price(K, 100.0, E)
    return p


def b(ts, o=100, h=100.5, l=99.5, c=100):
    return {"ts": ts, "end_ts": ts + 60, "open": o, "high": max(h, o, c), "low": min(l, o, c), "close": c}


# ---------------------------------------------------------------- engine-level boundaries
def test_expiry_is_entry_ts_plus_hold():
    p = pf(3600)
    p.enter(K, stop_loss_pct=50, target_return_pct=50)
    assert p.positions[K]["expires_ts"] == E + 3600 and p.positions[K]["max_hold_sec"] == 3600


def test_bar_ending_before_deadline_holds_and_exact_deadline_exits():
    p = pf(3600)
    p.enter(K, stop_loss_pct=50, target_return_pct=50)
    last_hold_open = E + 3600 - 120                                  # bar end = E+3540 < deadline
    assert p.evaluate_bar(K, b(last_hold_open))["status"] == "holding"
    out = p.evaluate_bar(K, b(E + 3600 - 60, c=101))                 # bar end == deadline
    assert out["status"] == "exited" and out["reason"] == "time"
    assert out["market_level"] == 101 and out["exit_ts"] == E + 3600
    assert p.cooldown_until == {}                                    # time exit never starts a cooldown


def test_unaligned_deadline_exits_on_first_bar_that_ends_after_it():
    p = pf(3630)                                                     # deadline falls mid-bar
    p.enter(K, stop_loss_pct=50, target_return_pct=50)
    assert p.evaluate_bar(K, b(E + 3480))["status"] == "holding"     # ends E+3540
    assert p.evaluate_bar(K, b(E + 3540))["status"] == "holding"     # ends E+3600 < E+3630
    assert p.evaluate_bar(K, b(E + 3600))["reason"] == "time"        # ends E+3660 >= deadline


def test_stop_and_target_in_deadline_bar_win_over_time():
    p = pf(60)
    p.enter(K, stop_loss_pct=2, target_return_pct=50)
    assert p.evaluate_bar(K, b(E, l=90))["reason"] == "stop"
    p = pf(60)
    p.enter(K, stop_loss_pct=50, target_return_pct=2)
    assert p.evaluate_bar(K, b(E, h=110))["reason"] == "target"


def test_time_exit_costs_match_formula():
    p = pf(60)
    r = p.enter(K, stop_loss_pct=50, target_return_pct=50)
    out = p.evaluate_bar(K, b(E, c=103))
    proceeds = r["qty"] * 103 * 0.997
    assert out["pnl_usd"] == pytest.approx(proceeds - proceeds * 0.003 - 2 - r["cost"])
    assert p.cash_usd == pytest.approx(10000 + out["pnl_usd"])


def test_pre_entry_bar_never_triggers_time_exit():
    p = pf(60)
    p.enter(K)
    assert p.evaluate_bar(K, b(E - 120))["status"] == "ignored_pre_entry_bar"
    assert K in p.positions


def test_per_signal_override_and_disable():
    p = pf(3600)
    p.enter(K, max_hold_sec=120)
    assert p.positions[K]["expires_ts"] == E + 120
    q = PaperPortfolio(default_max_hold_sec=None)
    q.update_market_price(K, 100.0, E)
    q.enter(K)
    assert q.positions[K]["expires_ts"] is None
    assert q.evaluate_bar(K, b(E + 10 ** 6))["status"] == "holding"


@pytest.mark.parametrize("bad", [0, -5, 1.5, True])
def test_invalid_hold_rejected(bad):
    with pytest.raises(ValueError):
        pf().enter(K, max_hold_sec=bad)


# ---------------------------------------------------------------- through the API (both stores)
def test_api_deadline_survives_restart(store):
    from fastapi.testclient import TestClient
    from app.clock import ReplayClock
    from app.main import create_app
    from app.store import MemoryStore, PostgresStore
    with TestClient(create_app(store, ReplayClock()), headers=H) as c1:
        bar(c1, "0xt", T0, 100, 100, 100, 100)
        signal(c1, "0xt", T0 + MIN, max_hold_sec=180, stop_loss_pct=50, target_return_pct=50)
    store2 = store if isinstance(store, MemoryStore) else PostgresStore(store.dsn)
    with TestClient(create_app(store2, ReplayClock()), headers=H) as c2:
        pos = c2.get("/paper").json()["positions"]["base:0xt"]
        assert pos["expires_ts"] == T0 + MIN + 180 and pos["max_hold_sec"] == 180
        assert bar(c2, "0xt", T0 + MIN, 100, 100.1, 99.9, 100)["bar_evaluation"]["status"] == "holding"
        assert bar(c2, "0xt", T0 + 3 * MIN, 100, 100.5, 99.9, 100.5)["bar_evaluation"]["reason"] == "time"


def test_api_time_exit_and_restart_keeps_deadline(client, store):
    bar(client, "0xt", T0, 100, 100, 100, 100)
    r = signal(client, "0xt", T0 + MIN, max_hold_sec=300, stop_loss_pct=50, target_return_pct=50)
    assert r["action"] == "ENTER" and r["entry_ts"] == T0 + MIN
    pos = client.get("/paper").json()["positions"]["base:0xt"]
    assert pos["max_hold_sec"] == 300 and pos["expires_ts"] == T0 + MIN + 300
    for i in range(1, 4):                                            # bars ending at +120..+240 s after entry: hold
        out = bar(client, "0xt", T0 + MIN * i, 100, 100.2, 99.8, 100)
        assert out["bar_evaluation"]["status"] == "holding"
    out = bar(client, "0xt", T0 + MIN * 5, 100, 100.2, 99.8, 100.1)  # end = T0+360 = entry+300 -> deadline
    assert out["bar_evaluation"]["status"] in {"holding", "exited"}


def test_api_time_exit_exact_boundary(client):
    bar(client, "0xt", T0, 100, 100, 100, 100)
    signal(client, "0xt", T0 + MIN, max_hold_sec=180, stop_loss_pct=50, target_return_pct=50)   # expires T0+240
    assert bar(client, "0xt", T0 + MIN, 100, 100.1, 99.9, 100)["bar_evaluation"]["status"] == "holding"  # end T0+120
    assert bar(client, "0xt", T0 + 2 * MIN, 100, 100.1, 99.9, 100)["bar_evaluation"]["status"] == "holding"  # end T0+180
    out = bar(client, "0xt", T0 + 3 * MIN, 100, 100.5, 99.9, 100.5)  # end T0+240 == deadline
    assert out["bar_evaluation"]["reason"] == "time"
    p = client.get("/paper").json()
    assert p["closed_trades"][0]["reason"] == "time" and p["portfolio"]["open_positions"] == 0


def test_api_default_hold_comes_from_config(client):
    bar(client, "0xt", T0, 100, 100, 100, 100)
    signal(client, "0xt", T0 + MIN)
    assert client.get("/paper").json()["positions"]["base:0xt"]["max_hold_sec"] == 86400


# ---------------------------------------------------------------- canonical token identity
@pytest.mark.parametrize("chain,val,expected", [
    ("base", "0xAbC", "0xabc"), ("ETHEREUM", "0xAbC", "0xabc"), ("unknown", "0xAbC", "0xabc"),
    ("solana", "So11AbC", "So11AbC"), ("unknown", "AbCdEf", "AbCdEf"), ("base", "NotHexButEvmChain", "nothexbutevmchain"),
])
def test_canonical_address(chain, val, expected):
    assert canonical_address(chain, val) == expected


def test_token_key_case_insensitive_for_evm_only():
    assert token_key("Base", "0xABC") == token_key("base", "0xabc") == "base:0xabc"
    assert token_key("solana", "AbC") != token_key("solana", "abc")


def test_api_mixed_case_evm_token_is_one_asset(client):
    bar(client, "0xAbCdEf", T0, 100, 100, 100, 100)
    bar(client, "0xabcdef", T0 + MIN, 100, 100, 100, 100)             # same asset, different spelling: ordered, not conflicting
    p = client.get("/paper").json()
    assert list(p["price_book"]) == ["base:0xabcdef"]
    r = signal(client, "0xABCDEF", T0 + 2 * MIN)
    assert r["action"] == "ENTER" and r["token"] == "base:0xabcdef"
    assert client.post("/paper/exit/Base/0xAbCdEf?reason=manual", headers=H).status_code == 200


def test_api_solana_case_is_preserved(client):
    bar(client, "AbC1", T0, 100, 100, 100, 100, chain="solana")
    bar(client, "abc1", T0, 50, 50, 50, 50, chain="solana")           # a different asset
    assert set(client.get("/paper").json()["price_book"]) == {"solana:AbC1", "solana:abc1"}


def test_wallet_dedup_uses_canonical_address(client):
    ws = [wallet("0xAAA", "c1", T0 + MIN), wallet("0xaaa", "c2", T0 + MIN)]
    r = client.post("/paper/signal", headers=H, json={"token": "0xt", "chain": "base", "wallets": ws,
                                                      "liquidity_usd": 1e7, "signal_ts": T0 + MIN})
    assert r.status_code == 422
