import pytest
from pydantic import ValidationError

from app.backtest import run_backtest
from app.models import BacktestRequest, PriceBar, WalletEvent

T = 1000          # event time
H = 3600


def ev(token="QNT", ts=T, price=100.0, side="BUY", wallet="w"):
    return WalletEvent(wallet=wallet, token=token, ts=ts, side=side, usd_value=1000, price=price)


def bar(ts, o, h=None, l=None, c=None, vol=1e9, token="QNT"):
    h = h if h is not None else max(o, c if c is not None else o)
    l = l if l is not None else min(o, c if c is not None else o)
    c = c if c is not None else o
    return PriceBar(token=token, ts=ts, open=o, high=h, low=l, close=c, volume_usd=vol)


def req(events, prices, **kw):
    # zero-cost defaults so each test isolates ONE behaviour
    base = dict(slippage_bps=0, fee_bps=0, gas_usd=0, horizon_hours=1, target_return_pct=5,
                detection_latency_sec=60, block_latency_sec=12)
    base.update(kw)
    return BacktestRequest(events=events, prices=prices, **base)


# ------------------------------------------------------------------ no look-ahead
def test_no_lookahead_bars_before_execution_are_never_read():
    prices = [
        bar(900, 100, h=500, l=100, c=500),    # BEFORE the event: huge spike must be ignored
        bar(1000, 100, h=500, l=100, c=500),   # same timestamp as event: follower cannot act yet
        bar(1100, 100),                        # first bar at/after T+72s -> fill here
        bar(1200, 100),
    ]
    out = run_backtest(req([ev()], prices))
    r = out["results"][0]
    assert out["events"] == 1
    assert r["entry_ts"] == 1100
    assert r["hit"] is False and out["hits"] == 0
    assert r["gross_return_pct"] == 0


def test_bar_inside_latency_window_is_not_used_for_entry():
    # exec_ts = 1072, so a bar at 1050 must be skipped even though it is after the event
    prices = [bar(1050, 50), bar(1100, 100), bar(1200, 100)]
    r = run_backtest(req([ev()], prices))["results"][0]
    assert r["entry_ts"] == 1100 and r["entry_price"] == 100


# ------------------------------------------------------------------ token isolation
def test_event_never_sees_other_tokens_prices():
    prices = [bar(2000, 1, h=500, l=1, c=500, token="ORCA")]
    out = run_backtest(req([ev("QNT")], prices))
    assert out["events"] == 0
    assert out["skip_reasons"] == {"no_price_data_for_token": 1}


def test_mixed_tokens_only_own_bars_used():
    prices = [
        bar(1100, 100, token="QNT"), bar(1200, 100, token="QNT"),
        bar(1100, 1, h=900, l=1, c=900, token="ORCA"), bar(1200, 1, h=900, l=1, c=900, token="ORCA"),
    ]
    out = run_backtest(req([ev("QNT")], prices))
    assert out["events"] == 1
    assert out["results"][0]["gross_return_pct"] == 0
    assert out["hits"] == 0


# ------------------------------------------------------------------ follower price & costs
def test_entry_uses_follower_price_not_whale_price():
    prices = [bar(1100, 110), bar(1200, 110)]
    r = run_backtest(req([ev(price=100)], prices))["results"][0]
    assert r["whale_price"] == 100
    assert r["entry_price"] == 110


def test_costs_reduce_return_exactly():
    # entry open 100, slippage 50bps -> 100.5 ; time-exit close 100 -> 99.5 after exit slippage
    prices = [bar(1100, 100), bar(1200, 100)]
    out = run_backtest(req([ev()], prices, slippage_bps=50, fee_bps=30, gas_usd=2, notional_usd=1000))
    r = out["results"][0]
    gross = (99.5 / 100.5 - 1) * 100
    cost = 2 * 0.30 + 2 * 2 / 1000 * 100          # 0.6% fees + 0.4% gas
    assert r["entry_price"] == pytest.approx(100.5)
    assert r["gross_return_pct"] == pytest.approx(gross, abs=1e-4)
    assert r["net_return_pct"] == pytest.approx(gross - cost, abs=1e-4)
    assert out["wins"] == 0 and out["win_rate_pct"] == 0


