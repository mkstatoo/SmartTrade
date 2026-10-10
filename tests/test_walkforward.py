"""Walk-forward without look-ahead. The price/event data below are seeded FIXTURES for exercising the harness
(random walks / steady trends); they are not market data and say nothing about any strategy's edge."""
import copy
import random

import pytest
from fastapi.testclient import TestClient

import app.walkforward as wf
from app.backtest import run_backtest
from app.clock import ReplayClock
from app.main import create_app
from app.models import BacktestRequest
from app.store import MemoryStore
from app.walkforward import split_phases, walk_forward
from conftest import H

T0 = 1_700_000_040
DAY = 86400


def bars(token, n, f):
    out, prev = [], f(0)
    for i in range(n):
        o, c = prev, f(i + 1)
        out.append({"chain": "base", "token": token, "ts": T0 + 60 * i, "timeframe": "1m", "open": o,
                    "high": max(o, c) * 1.0002, "low": min(o, c) * 0.9998, "close": c, "volume_usd": 1e7})
        prev = c
    return out


def walk(seed, n, drift=0.0, vol=0.0015):
    rng = random.Random(seed)
    px = [100.0]
    for _ in range(n + 1):
        px.append(px[-1] * (1 + drift + rng.gauss(0, vol)))
    return lambda i: px[i]


def make(seed=1, days=4, trend=None, n_events=240):
    n = days * 1440
    rng = random.Random(seed)
    prices = []
    for t in ("0xa", "0xb"):
        f = (lambda i: 100.0 * (1.0004 ** i)) if trend else walk(seed + len(t) + ord(t[-1]), n, drift=0.00002)
        prices += bars(t, n, f)
    horizon = 3 * 3600
    events = []
    for i in range(n_events):
        ts = T0 + rng.randint(600, n * 60 - horizon - 3600)
        events.append({"wallet": f"0xw{i}", "token": "0xa" if i % 2 else "0xb", "chain": "base", "ts": ts,
                       "side": "BUY", "usd_value": 1000.0, "price": 100.0, "tx_hash": f"0x{i:064x}", "log_index": 0})
    return BacktestRequest.model_validate({"events": events, "prices": prices, "horizon_hours": 3,
                                           "max_entry_delay_hours": 1, "notional_usd": 1000, "slippage_bps": 30})


def clone(req, **upd):
    return req.model_copy(update=upd)


def mutate_after(req, boundary, strictly_after=True):
    """Return a copy whose bars after `boundary` are scaled x3 and whose later events are rewritten."""
    prices = [p.model_copy(update={"open": p.open * 3, "high": p.high * 3, "low": p.low * 3, "close": p.close * 3})
              if p.ts > boundary else p for p in req.prices]
    events = [e.model_copy(update={"usd_value": e.usd_value * 7, "price": e.price * 2}) if e.ts >= boundary else e
              for e in req.events]
    return clone(req, prices=prices, events=events)


@pytest.fixture(scope="module")
def data():
    return make()


@pytest.fixture(scope="module")
def report(data):
    return walk_forward(data, min_trades=5)


# ------------------------------------------------------------------ structure
def test_phases_are_ordered_and_purged(data, report):
    ph = report["phases"]
    assert ph["train"]["end"] == ph["validation"]["start"] < ph["validation"]["end"] == ph["test"]["start"]
    assert ph["test"]["end"] is None and ph["reach_sec"] == 60 + 12 + 1 * 3600 + 3 * 3600
    assert report["purged_events"]["train"] > 0 and report["purged_events"]["validation"] > 0
    assert report["purged_events"]["test"] == 0                              # last phase has no later phase to leak into


def test_every_phase_passes_its_own_leakage_checks(report):
    assert [c["phase"] for c in report["leakage_checks"]][:2] == ["train", "validation"]
    for c in report["leakage_checks"]:
        assert c["events_start_inside"] and c["lifecycle_ends_inside"], c
    assert report["leakage_checks"][0]["grid_cells_checked"] == 9


