"""Pure accounting rules of the paper engine (engine-test fixture bars, not market data)."""
import pytest

from app.paper import PaperPortfolio

K = "base:0xtok"
E = 1_700_000_100            # a bar END (price known time)


def pf(**kw):
    p = PaperPortfolio(**kw)
    p.update_market_price(K, 100.0, E)
    return p


def b(ts, o, h, l, c):
    return {"ts": ts, "end_ts": ts + 60, "open": o, "high": h, "low": l, "close": c}


def test_entry_costs_exact():
    p = pf()
    r = p.enter(K, target_return_pct=5, stop_loss_pct=2)
    assert r["status"] == "entered"
    fill = 100 * 1.003
    assert r["entry"] == pytest.approx(fill)
    assert r["qty"] == pytest.approx(500 / fill)
    assert p.cash_usd == pytest.approx(10000 - 500 - 500 * 0.003 - 2)
    assert p.positions[K]["entry_ts"] == E


def test_entry_does_not_touch_price_book():
    p = pf()
    p.enter(K)
    assert p.last_prices[K] == 100.0            # market close, not the fill price


def test_pre_entry_bar_is_ignored():
    p = pf()
    p.enter(K, target_return_pct=1, stop_loss_pct=1)
    out = p.evaluate_bar(K, b(E - 60, 100, 200, 1, 100))      # opened before the price was known
    assert out["status"] == "ignored_pre_entry_bar" and K in p.positions


def test_stop_checked_before_target_in_same_bar():
    p = pf()
    p.enter(K, target_return_pct=5, stop_loss_pct=2)
    out = p.evaluate_bar(K, b(E, 100, 120, 90, 100))
    assert out["reason"] == "stop"


def test_gap_down_fills_at_open_not_stop_level():
    p = pf()
    p.enter(K, stop_loss_pct=2)
    out = p.evaluate_bar(K, b(E, 90, 91, 89, 90))
    assert out["market_level"] == 90 and out["exit"] == pytest.approx(90 * 0.997)


def test_gap_up_target_fills_at_open():
    p = pf()
    p.enter(K, target_return_pct=5)
    out = p.evaluate_bar(K, b(E, 110, 111, 109, 110))
    assert out["reason"] == "target" and out["market_level"] == 110


def test_exit_costs_and_pnl_reconcile():
    p = pf()
    p.enter(K, target_return_pct=5)
    cost0 = p.positions[K]["cost"]
    out = p.evaluate_bar(K, b(E, 100, 106, 100, 105))
    entry = 100 * 1.003
    level = max(entry * 1.05, 100)
    qty = 500 / entry
    proceeds = qty * level * 0.997
    exp_pnl = proceeds - proceeds * 0.003 - 2 - cost0
    assert out["pnl_usd"] == pytest.approx(exp_pnl)
    assert p.cash_usd == pytest.approx(10000 + exp_pnl)
    assert p.realized_pnl_usd == pytest.approx(exp_pnl)
    assert out["exit_ts"] == E + 60


def test_cooldown_only_after_stop_and_blocks_reentry():
    p = pf()
    p.enter(K, stop_loss_pct=2)
    p.evaluate_bar(K, b(E, 100, 100, 90, 95))
    assert K in p.cooldown_until
    p.update_market_price(K, 95, E + 120)
    assert p.enter(K)["status"] == "cooldown"
    p.update_market_price(K, 95, p.cooldown_until[K])
    assert p.enter(K)["status"] == "entered"


def test_no_cooldown_after_target_or_manual():
    p = pf()
    p.enter(K)
    p.exit(K, 100, "manual")
    assert K not in p.cooldown_until


def test_total_exposure_cap_across_tokens():
    p = PaperPortfolio()
    keys = [f"base:t{i}" for i in range(4)]
    for k in keys:
        p.update_market_price(k, 10.0, E)
    st = [p.enter(k)["status"] for k in keys]
    assert st[:3] == ["entered"] * 3 and st[3] == "risk_limit_or_no_cash"
    assert p.exposure_usd() / p.equity_usd() <= 0.15 + 1e-9


def test_allocation_above_cap_rejected():
    with pytest.raises(ValueError):
        pf().enter(K, allocation_pct=0.2)


def test_already_in_position():
    p = pf()
    p.enter(K)
    assert p.enter(K)["status"] == "already_in_position"


def test_no_price_no_entry():
    assert PaperPortfolio().enter("base:none")["status"] == "no_market_price"


def test_cash_never_negative_with_tiny_balance():
    p = PaperPortfolio(initial_cash_usd=3.0)
    p.update_market_price(K, 1.0, E)
    r = p.enter(K)
    assert r["status"] == "risk_limit_or_no_cash" and p.cash_usd == 3.0


def test_inconsistent_ohlc_rejected():
    p = pf()
    p.enter(K, stop_loss_pct=2)
    with pytest.raises(ValueError):
        p.evaluate_bar(K, b(E, 100, 99, 98, 100))