# ------------------------------------------------------------------ exits
def test_target_exit_is_not_peak_picking():
    prices = [
        bar(1100, 100, h=106, l=99, c=101),    # touches target 105 here
        bar(1200, 101, h=150, l=100, c=140),   # later spike must NOT be credited
    ]
    r = run_backtest(req([ev()], prices))["results"][0]
    assert r["exit_reason"] == "target" and r["hit"] is True
    assert r["exit_price"] == pytest.approx(105)
    assert r["gross_return_pct"] == pytest.approx(5.0)


def test_stop_wins_when_stop_and_target_hit_in_same_bar():
    prices = [bar(1100, 100, h=110, l=90, c=100), bar(1200, 100)]
    r = run_backtest(req([ev()], prices, stop_loss_pct=5))["results"][0]
    assert r["exit_reason"] == "stop"
    assert r["gross_return_pct"] == pytest.approx(-5.0)


def test_gap_through_stop_fills_at_open():
    prices = [bar(1100, 100), bar(1200, 90, h=91, l=89, c=90)]   # opens below the 95 stop
    r = run_backtest(req([ev()], prices, stop_loss_pct=5))["results"][0]
    assert r["exit_reason"] == "stop"
    assert r["exit_price"] == pytest.approx(90)


def test_time_exit_uses_last_bar_inside_horizon():
    prices = [
        bar(1100, 100), bar(2000, 100, c=102), bar(4600, 100, c=103),   # 4600 = fill+1h, inclusive
        bar(5000, 100, h=999, c=999),                                    # beyond horizon: ignored
    ]
    r = run_backtest(req([ev()], prices))["results"][0]
    assert r["exit_reason"] == "time" and r["exit_ts"] == 4600
    assert r["exit_price"] == pytest.approx(103)


def test_mae_mfe_are_tracked():
    prices = [bar(1100, 100, h=104, l=97, c=100), bar(1200, 100)]
    r = run_backtest(req([ev()], prices))["results"][0]
    assert r["mae_pct"] == pytest.approx(-3.0)
    assert r["mfe_pct"] == pytest.approx(4.0)


# ------------------------------------------------------------------ skips
def test_max_entry_delay_is_enforced():
    prices = [bar(1000 + 10 * H, 100), bar(1000 + 11 * H, 100)]    # first usable bar is 10h late
    out = run_backtest(req([ev()], prices, max_entry_delay_hours=1))
    assert out["events"] == 0 and out["skip_reasons"] == {"entry_delay_exceeded": 1}
    out2 = run_backtest(req([ev()], prices, max_entry_delay_hours=24, horizon_hours=2))
    assert out2["events"] == 1


def test_illiquid_entry_bar_is_skipped():
    prices = [bar(1100, 100, vol=100), bar(1200, 100)]             # $1000 vs $100 volume
    out = run_backtest(req([ev()], prices, notional_usd=1000, max_participation_pct=5))
    assert out["events"] == 0 and out["skip_reasons"] == {"illiquid_entry_bar": 1}


def test_no_bar_after_latency_is_skipped():
    out = run_backtest(req([ev()], [bar(900, 100)]))
    assert out["skip_reasons"] == {"no_bar_after_latency": 1}


def test_sells_and_cex_in_are_ignored_cex_out_is_traded():
    prices = [bar(1100, 100), bar(1200, 100)]
    evs = [ev(side="SELL"), ev(side="CEX_IN"), ev(side="CEX_OUT")]
    out = run_backtest(req(evs, prices))
    assert out["events"] == 1 and out["results"][0]["side"] == "CEX_OUT"


# ------------------------------------------------------------------ summary + validation
def test_summary_profit_factor_and_rates():
    prices = [
        bar(1100, 100, h=106), bar(1200, 100),                         # event 1: target hit (+5)
        bar(5000, 100, h=100, l=94, c=94), bar(5100, 94),              # event 2 (ts=4900): loses
    ]
    evs = [ev(ts=1000), ev(ts=4900, wallet="w2")]
    out = run_backtest(req(evs, prices, stop_loss_pct=5, horizon_hours=1))
    assert out["events"] == 2 and out["hits"] == 1 and out["wins"] == 1
    assert out["hit_rate_pct"] == 50 and out["win_rate_pct"] == 50
    assert out["profit_factor"] == pytest.approx(5 / 5, abs=1e-3)


def test_inconsistent_ohlc_is_rejected():
    with pytest.raises(ValidationError):
        PriceBar(token="QNT", ts=1, open=100, high=90, low=80, close=85, volume_usd=1)


def test_volume_is_required():
    with pytest.raises(ValidationError):
        PriceBar(token="QNT", ts=1, open=1, high=1, low=1, close=1)