def test_selection_uses_train_only(data, report):
    tr = [g for g in report["grid"] if g["train"]["effective_n"] >= 5]
    best = max(tr, key=lambda g: (g["train"]["avg_net_return_pct"], -(g["stop_loss_pct"] or 0), g["target_return_pct"]))
    assert report["selected"] == {"target_return_pct": best["target_return_pct"], "stop_loss_pct": best["stop_loss_pct"]}


def test_split_rejects_bad_input(data):
    with pytest.raises(ValueError):
        split_phases(data, 0.8, 0.3)
    with pytest.raises(ValueError):
        split_phases(clone(data, events=data.events[:2]), 0.5, 0.2)


# ------------------------------------------------------------------ the core: the future cannot influence the past
def test_changing_everything_after_the_train_end_does_not_change_train_results(data, report):
    b1 = report["phases"]["train"]["end"]
    other = walk_forward(mutate_after(data, b1), min_trades=5)
    assert other["grid"] == report["grid"]


def test_changing_everything_after_validation_end_does_not_change_selection_or_validation(data, report):
    b2 = report["phases"]["validation"]["end"]
    other = walk_forward(mutate_after(data, b2), min_trades=5)
    assert other["grid"] == report["grid"] and other["selected"] == report["selected"]
    assert other["validation"] == report["validation"] and other["gate_passed"] == report["gate_passed"]
    if report["gate_passed"]:
        assert other["oos"] != report["oos"]                                  # the mutation did reach the OOS phase


def test_selection_cannot_peek_at_test_phase(data, report):
    b2 = report["phases"]["validation"]["end"]
    wild = mutate_after(data, b2)
    assert walk_forward(wild, min_trades=5)["selected"] == report["selected"]


def test_event_and_price_order_do_not_matter(data, report):
    shuffled = clone(data, events=random.Random(3).sample(data.events, len(data.events)),
                     prices=random.Random(4).sample(data.prices, len(data.prices)))
    again = walk_forward(shuffled, min_trades=5)
    assert again["grid"] == report["grid"] and again["selected"] == report["selected"] and again["oos"] == report["oos"]


def test_purge_drops_events_whose_life_crosses_the_boundary(data, report):
    b1, reach = report["phases"]["train"]["end"], report["phases"]["reach_sec"]
    def ev(ts, i):
        return data.events[0].model_copy(update={"ts": ts, "wallet": f"0xprobe{i}", "tx_hash": f"0x{i + 9000:064x}"})
    inside, edge, crossing = ev(b1 - reach - 1, 1), ev(b1 - reach, 2), ev(b1 - reach + 1, 3)
    probe = clone(data, events=list(data.events) + [inside, edge, crossing])
    ph = report["phases"]                                                    # fixed boundary (adding events would move quantiles)
    req, purged = wf._phase_req(probe, ph["train"]["start"], ph["train"]["end"], ph["reach_sec"])
    wallets = {e.wallet for e in req.events}
    assert "0xprobe1" in wallets and "0xprobe2" in wallets and "0xprobe3" not in wallets


def test_trades_never_use_bars_after_the_phase_end(data):
    ph = split_phases(data, 0.5, 0.2)
    req, _ = wf._phase_req(data, ph["train"]["start"], ph["train"]["end"], ph["reach_sec"])
    assert max(p.ts for p in req.prices) <= ph["train"]["end"]
    res = run_backtest(req)
    assert res["effective_n"] > 0 and max(r["exit_ts"] for r in res["results"]) <= ph["train"]["end"]


