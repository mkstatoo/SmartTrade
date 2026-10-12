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
from app.chain.rpc import FailoverSource, JsonRpcSource, RpcError  # noqa: E402
from app.migrate import migrate  # noqa: E402

CHAIN = os.getenv("MARKET_CHAIN", "ethereum")
if CHAIN not in market.CHAINS:
    raise SystemExit(f"unknown chain {CHAIN!r}")
LABEL, DLABEL = f"{CHAIN}-mkt", f"{CHAIN}-mkt-disc"     # ethereum keeps its historical labels
SUFFIX = "" if CHAIN == "ethereum" else f"_{CHAIN}"
CONF = 12
DISC = int(os.getenv("MARKET_DISCOVERY_BLOCKS", "300"))
WATCH = int(os.getenv("MARKET_WATCH_BLOCKS", "1500"))
TOP_K = int(os.getenv("MARKET_TOP_K", "30"))
RECEIPT_LIMIT = int(os.getenv("MARKET_RECEIPT_LIMIT", "150000"))
CANDIDATES = int(os.getenv("MARKET_CANDIDATES", "300"))
SAMPLE = int(os.getenv("MARKET_VERIFY_SAMPLE", "50"))
WORKERS = int(os.getenv("MARKET_WORKERS", "4"))
FRESH_TAIL = int(os.getenv("MARKET_FRESH_TAIL_BLOCKS", "40"))
# the independent verifier is usually a non-archive public node: it only serves recent receipts, so the sample is drawn from the newest blocks
VERIFY_RECENT_BLOCKS = int(os.getenv("MARKET_VERIFY_RECENT_BLOCKS", "100"))


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


FLUSH = []          # set by main(): writes the (partial) report, so a step that is killed by a time limit still leaves its predecessors on record


def step(rep, name, fn):
    t0 = time.time()
    try:
        out = fn()
        rep["steps"][name] = {"ok": True, "seconds": round(time.time() - t0, 1)}
    except Exception as exc:  # noqa: BLE001
        rep["steps"][name] = {"ok": False, "seconds": round(time.time() - t0, 1), "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        out = None
    for f in FLUSH:
        f()
    return out


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
                  "AND x.block_number >= (SELECT max(block_number) FROM chain_txs WHERE chain=%s) - %s "
                  "ORDER BY md5(x.tx_hash) LIMIT %s", chain, chain, VERIFY_RECENT_BLOCKS, SAMPLE)
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
    trades = q(dsn, "SELECT tx_hash, wallet FROM chain_trades_canonical WHERE chain=%s AND confidence='confirmed' "
                  "AND block_number >= (SELECT max(block_number) FROM chain_txs WHERE chain=%s) - %s ORDER BY md5(tx_hash || token) LIMIT %s",
                  chain, chain, VERIFY_RECENT_BLOCKS, SAMPLE)
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


def volume_coverage(dsn, chain, swaps, pools, val):
    """How much of the traded USD volume (priced swaps with exactly one quote leg) sits in transactions that became a wallet trade,
    versus transactions that were skipped and why. Counting transactions overstates coverage when bots trade small and often."""
    traded = {r["tx_hash"] for r in q(dsn, "SELECT DISTINCT tx_hash FROM chain_trades_canonical WHERE chain=%s", chain)}
    skip = {}
    for r in q(dsn, "SELECT tx_hash, reason FROM chain_trade_skips WHERE chain=%s", chain):
        skip.setdefault(r["tx_hash"], r["reason"])
    usd = Counter()
    n = Counter()
    for sw in swaps:
        r = val.priced_swap(pools[sw["pool"]], sw["d0"], sw["d1"], sw["block"], sw["log_index"])
        if not isinstance(r, dict):
            continue
        cls = "attributed_to_a_wallet" if sw["tx"] in traded else ("skipped:" + skip[sw["tx"]] if sw["tx"] in skip else "no_receipt_or_other")
        usd[cls] += r["usd"]
        n[cls] += 1
    total = sum(usd.values()) or Decimal(1)
    return {"priced_swaps_usd_total": float(sum(usd.values())),
            "by_class": {k: {"usd": float(v), "share": round(float(v / total), 4), "swaps": n[k]} for k, v in usd.most_common()},
            "note": "volume-weighted: the share of traded USD whose wallet we know; txs counted without weights would overstate it"}


