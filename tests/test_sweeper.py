"""Independent expiry: positions leave at their deadline even if their token never receives another bar."""
import time

import pytest
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.main import create_app, sweep_once
from app.paper import PaperPortfolio
from app.store import MemoryStore, PostgresStore
from conftest import H, MIN, T0, bar, signal

K = "base:0xtok"
E = 1_700_000_100


class FakeLive:
    name = "live"

    def __init__(self, now):
        self.t = now

    def now(self, portfolio=None):
        return int(self.t)


def pf(hold=600):
    p = PaperPortfolio(default_max_hold_sec=hold)
    p.update_market_price(K, 100.0, E)
    p.enter(K, stop_loss_pct=50, target_return_pct=50)
    return p


# ------------------------------------------------------------------ engine
def test_sweep_before_deadline_does_nothing_and_at_deadline_closes():
    p = pf(600)
    assert p.sweep_expired(E + 599) == [] and K in p.positions
    out = p.sweep_expired(E + 600)
    assert len(out) == 1 and out[0]["reason"] == "time" and K not in p.positions
    assert out[0]["price_basis"] == "stale_last_close" and out[0]["price_age_sec"] == 600
    assert out[0]["exit_ts"] == E + 600 and out[0]["market_level"] == 100.0


def test_sweep_costs_exact_and_no_cooldown_and_idempotent():
    p = pf(60)
    qty, cost = p.positions[K]["qty"], p.positions[K]["cost"]
    out = p.sweep_expired(E + 10_000)[0]
    proceeds = qty * 100 * 0.997
    assert out["pnl_usd"] == pytest.approx(proceeds - proceeds * 0.003 - 2 - cost)
    assert p.cooldown_until == {} and p.sweep_expired(E + 20_000) == []


def test_sweep_ignores_positions_without_deadline_and_only_expired_ones():
    p = PaperPortfolio(default_max_hold_sec=None)
    p.update_market_price(K, 100.0, E)
    p.enter(K)
    p.update_market_price("base:0xb", 10.0, E)
    p.enter("base:0xb", max_hold_sec=60)
    assert p.sweep_expired(E + 10 ** 9)[0]["token"] == "base:0xb" and K in p.positions


def test_normal_bar_exit_keeps_bar_basis():
    p = pf(60)
    out = p.evaluate_bar(K, {"ts": E, "end_ts": E + 60, "open": 100, "high": 100.2, "low": 99.9, "close": 100})
    assert out["reason"] == "time" and out["price_basis"] == "bar" and out["price_age_sec"] is None


# ------------------------------------------------------------------ API + background loop (memory and PostgreSQL)
def live_app(store, now, interval=0):
    clock = FakeLive(now)
    return TestClient(create_app(store, clock, sweep_interval=interval), headers=H), clock


def seed_position(c, hold=300):
    """ENTER through the API while the (fake) wall clock is at the signal time."""
    bar(c, "0xt", T0, 100, 100, 100, 100)
    return signal(c, "0xt", T0 + MIN, max_hold_sec=hold, stop_loss_pct=50, target_return_pct=50)


def test_endpoint_sweeps_only_when_due_and_records_basis(store):
    c, clk = live_app(store, T0 + MIN)
    with c:
        seed_position(c, 300)                                    # expires T0+360
        clk.t = T0 + 359
        assert c.post("/paper/sweep").json()["swept"] == 0
        clk.t = T0 + 900
        r = c.post("/paper/sweep").json()
        assert r["swept"] == 1 and r["closed"][0]["price_age_sec"] == 900 - MIN
        assert c.post("/paper/sweep").json()["swept"] == 0       # idempotent
        t = c.get("/paper").json()["closed_trades"][0]
        assert t["reason"] == "time" and t["price_basis"] == "stale_last_close" and t["exit_ts"] == T0 + 900
        assert c.get("/paper").json()["portfolio"]["open_positions"] == 0


def test_sweeper_survives_restart(store):
    c, clk = live_app(store, T0 + MIN)
    with c:
        seed_position(c, 300)
    store2 = store if isinstance(store, MemoryStore) else PostgresStore(store.dsn)
    c2, clk2 = live_app(store2, T0 + 5000)
    with c2:
        assert c2.post("/paper/sweep").json()["swept"] == 1


def test_background_loop_closes_expired_position_without_any_new_bar(store):
    c, clk = live_app(store, T0 + MIN, interval=0.05)
    with c:
        seed_position(c, 300)
        assert c.get("/paper").json()["portfolio"]["open_positions"] == 1
        clk.t = T0 + 1000
        for _ in range(100):
            if c.get("/paper").json()["portfolio"]["open_positions"] == 0:
                break
            time.sleep(0.05)
        assert c.get("/paper").json()["portfolio"]["open_positions"] == 0
        assert c.get("/paper").json()["closed_trades"][0]["price_basis"] == "stale_last_close"


def test_loop_is_not_started_in_replay_mode_or_when_disabled():
    for clock, interval in ((ReplayClock(), 0.05), (FakeLive(T0), 0)):
        with TestClient(create_app(MemoryStore(), clock, sweep_interval=interval), headers=H) as c:
            bar(c, "0xt", T0, 100, 100, 100, 100)
            signal(c, "0xt", T0 + MIN, max_hold_sec=60) if clock.name == "replay" else None
            time.sleep(0.3)
            if clock.name == "replay":
                assert c.get("/paper").json()["portfolio"]["open_positions"] == 1


def test_loop_keeps_running_after_a_storage_failure(monkeypatch):
    import app.main as m
    real, calls = m.sweep_once, {"n": 0}

    def flaky(app):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("db hiccup")                       # first ticks fail ...
        return real(app)                                          # ... then storage is back
    monkeypatch.setattr(m, "sweep_once", flaky)
    c, clk = live_app(MemoryStore(), T0 + MIN, interval=0.05)
    with c:
        seed_position(c, 300)
        clk.t = T0 + 1000
        for _ in range(120):
            if c.get("/paper").json()["portfolio"]["open_positions"] == 0:
                break
            time.sleep(0.05)
        assert c.get("/paper").json()["portfolio"]["open_positions"] == 0 and calls["n"] > 3


def test_sweep_once_is_cheap_when_nothing_is_due():
    class Spy(MemoryStore):
        txns = 0

        def txn(self):
            Spy.txns += 1
            return super().txn()
    store = Spy()
    c, clk = live_app(store, T0 + MIN)
    with c:
        seed_position(c, 3600)
        before = Spy.txns
        for _ in range(5):
            assert sweep_once(c.app) == []
        assert Spy.txns == before                                  # no write transaction was opened