# ------------------------------------------------------------------ gate and single OOS evaluation
def test_failed_validation_gate_means_oos_is_never_run(data, monkeypatch):
    base = walk_forward(data, min_trades=5)
    b1, b2 = base["phases"]["train"]["end"], base["phases"]["validation"]["end"]
    crash = [p.model_copy(update={"open": p.open * (1 - 0.00003 * (p.ts - b1) / 60), "high": p.high * (1 - 0.00003 * (p.ts - b1) / 60),
                                  "low": p.low * (1 - 0.00003 * (p.ts - b1) / 60), "close": p.close * (1 - 0.00003 * (p.ts - b1) / 60)})
             if b1 < p.ts <= b2 else p for p in data.prices]
    calls = []
    real = wf.run_backtest
    monkeypatch.setattr(wf, "run_backtest", lambda r: calls.append(len(r.events)) or real(r))
    rep = walk_forward(clone(data, prices=crash), min_trades=5)
    assert rep["gate_passed"] is False and rep["oos"] is None and rep["sensitivity"] is None
    assert len(calls) == 9 + 1                                               # grid + validation, nothing else
    assert any("NOT evaluated" in n for n in rep["notes"])


def test_oos_runs_once_with_selected_params_then_only_sensitivity(monkeypatch):
    up = make(trend=True)
    calls = []
    real = wf.run_backtest
    monkeypatch.setattr(wf, "run_backtest", lambda r: calls.append((r.target_return_pct, r.stop_loss_pct, r.detection_latency_sec,
                                                                    r.slippage_bps)) or real(r))
    rep = walk_forward(up, min_trades=5)
    assert rep["gate_passed"] and rep["oos"]["effective_n"] > 0
    sel = (rep["selected"]["target_return_pct"], rep["selected"]["stop_loss_pct"])
    after_grid = calls[9:]
    assert after_grid[0][:2] == sel and len(after_grid) == 1 + 1 + 16        # validation, OOS, 4x4 sensitivity
    assert all(c[:2] == sel for c in after_grid)                             # never re-selected from later phases


# ------------------------------------------------------------------ sensitivity
def test_sensitivity_grid_and_slippage_effect_on_a_steady_trend():
    up = make(trend=True)
    rep = walk_forward(up, min_trades=5)
    cells = rep["sensitivity"]["cells"]
    assert len(cells) == 16
    for lat in (0, 60, 300, 900):
        row = [c["avg_net_return_pct"] for c in cells if c["detection_latency_sec"] == lat and c["effective_n"] > 0]
        assert row == sorted(row, reverse=True), (lat, row)                  # more slippage never helps
    assert 0 <= rep["sensitivity"]["share_of_cells_profitable"] <= 1


def test_exact_cost_formula_for_a_flat_market():
    flat = BacktestRequest.model_validate({
        "events": [{"wallet": "0xw", "token": "0xa", "chain": "base", "ts": T0 + 600, "side": "BUY", "usd_value": 1, "price": 100}],
        "prices": bars("0xa", 600, lambda i: 100.0), "horizon_hours": 1, "slippage_bps": 50, "fee_bps": 10, "gas_usd": 1,
        "notional_usd": 1000})
    r = run_backtest(flat)["results"][0]
    s = 0.005
    gross = ((1 - s) / (1 + s) - 1) * 100
    assert r["gross_return_pct"] == pytest.approx(gross, abs=1e-3)
    assert r["net_return_pct"] == pytest.approx(gross - 2 * 0.10 - 2 * 1 / 1000 * 100, abs=1e-3)


# ------------------------------------------------------------------ API
def test_api_walkforward(data):
    body = {"base": data.model_dump(), "min_trades": 5}
    with TestClient(create_app(MemoryStore(), ReplayClock()), headers=H) as c:
        r = c.post("/backtest/walkforward", json=body)
        assert r.status_code == 200 and r.json()["selected"] is not None
        assert c.post("/backtest/walkforward", json={**body, "train_frac": 0.8, "val_frac": 0.3}).status_code == 422
        tiny = {**body, "base": {**body["base"], "events": body["base"]["events"][:2]}}
        assert c.post("/backtest/walkforward", json=tiny).status_code == 422
        assert c.post("/backtest/walkforward", json=body, headers={"X-Research-Key": ""}).status_code == 401
