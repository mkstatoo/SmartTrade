from bisect import bisect_left
from collections import defaultdict
from statistics import mean
from .ids import canonical_address
from .models import BacktestRequest
BUY_SIDES=("BUY","CEX_OUT")

def _dedup(events):
    seen=set(); out=[]
    for e in sorted(events,key=lambda x:x.ts):
        key=(e.chain.lower(), canonical_address(e.chain,e.token),
             canonical_address(e.chain,e.wallet), e.tx_hash.lower(), e.log_index, e.side, e.ts)
        # Stable event identity where available; conservative content fingerprint for providers
        # that omit tx/log identifiers (e.g. CEX imports).
        if e.tx_hash:
            identity=key
        else:
            identity=key+(round(e.usd_value,8),round(e.price,12))
        if identity in seen: continue
        seen.add(identity)
        out.append(e)
    return out

def _simulate(e,bars,ts_list,req):
    exec_ts=e.ts+req.detection_latency_sec+req.block_latency_sec
    i=bisect_left(ts_list,exec_ts)
    if i>=len(bars): return None,"no_bar_after_latency"
    entry_bar=bars[i]
    if entry_bar.ts-e.ts>req.max_entry_delay_hours*3600:return None,"entry_delay_exceeded"
    if entry_bar.volume_usd<=0 or req.notional_usd/entry_bar.volume_usd*100>req.max_participation_pct:return None,"illiquid_entry_bar"
    slip=req.slippage_bps/1e4; entry_px=entry_bar.open*(1+slip)
    target_px=entry_px*(1+req.target_return_pct/100); stop_px=entry_px*(1-req.stop_loss_pct/100) if req.stop_loss_pct else None
    end_ts=entry_bar.ts+req.horizon_hours*3600; exit_level=None; reason="time"; exit_bar=entry_bar; min_low=entry_px; max_high=entry_px
    for b in bars[i:]:
        if b.ts>end_ts: break
        exit_bar=b; min_low=min(min_low,b.low); max_high=max(max_high,b.high)
        if stop_px is not None and b.low<=stop_px: exit_level=min(stop_px,b.open); reason="stop"; break
        if b.high>=target_px: exit_level=max(target_px,b.open); reason="target"; break
    if exit_level is None: exit_level=exit_bar.close
    exit_px=exit_level*(1-slip); gross=(exit_px/entry_px-1)*100
    cost=2*req.fee_bps/100+2*req.gas_usd/req.notional_usd*100; net=gross-cost
    return {"wallet":e.wallet,"chain":e.chain,"token":e.token,"side":e.side,"event_ts":e.ts,"whale_price":e.price,"exec_ts":exec_ts,"entry_ts":entry_bar.ts,"entry_price":round(entry_px,8),"exit_ts":exit_bar.ts,"exit_price":round(exit_px,8),"exit_reason":reason,"gross_return_pct":round(gross,4),"net_return_pct":round(net,4),"mae_pct":round((min_low/entry_px-1)*100,4),"mfe_pct":round((max_high/entry_px-1)*100,4),"time_to_exit_sec":exit_bar.ts-entry_bar.ts,"hit":reason=="target"},None

def _timeframe_seconds(tf):
    try:
        unit=tf[-1].lower(); n=int(tf[:-1])
        return n*{"s":1,"m":60,"h":3600,"d":86400}[unit]
    except Exception: return 10**18

def run_backtest(req):
    bars_by_key=defaultdict(list)
    for p in req.prices: bars_by_key[(p.chain.lower(),canonical_address(p.chain,p.token),p.timeframe)].append(p)
    ts_by_key={}
    for k,bars in bars_by_key.items(): bars.sort(key=lambda x:x.ts); ts_by_key[k]=[b.ts for b in bars]
    results=[]; skipped=[]; deduped=_dedup([e for e in req.events if e.side in BUY_SIDES])
    last_successful_by_wallet_token={}
    effective=[]
    for e in deduped:
        key=(e.chain.lower(), canonical_address(e.chain,e.wallet), canonical_address(e.chain,e.token))
        candidates=[(k,b) for k,b in bars_by_key.items() if k[0]==e.chain.lower() and k[1]==canonical_address(e.chain,e.token) and k[2]==req.timeframe]
        if not candidates:
            skipped.append({"wallet":e.wallet,"token":e.token,"event_ts":e.ts,"reason":"no_price_data_for_token"}); continue
        k,bars=candidates[0]; ts_list=ts_by_key[k]
        if key in last_successful_by_wallet_token and e.ts-last_successful_by_wallet_token[key] < req.horizon_hours*3600:
            skipped.append({"wallet":e.wallet,"token":e.token,"event_ts":e.ts,"reason":"overlapping_wallet_token"}); continue
        res,reason=_simulate(e,bars,ts_list,req)
        if res:
            results.append(res); effective.append(e); last_successful_by_wallet_token[key]=res["exit_ts"]
        else: skipped.append({"wallet":e.wallet,"token":e.token,"event_ts":e.ts,"reason":reason})
    nets=[r["net_return_pct"] for r in results]; n=len(results); hits=sum(r["hit"] for r in results); wins=sum(x>0 for x in nets); gp=sum(x for x in nets if x>0); gl=-sum(x for x in nets if x<0)
    reasons=defaultdict(int)
    for s in skipped: reasons[s["reason"]]+=1
    return {"events":n,"effective_n":len(results),"hits":hits,"hit_rate_pct":round(hits/n*100,2) if n else 0,"wins":wins,"losses":n-wins,"win_rate_pct":round(wins/n*100,2) if n else 0,"avg_net_return_pct":round(mean(nets),4) if n else 0,"profit_factor":round(gp/gl,4) if gl else None,"skipped":len(skipped),"skip_reasons":dict(reasons),"assumptions":req.model_dump(exclude={"events","prices"}),"results":results,"skipped_events":skipped}