def cross_pool_prices(swaps, pools, val):
    """Same token, same 20-block bucket, two different pools: median execution prices of ALL priced swaps (attributed or not) should
    agree up to fee tiers and arbitrage lag. An independent check of the pricing path (quote conversion, decimals, direction)."""
    per = defaultdict(list)
    for sw in swaps:
        r = val.priced_swap(pools[sw["pool"]], sw["d0"], sw["d1"], sw["block"], sw["log_index"])
        if isinstance(r, dict):
            per[(r["token"], sw["block"] // 20, sw["pool"])].append(r["price_usd"])
    by_tb = defaultdict(dict)
    for (tok, bucket, pool), px in per.items():
        if len(px) >= 2:
            by_tb[(tok, bucket)][pool] = statistics.median(px)
    devs = []
    for pl in by_tb.values():
        if len(pl) >= 2:
            v = sorted(pl.values())
            devs.append(float(abs(v[-1] - v[0]) / ((v[-1] + v[0]) / 2) * 100))
    if not devs:
        return {"buckets_compared": 0, "note": "no token had >=2 pools with >=2 priced swaps in the same 20-block bucket"}
    devs.sort()
    return {"buckets_compared": len(devs), "tokens_compared": len({k[0] for k in by_tb if len(by_tb[k]) >= 2}),
            "median_deviation_pct": statistics.median(devs), "p90_deviation_pct": devs[int(0.9 * (len(devs) - 1))], "max_deviation_pct": devs[-1]}


def state_check(rpc, dsn, chain):
    """Independent of the logs: for recent confirmed trades compare balanceOf(wallet) after minus before the block with the wallet's
    Transfer delta used for attribution. A node only serves state for recent blocks; if it does not, the result is 'unavailable'."""
    head = rpc.head()
    rows = q(dsn, "SELECT wallet, token, block_number, tx_hash, evidence FROM chain_trades_canonical WHERE chain=%s AND confidence='confirmed' "
                  "AND block_number >= %s ORDER BY md5(tx_hash || token) LIMIT 60", chain, head - 100)
    out = {"candidates": len(rows), "checked": 0, "exact_match": 0, "unavailable": 0, "mismatches": []}
    for r in rows:
        data = market.calldata(market.SEL["balanceOf"], r["wallet"])
        b1 = market._try(rpc, r["token"], data, r["block_number"])
        b0 = market._try(rpc, r["token"], data, r["block_number"] - 1)
        if b1 is None or b0 is None:
            out["unavailable"] += 1
            continue
        delta, expect = market.dec_uint(b1) - market.dec_uint(b0), int(r["evidence"]["sender_delta_raw"])
        out["checked"] += 1
        if delta == expect:
            out["exact_match"] += 1
        elif len(out["mismatches"]) < 10:
            out["mismatches"].append({"tx": r["tx_hash"][:14], "state_delta": str(delta), "log_delta": str(expect)})
    if out["checked"] < 10:
        out["status"] = "unavailable: fewer than 10 trades could be checked against node state"
    else:
        out["match_rate"] = round(out["exact_match"] / out["checked"], 4)
        out["criterion"] = "pass if >=10 checked and >=90% equal (other transactions of the same wallet in the same block legitimately differ)"
        out["status"] = "pass" if out["match_rate"] >= 0.9 else "fail"
    return out


def to_summary(dsn, chain):
    """Who do the transactions go to? Separates routers (seen in confirmed trades too) from private bot contracts."""
    txs = q(dsn, "SELECT x.tx_hash, x.to_addr FROM chain_txs x JOIN chain_blocks b ON b.chain=x.chain AND b.block_hash=x.block_hash AND b.canonical "
                 "WHERE x.chain=%s", chain)
    traded = {r["tx_hash"] for r in q(dsn, "SELECT DISTINCT tx_hash FROM chain_trades_canonical WHERE chain=%s", chain)}
    skipped = {r["tx_hash"] for r in q(dsn, "SELECT DISTINCT tx_hash FROM chain_trade_skips WHERE chain=%s AND reason='no_sender_transfer'", chain)} - traded
    top = lambda keep: [{"to": a, "txs": n} for a, n in Counter(r["to_addr"] for r in txs if r["tx_hash"] in keep).most_common(8)]  # noqa: E731
    return {"top_to_for_txs_with_a_trade": top(traded), "top_to_for_unattributed_txs": top(skipped), "unattributed_txs": len(skipped),
            "note": "addresses are not labelled here; a 'to' that is frequent among attributed trades is a public router, one that appears only among "
                    "unattributed txs is typically a private bot contract"}


def unattributed_beneficiaries(rpc, dsn, chain, sample=300):
    """DIAGNOSTIC ONLY (nothing is attributed from it): for transactions whose sender did not receive/pay the traded token, who DID end up with it?
    An address without code (EOA) is plausibly a real user behind a relayer; an address with code is a bot / vault / aggregator contract."""
    pools = {r["pool"] for r in q(dsn, "SELECT pool FROM chain_pools WHERE chain=%s", chain)}
    rows = q(dsn, "SELECT DISTINCT ON (s.tx_hash) s.tx_hash, s.block_hash, s.detail->>'token' AS token FROM chain_trade_skips s "
                  "JOIN chain_blocks b ON b.chain=s.chain AND b.block_hash=s.block_hash AND b.canonical "
                  "WHERE s.chain=%s AND s.reason='no_sender_transfer' AND s.tx_hash NOT IN (SELECT tx_hash FROM chain_trades_canonical WHERE chain=%s) "
                  "ORDER BY s.tx_hash LIMIT 5000", chain, chain)
    rows = sorted(rows, key=lambda r: __import__("hashlib").md5(r["tx_hash"].encode()).hexdigest())[:sample]
    kinds, repeat, errors = Counter(), Counter(), 0
    code_cache = {}
    for r in rows:
        tr = q(dsn, "SELECT to_addr, log_index FROM chain_transfers WHERE chain=%s AND block_hash=%s AND tx_hash=%s AND token=%s ORDER BY log_index DESC",
               chain, r["block_hash"], r["tx_hash"], r["token"])
        final = next((t["to_addr"] for t in tr if t["to_addr"] not in pools and t["to_addr"] != r["token"]), None)
        if final is None:
            kinds["no_final_recipient"] += 1
            continue
        repeat[final] += 1
        if final not in code_cache:
            try:
                code_cache[final] = len(rpc._call("eth_getCode", [final, "latest"])) > 2
            except RpcError:
                code_cache[final] = None
        c = code_cache[final]
        if c is None:
            errors += 1
        else:
            kinds["contract" if c else "eoa"] += 1
    return {"sampled": len(rows), "final_recipient_is": dict(kinds), "code_lookup_errors": errors,
            "most_repeated_recipients": [{"to": a, "txs": n} for a, n in repeat.most_common(5)],
            "note": "diagnostic only: an EOA recipient suggests a real user behind a relayer (a possible later attribution rule); a contract suggests a bot or aggregator"}


def wallet_summary(dsn, chain):
    rows = q(dsn, "SELECT wallet, count(*) n, sum(usd) usd, count(*) FILTER (WHERE confidence='confirmed') c FROM chain_trades_canonical "
                  "WHERE chain=%s GROUP BY wallet ORDER BY sum(usd) DESC", chain)
    pnl = pipeline.wallet_pnl(dsn, chain)
    closed = sum(r["totals"]["closed_trades"] for r in pnl.values())
    known_closed = sum(r["totals"]["closed_trades_fully_known"] for r in pnl.values())
    unk = sum(Decimal(str(r["totals"]["realized_unknown_basis_proceeds_usd"])) for r in pnl.values())
    per = []
    for w, r in pnl.items():
        t = r["totals"]
        per.append({"wallet": w, "closed_trades": t["closed_trades"], "closed_with_known_cost": t["closed_trades_fully_known"], "wins": t["wins"],
                    "realized_pnl_known_cost_usd": float(Decimal(str(t["realized_pnl_usd"]))),
                    "unrealized_pnl_usd": float(Decimal(str(t["unrealized_pnl_usd"]))),
                    "fees_in_trades_usd": float(Decimal(str(t["fees_in_trades_usd"]))),
                    "sells_with_unknown_basis_usd": float(Decimal(str(t["realized_unknown_basis_proceeds_usd"]))),
                    "open_positions_marked_at_last_price": sum(1 for x in r["tokens"].values() if x["open_qty"] > 0)})
    with_cost = [x for x in per if x["closed_with_known_cost"] >= 1]
    kn_closed = sum(x["closed_with_known_cost"] for x in with_cost)
    summary = {"wallets_with_a_known_cost_closed_trade": len(with_cost), "closed_trades_with_known_cost": kn_closed,
               "win_rate_on_those": round(sum(x["wins"] for x in with_cost) / kn_closed, 4) if kn_closed else None,
               "total_realized_known_cost_usd": round(sum(x["realized_pnl_known_cost_usd"] for x in with_cost), 2),
               "total_unrealized_usd_all_wallets": round(sum(x["unrealized_pnl_usd"] for x in per), 2),
               "top_by_realized_known_cost": sorted(with_cost, key=lambda x: -x["realized_pnl_known_cost_usd"])[:10],
               "bottom_by_realized_known_cost": sorted(with_cost, key=lambda x: x["realized_pnl_known_cost_usd"])[:5],
               "unrealized_caveat": "marked at the LAST execution price seen in this window; in thin pools that price is not what a position could be sold for, so treat it as indicative only",
               "caveat": "observed only inside this window: no history before it, so cost basis of earlier holdings is unknown (excluded, never invented); "
                         "wallets are tx.from only; execution price only (no off-chain costs); a ranking from one window is NOT evidence of skill"}
    return {"pnl_overview": summary, "wallets": len(rows), "wallets_with_confirmed_trade": sum(1 for r in rows if r["c"]), "wallets_with_2plus_trades": sum(1 for r in rows if r["n"] >= 2),
            "top_by_usd": [{"wallet": r["wallet"], "trades": r["n"], "usd": float(r["usd"])} for r in rows[:10]],
            "pnl": {"wallets_with_pnl": len(pnl), "closed_trades": closed, "closed_trades_with_known_cost": known_closed,
                    "sells_with_unknown_basis_usd": float(unk),
                    "trades_with_unpriced_gas": sum(r["gas_unpriced_trades"] for r in pnl.values()),
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

    def flush():
        rep["partial"] = True
        (out / f"market_run{SUFFIX}.json").write_text(json.dumps(rep, indent=1, default=str))
        (out / f"market_run{SUFFIX}.md").write_text(md(rep))

    def finish(code):
        rep.pop("partial", None)
        flush_final = (out / f"market_run{SUFFIX}.json")
        flush_final.write_text(json.dumps(rep, indent=1, default=str))
        (out / f"market_run{SUFFIX}.md").write_text(md(rep))
        print(json.dumps(rep["headline"], default=str), flush=True)
        return code
    FLUSH.append(flush)

    if not sel or not sel.get("primary"):
        rep["skipped"] = f"no usable primary provider for {CHAIN} in selection.json"
        return finish(2)
    dsn = os.environ["DATABASE_URL"]
    migrate(dsn)
    cfg = market.CHAINS[CHAIN]
    # primary first, then the other ranked providers (the verifier stays last so the second-provider check keeps its independence)
    order = [sel["primary"]] + [n for n in sel.get("ranked", []) if n not in (sel["primary"], sel.get("verifier"))] + ([sel["verifier"]] if sel.get("verifier") else [])
    urls = {n: url_for(cfg_p, CHAIN, n) for n in order}
    prim_url = urls[sel["primary"]]
    prim = FailoverSource([JsonRpcSource(urls[n], timeout=30, retries=6, backoff=1.0) for n in order], labels=order)
    ver = JsonRpcSource(url_for(cfg_p, CHAIN, sel["verifier"]), timeout=30, retries=3, backoff=1.0) if sel.get("verifier") else None
    rng_primary = sel.get("ranges", {}).get(sel["primary"], 1)
    batch = max(1, min(50, rng_primary))
    rep["primary"], rep["verifier"], rep["getlogs_range"] = sel["primary"], sel.get("verifier"), rng_primary
    rep["failover"] = {"chain": order[:-1] if sel.get("verifier") else order, "switches": prim.switches}  # same list object: stays current
    head = prim.head()
    last = head - CONF - 3
    start = last - (DISC + WATCH) + 1
    rep["window"] = {"head": head, "discovery": [start, start + DISC - 1], "watch": [start + DISC, last]}

    d1 = step(rep, "ingest_discovery", lambda: ingest(prim, dsn, DLABEL, start_block=start, confirmations=CONF, batch=batch,
                                                      max_blocks=DISC, topics0=pipeline.SWAP_TOPICS))
    if d1 is None:
        return finish(1)
    rep["discovery_ingest"] = {k: getattr(d1, k) for k in ("blocks", "logs", "decoded", "decode_errors", "reorgs", "next_block")} | {"notes": d1.notes[:5]}
    disc = step(rep, "discover_pools", lambda: pipeline.discover_pools(dsn, prim, LABEL, cfg, discovery_chain=DLABEL, top_k=TOP_K, candidates=CANDIDATES))
    if disc is None:
        return finish(1)
    rep["discovery"] = disc | {"rejected_unverified": len(disc["rejected_unverified"]), "constants": {a[:10]: v["ok"] for a, v in disc["constants"].items()}}
    pools = sorted(pipeline.watch_list(dsn, LABEL))
    w1 = step(rep, "ingest_watch", lambda: ingest(prim, dsn, LABEL, start_block=start + DISC, confirmations=CONF, batch=batch,
                                                  max_blocks=WATCH, topics0=pipeline.SWAP_TOPICS, addresses=pools))
    if w1 is None:
        return finish(1)
    rep["watch_ingest"] = {k: getattr(w1, k) for k in ("blocks", "logs", "decoded", "decode_errors", "reorgs", "next_block")} | {"notes": w1.notes[:5]}

    # a fresh tail: the balance-state check needs trades whose blocks the node still serves state for. The run itself takes a long time,
    # so the blocks that were "recent" when it started are not any more; extend the window up to the CURRENT head right before that check.
    w2 = step(rep, "ingest_fresh_tail", lambda: ingest(prim, dsn, LABEL, confirmations=CONF, batch=batch, max_blocks=FRESH_TAIL,
                                                       topics0=pipeline.SWAP_TOPICS, addresses=pools))
    if w2 is not None:
        rep["watch_ingest"]["fresh_tail"] = {"blocks": w2.blocks, "logs": w2.logs, "next_block": w2.next_block}
        rep["window"]["watch"][1] = w2.next_block - 1
        last = w2.next_block - 1

    # ETH price vs Chainlink NOW, while the node still serves state for these blocks
    conn = psycopg.connect(dsn, row_factory=dict_row)
    pool_objs = pipeline.watch_list(dsn, LABEL)
    dec = {r["address"]: r["decimals"] for r in conn.execute("SELECT address, decimals FROM chain_tokens WHERE chain=%s", (LABEL,))}
    for t, (_, dd) in cfg["expected"].items():
        dec.setdefault(t, dd)
    swaps_all = [s for s in pipeline.load_swaps(conn, LABEL) if s["pool"] in pool_objs]
    series, dropped = pipeline.robust_eth_series(pipeline.eth_points(cfg, dec, pool_objs, swaps_all))
    conn.close()
    val = market.Valuation(cfg, dec, series)
    rep["eth_series"] = {"points": len(series.pts), "outliers_dropped": dropped,
                         "min": float(min(p[1] for p in series.pts)) if series.pts else None, "max": float(max(p[1] for p in series.pts)) if series.pts else None}
    rep["chainlink"] = step(rep, "chainlink_check", lambda: chainlink_check(prim, cfg, series, prim.head())) or {"status": "error"}

    mk = lambda: FailoverSource([JsonRpcSource(urls[n], timeout=30, retries=6, backoff=1.0) for n in order], labels=order)  # noqa: E731
    # tail of the window first: the balance-state check only works while the node still serves state for those blocks
    tail = step(rep, "collect_tail_receipts", lambda: pipeline.collect_txs(dsn, mk, LABEL, workers=WORKERS, since_block=last - 60))
    if tail is not None and step(rep, "derive_tail", lambda: pipeline.derive_trades(dsn, LABEL, cfg)) is not None:
        rep["state_check"] = step(rep, "state_check", lambda: state_check(prim, dsn, LABEL)) or {"status": "error"}
    col = step(rep, "collect_receipts", lambda: pipeline.collect_txs(dsn, mk, LABEL, workers=WORKERS, limit=RECEIPT_LIMIT))
    if col is None:
        return finish(1)
    rep["receipts"] = {"stored": col.txs + (tail.txs if tail else 0), "transfers": col.transfers, "errors": col.receipt_errors + (tail.receipt_errors if tail else 0), "inconsistent_with_getlogs": col.inconsistent + (tail.inconsistent if tail else 0),
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
    rep["cross_pool_prices"] = step(rep, "cross_pool_prices", lambda: cross_pool_prices(swaps_all, pool_objs, val))
    rep["volume_coverage"] = step(rep, "volume_coverage", lambda: volume_coverage(dsn, LABEL, swaps_all, pool_objs, val))
    rep["unattributed_beneficiaries"] = step(rep, "unattributed_beneficiaries", lambda: unattributed_beneficiaries(prim, dsn, LABEL))
    rep.setdefault("state_check", {"status": "error: tail stage did not run"})
    rep["tx_targets"] = step(rep, "tx_targets", lambda: to_summary(dsn, LABEL))
    rep["wallets"] = step(rep, "wallet_summary", lambda: wallet_summary(dsn, LABEL))

    h = rep["headline"]
    h["window blocks (discovery + watch)"] = f"{DISC} + {WATCH}"
    h["pools watched"] = len(pools)
    h["receipts stored / errors / inconsistent"] = f'{rep["receipts"]["stored"]} / {rep["receipts"]["errors"]} / {rep["receipts"]["inconsistent_with_getlogs"]}'
    h["trades (confirmed / mismatch)"] = f"{der.trades} ({der.confirmed} / {der.mismatch})"
    h["share of swap txs that became a trade"] = rep["attribution"]["share_with_a_trade"]
    h["chainlink check"] = rep["chainlink"].get("status")
    h["second provider check"] = rep["second_provider"].get("passed")
    h["balance-state check"] = rep["state_check"].get("status")
    if rep.get("cross_pool_prices"):
        h["cross-pool price deviation (median / max %)"] = f'{rep["cross_pool_prices"].get("median_deviation_pct")} / {rep["cross_pool_prices"].get("max_deviation_pct")}'
    if rep.get("wallets"):
        h["wallets with a confirmed trade"] = rep["wallets"]["wallets_with_confirmed_trade"]
    failed = [name for name, s in rep["steps"].items() if not s["ok"]]
    integrity = {"steps_failed": failed, "receipts_inconsistent": rep["receipts"]["inconsistent_with_getlogs"],
                 "chainlink_failed": rep["chainlink"].get("status") == "fail",
                 "second_provider_failed": rep["second_provider"].get("passed") is False,
                 "state_check_failed": rep["state_check"].get("status") == "fail"}
    rep["integrity"] = integrity
    bad = bool(failed or rep["receipts"]["inconsistent_with_getlogs"] or integrity["chainlink_failed"] or integrity["second_provider_failed"] or integrity["state_check_failed"])
    h["integrity"] = "FAIL: " + json.dumps(integrity) if bad else "no integrity problem found by the checks above"
    return finish(1 if bad else 0)


if __name__ == "__main__":
    sys.exit(main())
