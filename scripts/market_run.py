#!/usr/bin/env python3
"""REAL-CHAIN run of the wallet-attribution pipeline on Ethereum mainnet (Uniswap V2/V3 watch-list).

  1. discovery window  : ALL swap logs -> rank pools -> verify the top candidates through the Uniswap factories -> top-K by USD volume
  2. watch window      : only swaps of the watched pools -> (Chainlink cross-check of the ETH price while state is still recent)
                         -> transaction receipts -> wallet trades -> PnL
  3. independent checks: Chainlink ETH/USD vs the ETH price taken from swaps; sample of receipts and tx.from re-fetched through a
                         DIFFERENT provider; cross-pool price consistency of the same token; attribution rates.
Needs reports/selection.json (provider_probe.py), DATABASE_URL, and the private endpoint env vars. Never writes endpoint URLs or host
names into reports. Writes reports/market_run.json and reports/market_run.md. Exit: 0 ok, 1 an integrity check failed, 2 nothing could run."""
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.chain import abi, market, pipeline  # noqa: E402
from app.chain.ingest import ingest  # noqa: E402
from app.chain.rpc import JsonRpcSource, RpcError  # noqa: E402
from app.migrate import migrate  # noqa: E402

CHAIN = "ethereum"
LABEL, DLABEL = "ethereum-mkt", "ethereum-mkt-disc"
CONF = 12
DISC = int(os.getenv("MARKET_DISCOVERY_BLOCKS", "200"))
WATCH = int(os.getenv("MARKET_WATCH_BLOCKS", "300"))
TOP_K = int(os.getenv("MARKET_TOP_K", "30"))
RECEIPT_LIMIT = int(os.getenv("MARKET_RECEIPT_LIMIT", "3000"))
SAMPLE = int(os.getenv("MARKET_VERIFY_SAMPLE", "50"))
WORKERS = int(os.getenv("MARKET_WORKERS", "4"))


def url_for(cfg, chain, name):
    if name.startswith("private-"):
        return os.environ[f"RPC_{chain.upper()}_{name.split('-')[1]}"]
    for p in cfg["chains"][chain]["providers"]:
        if p["name"] == name:
            return p["url"]
    raise KeyError(name)


def q(dsn, sql, *a):
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        return c.execute(sql, a).fetchall()


