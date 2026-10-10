from app.backtest import run_backtest
from app.models import BacktestRequest

def event(ts=0, wallet="w", tx="tx", log=1):
    return {"wallet":wallet,"token":"0xtoken","chain":"base","ts":ts,"side":"BUY","usd_value":100,"price":10,"tx_hash":tx,"log_index":log}

def bar(ts, o=10,h=11,l=9,c=10,token="0xtoken",chain="base"):
    return {"chain":chain,"token":token,"ts":ts,"timeframe":"1m","open":o,"high":h,"low":l,"close":c,"volume_usd":1_000_000}

def test_duplicate_chain_tx_log_wallet_side_is_deduped():
    req=BacktestRequest(events=[event(),event()],prices=[bar(100),bar(200)],target_return_pct=5)
    r=run_backtest(req)
    assert r["effective_n"]==1

def test_overlapping_wallet_token_events_are_not_independent():
    req=BacktestRequest(events=[event(0,"w","a",1),event(60,"w","b",1)],prices=[bar(100),bar(200),bar(3600)],target_return_pct=5)
    r=run_backtest(req)
    assert r["effective_n"]==1 and r["skip_reasons"]["overlapping_wallet_token"]==1

def test_same_symbol_different_chain_does_not_mix_prices():
    req=BacktestRequest(events=[event()],prices=[bar(100,token="0xtoken",chain="ethereum"),bar(100,token="0xtoken",chain="base")],target_return_pct=5)
    r=run_backtest(req)
    assert len(r["results"])==1 and r["results"][0]["chain"]=="base"