def step(rep, name, fn):
    t0 = time.time()
    try:
        out = fn()
        rep["steps"][name] = {"ok": True, "seconds": round(time.time() - t0, 1)}
        return out
    except Exception as exc:  # noqa: BLE001
        rep["steps"][name] = {"ok": False, "seconds": round(time.time() - t0, 1), "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        return None


# ------------------------------------------------------------------------------------------------ independent checks
def chainlink_check(rpc, cfg, series, head):
    """ETH price from swaps vs Chainlink at the same blocks. Chainlink is a cross-check only, never an input."""
    feed = cfg["chainlink_eth_usd"]
    out = {"feed": feed, "samples": [], "unavailable": 0}
    dec = market._try(rpc, feed, market.SEL["feed_decimals"])
    if dec is None:
        out["status"] = "unavailable: feed address did not answer decimals() (address from memory could be wrong, or state not served)"
        return out
    d = market.dec_uint(dec)
    blocks = sorted({p[0][0] for p in series.pts})[-6:]
    for b in blocks:
        res = market._try(rpc, feed, market.SEL["latestRoundData"], b)
        if res is None:
            out["unavailable"] += 1
            continue
        px = Decimal(market.dec_int(res, 1)) / Decimal(10) ** d
        mine = series.at(b, 10 ** 9)
        out["samples"].append({"block": b, "blocks_behind_head": head - b, "chainlink": float(px), "from_swaps": float(mine),
                               "deviation_pct": float(abs(mine - px) / px * 100)})
    if not out["samples"]:
        out["status"] = "unavailable: node did not serve historical state for these blocks"
        return out
    devs = [s["deviation_pct"] for s in out["samples"]]
    out["median_deviation_pct"], out["max_deviation_pct"] = statistics.median(devs), max(devs)
    out["criterion"] = "pass if >=3 samples, median <= 0.5% and max <= 1.5% (Chainlink only updates on 0.5% moves or its heartbeat)"
    out["status"] = "pass" if len(devs) >= 3 and out["median_deviation_pct"] <= 0.5 and out["max_deviation_pct"] <= 1.5 else "fail"
    return out


def verify_with_second_provider(ver, dsn, chain, tokens):
    rows = q(dsn, "SELECT x.tx_hash, x.from_addr, x.status, x.gas_used, x.block_hash FROM chain_txs x "
                  "JOIN chain_blocks b ON b.chain=x.chain AND b.block_hash=x.block_hash AND b.canonical WHERE x.chain=%s "
                  "ORDER BY md5(x.tx_hash) LIMIT %s", chain, SAMPLE)
    bad, errors = [], 0
    for r in rows:
        try:
            rc = ver.receipt(r["tx_hash"])
        except RpcError:
            errors += 1
            continue
        stored = Counter((t["log_index"], t["token"], t["from_addr"], t["to_addr"], int(t["amount"])) for t in
                         q(dsn, "SELECT * FROM chain_transfers WHERE chain=%s AND tx_hash=%s AND block_hash=%s", chain, r["tx_hash"], r["block_hash"]))
        theirs = Counter()
        for l in rc["logs"]:
            if l["address"] in tokens and l["topics"] and l["topics"][0] == abi.TOPIC_ERC20_TRANSFER:
                d = abi.decode(l)
                if d:
                    theirs[(l["log_index"], l["address"], d[1]["from"], d[1]["to"], int(d[1]["amount"]))] += 1
        if (rc["from"], rc["status"], rc["gas_used"], rc["block_hash"]) != (r["from_addr"], r["status"], int(r["gas_used"]), r["block_hash"]) or stored != theirs:
            bad.append(r["tx_hash"][:14])
    trades = q(dsn, "SELECT tx_hash, wallet FROM chain_trades_canonical WHERE chain=%s AND confidence='confirmed' ORDER BY md5(tx_hash || token) LIMIT %s", chain, SAMPLE)
    bad_from, from_err = [], 0
    for t in trades:
        try:
            if ver.tx(t["tx_hash"])["from"] != t["wallet"]:
                bad_from.append(t["tx_hash"][:14])
        except RpcError:
            from_err += 1
    return {"receipts_checked": len(rows) - errors, "receipt_mismatches": bad, "receipt_fetch_errors": errors,
            "trade_wallets_checked": len(trades) - from_err, "wallet_mismatches": bad_from, "tx_fetch_errors": from_err,
            "passed": not bad and not bad_from and (len(rows) - errors) > 0 and (len(trades) - from_err) > 0}


def cross_pool_prices(dsn, chain):
    """Same token, same 10-block bucket, two different pools: their median execution prices should agree within fees/arbitrage."""
    per = defaultdict(list)
    for r in q(dsn, "SELECT token, block_number, evidence FROM chain_trades_canonical WHERE chain=%s", chain):
        for s in r["evidence"]["swaps"]:
            per[(r["token"], r["block_number"] // 10, s["pool"])].append(Decimal(s["price_usd"]))
    by_tb = defaultdict(dict)
    for (tok, bucket, pool), px in per.items():
        if len(px) >= 2:
            by_tb[(tok, bucket)][pool] = statistics.median(px)
    devs = []
    for pools in by_tb.values():
        if len(pools) >= 2:
            v = sorted(pools.values())
            devs.append(float(abs(v[-1] - v[0]) / ((v[-1] + v[0]) / 2) * 100))
    if not devs:
        return {"buckets_compared": 0, "note": "no token had >=2 pools with >=2 swaps in the same 10-block bucket"}
    devs.sort()
    return {"buckets_compared": len(devs), "median_deviation_pct": statistics.median(devs), "p90_deviation_pct": devs[int(0.9 * (len(devs) - 1))],
            "max_deviation_pct": devs[-1]}


def wallet_summary(dsn, chain):
    rows = q(dsn, "SELECT wallet, count(*) n, sum(usd) usd, count(*) FILTER (WHERE confidence='confirmed') c FROM chain_trades_canonical "
                  "WHERE chain=%s GROUP BY wallet ORDER BY sum(usd) DESC", chain)
    pnl = pipeline.wallet_pnl(dsn, chain)
    closed = sum(r["totals"]["closed_trades"] for r in pnl.values())
    known = sum(r["totals"]["closed_trades_fully_known"] for r in pnl.values())
    unk = sum(Decimal(str(r["totals"]["realized_unknown_basis_proceeds_usd"])) for r in pnl.values())
    return {"wallets": len(rows), "wallets_with_confirmed_trade": sum(1 for r in rows if r["c"]), "wallets_with_2plus_trades": sum(1 for r in rows if r["n"] >= 2),
            "top_by_usd": [{"wallet": r["wallet"], "trades": r["n"], "usd": float(r["usd"])} for r in rows[:10]],
            "pnl": {"wallets_with_pnl": len(pnl), "closed_trades": closed, "closed_trades_with_known_cost": known,
                    "sells_with_unknown_basis_usd": float(unk),
                    "note": "window is short: most sells have no earlier buy in the data, so their cost is UNKNOWN and is not turned into a profit or loss"}}


def md(rep):
    L = ["# Wallet attribution on real Ethereum data", "", f"run at {rep['at_utc']} UTC. Everything below is a measurement of THIS run only.", ""]
    for k, v in rep.get("headline", {}).items():
        L.append(f"- **{k}**: {v}")
    L += ["", "```json", json.dumps({k: v for k, v in rep.items() if k != "headline"}, indent=1, default=str), "```", ""]
    return "\n".join(L)


# ------------------------------------------------------------------------------------------------ main
def main():
    out = Path(os.getenv("REPORTS_DIR", ROOT / "reports"))
    out.mkdir(parents=True, exist_ok=True)
    cfg_p = json.loads(Path(os.getenv("PROVIDERS_FILE", ROOT / "scripts" / "providers.json")).read_text())
    sel = json.loads((out / "selection.json").read_text()).get(CHAIN)
    rep = {"at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "chain": CHAIN, "steps": {}, "headline": {},
           "params": {"discovery_blocks": DISC, "watch_blocks": WATCH, "top_k": TOP_K, "receipt_limit": RECEIPT_LIMIT, "confirmations": CONF}}

    def finish(code):
        (out / "market_run.json").write_text(json.dumps(rep, indent=1, default=str))
        (out / "market_run.md").write_text(md(rep))
        print(json.dumps(rep["headline"], default=str), flush=True)
        return code

    if not sel or not sel.get("primary"):
        rep["skipped"] = "no usable primary provider for ethereum in selection.json"
        return finish(2)
    dsn = os.environ["DATABASE_URL"]
    migrate(dsn)
    cfg = market.CHAINS[CHAIN]
    prim_url = url_for(cfg_p, CHAIN, sel["primary"])
    prim = JsonRpcSource(prim_url, timeout=30, retries=3, backoff=1.0)
    ver = JsonRpcSource(url_for(cfg_p, CHAIN, sel["verifier"]), timeout=30, retries=3, backoff=1.0) if sel.get("verifier") else None
    rng_primary = sel.get("ranges", {}).get(sel["primary"], 1)
    batch = max(1, min(50, rng_primary))
    rep["primary"], rep["verifier"], rep["getlogs_range"] = sel["primary"], sel.get("verifier"), rng_primary
    head = prim.head()
    last = head - CONF - 3
    start = last - (DISC + WATCH) + 1
    rep["window"] = {"head": head, "discovery": [start, start + DISC - 1], "watch": [start + DISC, last]}

    d1 = step(rep, "ingest_discovery", lambda: ingest(prim, dsn, DLABEL, start_block=start, confirmations=CONF, batch=batch,
                                                      max_blocks=DISC, topics0=pipeline.SWAP_TOPICS))
    if d1 is None:
        return finish(1)
    rep["discovery_ingest"] = {k: getattr(d1, k) for k in ("blocks", "logs", "decoded", "decode_errors", "reorgs", "next_block")} | {"notes": d1.notes[:5]}
    disc = step(rep, "discover_pools", lambda: pipeline.discover_pools(dsn, prim, LABEL, cfg, discovery_chain=DLABEL, top_k=TOP_K))
    if disc is None:
        return finish(1)
    rep["discovery"] = disc | {"rejected_unverified": len(disc["rejected_unverified"]), "constants": {a[:10]: v["ok"] for a, v in disc["constants"].items()}}
    pools = sorted(pipeline.watch_list(dsn, LABEL))
    w1 = step(rep, "ingest_watch", lambda: ingest(prim, dsn, LABEL, start_block=start + DISC, confirmations=CONF, batch=batch,
                                                  max_blocks=WATCH, topics0=pipeline.SWAP_TOPICS, addresses=pools))
    if w1 is None:
        return finish(1)
    rep["watch_ingest"] = {k: getattr(w1, k) for k in ("blocks", "logs", "decoded", "decode_errors", "reorgs", "next_block")} | {"notes": w1.notes[:5]}

    # ETH price vs Chainlink NOW, while the node still serves state for these blocks
    conn = psycopg.connect(dsn, row_factory=dict_row)
    pool_objs = pipeline.watch_list(dsn, LABEL)
    dec = {r["address"]: r["decimals"] for r in conn.execute("SELECT address, decimals FROM chain_tokens WHERE chain=%s", (LABEL,))}
    for t, (_, dd) in cfg["expected"].items():
        dec.setdefault(t, dd)
    series, dropped = pipeline.robust_eth_series(pipeline.eth_points(cfg, dec, pool_objs, [s for s in pipeline.load_swaps(conn, LABEL) if s["pool"] in pool_objs]))
    conn.close()
    rep["eth_series"] = {"points": len(series.pts), "outliers_dropped": dropped,
                         "min": float(min(p[1] for p in series.pts)) if series.pts else None, "max": float(max(p[1] for p in series.pts)) if series.pts else None}
    rep["chainlink"] = step(rep, "chainlink_check", lambda: chainlink_check(prim, cfg, series, prim.head())) or {"status": "error"}

    col = step(rep, "collect_receipts", lambda: pipeline.collect_txs(dsn, lambda: JsonRpcSource(prim_url, timeout=30, retries=3, backoff=1.0),
                                                                      LABEL, workers=WORKERS, limit=RECEIPT_LIMIT))
    if col is None:
        return finish(1)
    rep["receipts"] = {"stored": col.txs, "transfers": col.transfers, "errors": col.receipt_errors, "inconsistent_with_getlogs": col.inconsistent,
                       "decode_errors": col.decode_errors, "notes": col.notes}
    der = step(rep, "derive_trades", lambda: pipeline.derive_trades(dsn, LABEL, cfg))
    if der is None:
        return finish(1)
    swap_txs = der.txs
    quote_only = der.skips.get("quote_only", 0)
    rep["trades"] = {"txs_examined": der.txs, "txs_without_receipt": der.no_receipt, "trades": der.trades, "confirmed": der.confirmed, "mismatch": der.mismatch,
                     "skips_by_reason": dict(der.skips), "eth_points": der.eth_points, "eth_outliers_dropped": der.eth_outliers_dropped}
    with_trade = q(dsn, "SELECT count(DISTINCT tx_hash) n FROM chain_trades_canonical WHERE chain=%s", LABEL)[0]["n"]
    denom = max(1, swap_txs - quote_only)
    rep["attribution"] = {"swap_txs_excluding_quote_only": swap_txs - quote_only, "txs_with_a_trade": with_trade,
                          "share_with_a_trade": round(with_trade / denom, 4),
                          "confirmed_share_of_trades": round(der.confirmed / max(1, der.trades), 4)}
    tokens = {r["token0"] for r in q(dsn, "SELECT token0 FROM chain_pools WHERE chain=%s", LABEL)} | {r["token1"] for r in q(dsn, "SELECT token1 FROM chain_pools WHERE chain=%s", LABEL)}
    if ver is not None:
        rep["second_provider"] = step(rep, "second_provider_check", lambda: verify_with_second_provider(ver, dsn, LABEL, tokens)) or {"passed": False}
    else:
        rep["second_provider"] = {"passed": None, "note": "no verifier provider available"}
    rep["cross_pool_prices"] = step(rep, "cross_pool_prices", lambda: cross_pool_prices(dsn, LABEL))
    rep["wallets"] = step(rep, "wallet_summary", lambda: wallet_summary(dsn, LABEL))

    h = rep["headline"]
    h["window blocks (discovery + watch)"] = f"{DISC} + {WATCH}"
    h["pools watched"] = len(pools)
    h["receipts stored / errors / inconsistent"] = f"{col.txs} / {col.receipt_errors} / {col.inconsistent}"
    h["trades (confirmed / mismatch)"] = f"{der.trades} ({der.confirmed} / {der.mismatch})"
    h["share of swap txs that became a trade"] = rep["attribution"]["share_with_a_trade"]
    h["chainlink check"] = rep["chainlink"].get("status")
    h["second provider check"] = rep["second_provider"].get("passed")
    if rep.get("wallets"):
        h["wallets with a confirmed trade"] = rep["wallets"]["wallets_with_confirmed_trade"]
    failed = [name for name, s in rep["steps"].items() if not s["ok"]]
    integrity = {"steps_failed": failed, "receipts_inconsistent": col.inconsistent,
                 "chainlink_failed": rep["chainlink"].get("status") == "fail",
                 "second_provider_failed": rep["second_provider"].get("passed") is False}
    rep["integrity"] = integrity
    bad = bool(failed or col.inconsistent or integrity["chainlink_failed"] or integrity["second_provider_failed"])
    h["integrity"] = "FAIL: " + json.dumps(integrity) if bad else "no integrity problem found by the checks above"
    return finish(1 if bad else 0)


if __name__ == "__main__":
    sys.exit(main())
