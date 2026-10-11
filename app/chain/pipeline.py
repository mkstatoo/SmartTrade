"""Wallet attribution on a verified watch-list of Uniswap pools.

Stages (each one is idempotent and tested against a synthetic world with hidden true prices; the real-chain run is a
separate step, see scripts/market_run.py):
  1. discover_pools  - rank pools seen swapping in a discovery window by swap count, VERIFY the top candidates through the DEX factory,
                       value their swaps in USD and keep the top-K by USD volume (+ WETH/stable reference pools for the ETH price);
  2. collect_txs     - for swaps of the watched pools fetch the transaction receipt (tx.from, status, gas, every ERC-20 Transfer of the
                       watched tokens) and cross-check it against the logs already stored from eth_getLogs;
  3. derive_trades   - wallet = tx.from. A trade exists only for a token whose net swap flow is PRICED from the swaps themselves
                       (stable = 1 USD, WETH from WETH/stable swaps) and is compared with the sender's own Transfer delta.
                       'confirmed' = the sender really received/paid that amount (+-tol); 'mismatch' = it did not.
                       Everything that cannot be attributed is stored in chain_trade_skips with a reason - never guessed.
  4. wallet_pnl      - feeds the confirmed trades of each wallet into app.pnl.compute_pnl (marks = last observed execution price).
Limits that stay true: the wallet is tx.from (relayers, bots, smart wallets and aggregators that pay out to someone else are
'no_sender_transfer'); only Uniswap V2/V3 pools; a short window means most sells have an unknown basis."""
from __future__ import annotations

import json
import statistics
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from app.chain import abi, market
from app.chain.rpc import RpcError

METHOD_VERSION = 1
SWAP_TOPICS = (abi.TOPIC_V2_SWAP, abi.TOPIC_V3_SWAP)
SWAP_KINDS = ("uniswap_v2_swap", "uniswap_v3_swap")
TOL = Decimal("0.02")
ETH_DEC = Decimal(10) ** 18


def _conn(dsn):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=True)


# ------------------------------------------------------------------------------------------------ loading
def load_swaps(conn, chain: str) -> list[dict]:
    rows = conn.execute(
        "SELECT l.address, l.block_number, l.block_hash, l.tx_hash, l.log_index, l.block_ts, d.kind, d.fields "
        "FROM chain_logs_canonical l JOIN chain_decoded d ON d.log_id = l.id AND d.decoder_version = %s "
        "WHERE l.chain = %s AND d.kind = ANY(%s) ORDER BY l.block_number, l.log_index",
        (abi.DECODER_VERSION, chain, list(SWAP_KINDS))).fetchall()
    out = []
    for r in rows:
        d0, d1 = market.normalise_swap(r["kind"], r["fields"])
        out.append({"pool": r["address"], "block": r["block_number"], "block_hash": r["block_hash"], "tx": r["tx_hash"],
                    "log_index": r["log_index"], "ts": r["block_ts"], "d0": d0, "d1": d1})
    return out


def robust_eth_series(points, *, window: int = 9, tol: Decimal = Decimal("0.03")):
    """points: [(block, log_index, price)]. A point that deviates more than `tol` from the median of its neighbours
    (window points around it) is dropped as an outlier. Returns (EthSeries, dropped_count)."""
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    keep, dropped = [], 0
    for i, (b, li, px) in enumerate(pts):
        lo, hi = max(0, i - window // 2), min(len(pts), i + window // 2 + 1)
        neigh = [p[2] for j, p in enumerate(pts[lo:hi], lo) if j != i]
        if len(neigh) >= 2:
            med = statistics.median(neigh)
            if med > 0 and abs(px - med) / med > tol:
                dropped += 1
                continue
        keep.append((b, li, px))
    s = market.EthSeries()
    for b, li, px in keep:
        s.add(b, li, px)
    return s.finalize(), dropped


def eth_points(cfg, decimals, pools: dict, swaps, min_weth: Decimal = Decimal("0.05")):
    out = []
    for s in swaps:
        p = pools.get(s["pool"])
        if p is None:
            continue
        pair = {p.token0: s["d0"], p.token1: s["d1"]}
        if cfg["weth"] in pair and abs(pair[cfg["weth"]]) < min_weth * ETH_DEC:
            continue                                           # dust swaps carry rounding noise, not a price
        px = market.eth_price_from_swap(cfg, decimals, p, s["d0"], s["d1"])
        if px is not None:
            out.append((s["block"], s["log_index"], px))
    return out


# ------------------------------------------------------------------------------------------------ 1. discovery
def discover_pools(dsn, rpc, chain: str, cfg: dict, *, discovery_chain: str, top_k: int = 30, candidates: int | None = None,
                   reference_pools: int = 3) -> dict:
    """Needs swap logs of ALL pools in `discovery_chain` (ingested with topics0=SWAP_TOPICS and no address filter)."""
    consts = market.check_constants(rpc, cfg)
    bad = {a: v for a, v in consts.items() if not v["ok"]}
    if bad:
        raise market.MarketError(f"reference token constants do not match the chain: {bad}")
    conn = _conn(dsn)
    try:
        swaps = load_swaps(conn, discovery_chain)
        counts = Counter(s["pool"] for s in swaps)
        cand = [p for p, _ in counts.most_common(candidates or 4 * top_k)]
        verified, rejected = {}, []
        for p in cand:
            v = market.verify_pool(rpc, cfg, p)
            if v is None:
                rejected.append(p)
            else:
                verified[p] = v
        decimals, symbols, dropped_tokens = {}, {}, []
        for t in sorted({t for v in verified.values() for t in (v.token0, v.token1)}):
            try:
                m = market.token_meta(rpc, t)
            except (market.MarketError, RpcError):
                dropped_tokens.append(t)
                continue
            decimals[t], symbols[t] = m["decimals"], m["symbol"]
        for t, (sym, dec) in cfg["expected"].items():
            decimals[t], symbols[t] = dec, sym
        verified = {p: v for p, v in verified.items() if v.token0 in decimals and v.token1 in decimals}
        series, dropped_pts = robust_eth_series(eth_points(cfg, decimals, verified, swaps))
        val = market.Valuation(cfg, decimals, series)
        vol, unpriced, kinds = defaultdict(Decimal), Counter(), {}
        for s in swaps:
            p = verified.get(s["pool"])
            if p is None:
                continue
            r = val.priced_swap(p, s["d0"], s["d1"], s["block"], s["log_index"])
            if isinstance(r, dict):
                vol[p.pool] += r["usd"]
                kinds[p.pool] = "base"
            elif r == "both_quote":
                kinds[p.pool] = "quote_pair"
                stable = next((t for t in (p.token0, p.token1) if t in cfg["stables"]), None)
                if stable is not None:
                    amt = s["d0"] if p.token0 == stable else s["d1"]
                    vol[p.pool] += market.D(abs(amt)) / Decimal(10) ** decimals[stable]
            else:
                unpriced[r] += 1
        ranked = sorted((p for p in verified if kinds.get(p) == "base"), key=lambda p: -vol[p])[:top_k]
        refs = sorted((p for p in verified if kinds.get(p) == "quote_pair"
                       and cfg["weth"] in (verified[p].token0, verified[p].token1)
                       and any(t in cfg["stables"] for t in (verified[p].token0, verified[p].token1))),
                      key=lambda p: -vol[p])[:reference_pools]
        chosen = {p: "watch" for p in ranked} | {p: "reference" for p in refs}
        lo = min((s["block"] for s in swaps), default=None)
        hi = max((s["block"] for s in swaps), default=None)
        with conn.transaction():
            for t, sym in symbols.items():
                if any(t in (verified[p].token0, verified[p].token1) for p in chosen):
                    conn.execute("INSERT INTO chain_tokens(chain, address, symbol, decimals) VALUES (%s,%s,%s,%s) "
                                 "ON CONFLICT (chain, address) DO UPDATE SET symbol=EXCLUDED.symbol, decimals=EXCLUDED.decimals, verified_at=now()",
                                 (chain, t, sym, decimals[t]))
            for p, role in chosen.items():
                v = verified[p]
                info = {"role": role, "swaps": counts[p], "usd_volume": str(vol[p].quantize(Decimal("0.01"))),
                        "window": [lo, hi], "discovery_chain": discovery_chain}
                conn.execute("INSERT INTO chain_pools(chain, pool, kind, factory, token0, token1, fee, discovery) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
                             "ON CONFLICT (chain, pool) DO UPDATE SET discovery=EXCLUDED.discovery, verified_at=now()",
                             (chain, p, v.kind, v.factory, v.token0, v.token1, v.fee, json.dumps(info)))
        return {"swaps_seen": len(swaps), "pools_seen": len(counts), "candidates": len(cand), "verified": len(verified),
                "rejected_unverified": rejected, "dropped_tokens": dropped_tokens, "unpriced_swaps": dict(unpriced),
                "eth_points": len(series.pts), "eth_outliers_dropped": dropped_pts, "constants": consts,
                "pools": [{"pool": p, "role": r, "kind": verified[p].kind, "fee": verified[p].fee,
                           "pair": f"{symbols[verified[p].token0]}/{symbols[verified[p].token1]}",
                           "swaps": counts[p], "usd_volume": float(vol[p])} for p, r in chosen.items()]}
    finally:
        conn.close()


def watch_list(dsn, chain: str) -> dict:
    conn = _conn(dsn)
    try:
        rows = conn.execute("SELECT pool, kind, factory, token0, token1, fee, discovery FROM chain_pools WHERE chain=%s", (chain,)).fetchall()
        return {r["pool"]: market.Pool(r["pool"], r["kind"], r["factory"], r["token0"], r["token1"], r["fee"]) for r in rows}
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ 2. receipts
@dataclass
class CollectResult:
    chain: str
    txs: int = 0
    transfers: int = 0
    already: int = 0
    receipt_errors: int = 0
    inconsistent: int = 0
    decode_errors: int = 0
    notes: list = field(default_factory=list)


def collect_txs(dsn, rpc_factory, chain: str, *, workers: int = 4, limit: int | None = None) -> CollectResult:
    res = CollectResult(chain)
    conn = _conn(dsn)
    try:
        pools = conn.execute("SELECT pool, token0, token1 FROM chain_pools WHERE chain=%s", (chain,)).fetchall()
        if not pools:
            raise market.MarketError("no watch-list: run discover_pools first")
        pool_set = {r["pool"] for r in pools}
        tokens = {r["token0"] for r in pools} | {r["token1"] for r in pools}
        swap_logs = conn.execute(
            "SELECT l.tx_hash, l.block_number, l.block_hash, l.log_index, l.address, l.data FROM chain_logs_canonical l "
            "JOIN chain_decoded d ON d.log_id = l.id AND d.decoder_version=%s WHERE l.chain=%s AND d.kind = ANY(%s) AND l.address = ANY(%s)",
            (abi.DECODER_VERSION, chain, list(SWAP_KINDS), list(pool_set))).fetchall()
        by_tx = defaultdict(list)
        for r in swap_logs:
            by_tx[(r["tx_hash"], r["block_hash"])].append(r)
        have = {(r["tx_hash"], r["block_hash"]) for r in conn.execute("SELECT tx_hash, block_hash FROM chain_txs WHERE chain=%s", (chain,))}
        todo = sorted(k for k in by_tx if k not in have)
        res.already = len(by_tx) - len(todo)
        if limit is not None:
            todo = todo[:limit]
        local = threading.local()

        def fetch(key):
            src = getattr(local, "src", None)
            if src is None:
                src = local.src = rpc_factory()
            try:
                return key, src.receipt(key[0]), None, src.source
            except RpcError as exc:
                return key, None, str(exc)[:100], None

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for key, rc, err, source in ex.map(fetch, todo):
                if rc is None:
                    res.receipt_errors += 1
                    if len(res.notes) < 5:
                        res.notes.append(f"receipt error: {err}")
                    continue
                tx_hash, block_hash = key
                stored = {(r["log_index"], r["address"], r["data"]) for r in by_tx[key]}
                got = {(l["log_index"], l["address"], l["data"]) for l in rc["logs"]}
                if rc["block_hash"] != block_hash or not stored <= got:
                    res.inconsistent += 1
                    if len(res.notes) < 5:
                        res.notes.append(f"receipt of {tx_hash[:12]} disagrees with stored logs")
                    continue
                with conn.transaction():
                    conn.execute("INSERT INTO chain_txs(chain, tx_hash, block_hash, block_number, from_addr, to_addr, status, gas_used, effective_gas_price, source) "
                                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                 (chain, tx_hash, block_hash, rc["block_number"], rc["from"], rc.get("to"), rc["status"], rc["gas_used"],
                                  rc["effective_gas_price"], source))
                    for l in rc["logs"]:
                        if l["address"] not in tokens or not l["topics"] or l["topics"][0] != abi.TOPIC_ERC20_TRANSFER:
                            continue
                        try:
                            d = abi.decode(l)
                        except abi.DecodeError:
                            res.decode_errors += 1
                            continue
                        if d is None:
                            continue
                        f = d[1]
                        conn.execute("INSERT INTO chain_transfers(chain, block_hash, tx_hash, log_index, token, from_addr, to_addr, amount) "
                                     "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                     (chain, block_hash, tx_hash, l["log_index"], l["address"], f["from"], f["to"], int(f["amount"])))
                        res.transfers += 1
                res.txs += 1
        return res
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ 3. trades
@dataclass
class DeriveResult:
    chain: str
    trades: int = 0
    confirmed: int = 0
    mismatch: int = 0
    skips: Counter = field(default_factory=Counter)
    txs: int = 0
    no_receipt: int = 0
    eth_points: int = 0
    eth_outliers_dropped: int = 0


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def derive_trades(dsn, chain: str, cfg: dict, *, method_version: int = METHOD_VERSION, tol: Decimal = TOL) -> DeriveResult:
    res = DeriveResult(chain)
    conn = _conn(dsn)
    try:
        pools = watch_list(dsn, chain)
        dec = {r["address"]: r["decimals"] for r in conn.execute("SELECT address, decimals FROM chain_tokens WHERE chain=%s", (chain,))}
        for t, (_, d) in cfg["expected"].items():
            dec.setdefault(t, d)
        swaps = [s for s in load_swaps(conn, chain) if s["pool"] in pools]
        txs = {(r["tx_hash"], r["block_hash"]): r for r in conn.execute(
            "SELECT x.* FROM chain_txs x JOIN chain_blocks b ON b.chain=x.chain AND b.block_hash=x.block_hash AND b.canonical WHERE x.chain=%s", (chain,))}
        xfers = defaultdict(list)
        for r in conn.execute("SELECT t.* FROM chain_transfers t JOIN chain_blocks b ON b.chain=t.chain AND b.block_hash=t.block_hash AND b.canonical WHERE t.chain=%s", (chain,)):
            xfers[(r["tx_hash"], r["block_hash"])].append(r)
        series, res.eth_outliers_dropped = robust_eth_series(eth_points(cfg, dec, pools, swaps))
        res.eth_points = len(series.pts)
        val = market.Valuation(cfg, dec, series)
        by_tx = defaultdict(list)
        for s in swaps:
            by_tx[(s["tx"], s["block_hash"])].append(s)
        trades, skips = [], []
        for key in sorted(by_tx, key=lambda k: (by_tx[k][0]["block"], by_tx[k][0]["log_index"])):
            tx = txs.get(key)
            if tx is None:
                res.no_receipt += 1
                continue
            res.txs += 1
            sw = by_tx[key]
            if tx["status"] != 1:
                skips.append((key, "tx_failed", {}))
                continue
            wallet = tx["from_addr"]
            net, usd_dir, qty_dir, ev, tx_skip = defaultdict(int), defaultdict(lambda: [Decimal(0), Decimal(0)]), defaultdict(lambda: [Decimal(0), Decimal(0)]), defaultdict(list), set()
            for s in sw:
                r = val.priced_swap(pools[s["pool"]], s["d0"], s["d1"], s["block"], s["log_index"])
                if not isinstance(r, dict):
                    tx_skip.add("quote_only" if r == "both_quote" else r)
                    continue
                t, i = r["token"], (0 if r["trader_buys"] else 1)
                net[t] += r["raw"] if r["trader_buys"] else -r["raw"]
                usd_dir[t][i] += r["usd"]
                qty_dir[t][i] += r["qty"]
                ev[t].append({"pool": s["pool"], "log_index": s["log_index"], "buys": r["trader_buys"], "qty": str(r["qty"]),
                              "usd": str(r["usd"]), "price_usd": str(r["price_usd"])})
            for reason in sorted(tx_skip):
                skips.append((key, reason, {}))
            ts = sw[0]["ts"]
            made = []
            for t in sorted(net):
                if net[t] == 0:
                    skips.append((key, "zero_net_flow", {"token": t}))
                    continue
                buys = net[t] > 0
                u, q = usd_dir[t][0 if buys else 1], qty_dir[t][0 if buys else 1]
                if q <= 0 or u <= 0:
                    skips.append((key, "degenerate_swap", {"token": t}))
                    continue
                px = u / q
                qty = Decimal(abs(net[t])) / Decimal(10) ** dec[t]
                delta = sum((x["amount"] if x["to_addr"] == wallet else 0) - (x["amount"] if x["from_addr"] == wallet else 0)
                            for x in xfers[key] if x["token"] == t)
                delta = int(delta)
                if delta == 0:
                    skips.append((key, "no_sender_transfer", {"token": t, "wallet": wallet}))
                    continue
                rel = abs(Decimal(delta - net[t])) / Decimal(abs(net[t]))
                conf = "confirmed" if (_sign(delta) == _sign(net[t]) and rel <= tol) else "mismatch"
                made.append({"token": t, "side": "buy" if buys else "sell", "qty": qty, "usd": qty * px, "price": px, "conf": conf,
                             "evidence": {"swaps": ev[t], "swap_net_raw": str(net[t]), "sender_delta_raw": str(delta),
                                          "rel_diff": str(rel.quantize(Decimal("0.000001"))), "tolerance": str(tol),
                                          "first_log_index": ev[t][0]["log_index"]}})
            if made:
                px_eth = series.at(sw[0]["block"], sw[0]["log_index"])
                gas = (Decimal(int(tx["gas_used"])) * Decimal(int(tx["effective_gas_price"])) / ETH_DEC * px_eth) if px_eth else Decimal(0)
                for i, m in enumerate(made):
                    m["gas_usd"] = gas if i == 0 else Decimal(0)
                    m["evidence"]["gas_priced"] = bool(px_eth)
                    trades.append((key, sw[0]["block"], ts, wallet, m))
        with conn.transaction():
            conn.execute("DELETE FROM chain_trades t USING chain_blocks b WHERE b.chain=t.chain AND b.block_hash=t.block_hash AND b.canonical "
                         "AND t.chain=%s AND t.method_version=%s", (chain, method_version))
            conn.execute("DELETE FROM chain_trade_skips t USING chain_blocks b WHERE b.chain=t.chain AND b.block_hash=t.block_hash AND b.canonical "
                         "AND t.chain=%s AND t.method_version=%s", (chain, method_version))
            for key, block, ts, wallet, m in trades:
                conn.execute(
                    "INSERT INTO chain_trades(chain, block_hash, block_number, tx_hash, ts, wallet, token, side, qty, usd, price_usd, gas_usd, confidence, evidence, method_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                    (chain, key[1], block, key[0], ts, wallet, m["token"], m["side"], m["qty"], m["usd"], m["price"], m["gas_usd"],
                     m["conf"], json.dumps(m["evidence"]), method_version))
                res.trades += 1
                res.confirmed += m["conf"] == "confirmed"
                res.mismatch += m["conf"] == "mismatch"
            for key, reason, detail in skips:
                conn.execute("INSERT INTO chain_trade_skips(chain, block_hash, tx_hash, reason, method_version, detail) VALUES (%s,%s,%s,%s,%s,%s::jsonb) "
                             "ON CONFLICT DO NOTHING", (chain, key[1], key[0], reason, method_version, json.dumps(detail)))
                res.skips[reason] += 1
        return res
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ 4. PnL
def wallet_pnl(dsn, chain: str, *, method_version: int = METHOD_VERSION, method: str = "fifo") -> dict:
    """{wallet: compute_pnl(...)} from CONFIRMED trades only. Marks: last observed execution price per token on this chain."""
    from app.ids import token_key
    from app.pnl import compute_pnl
    conn = _conn(dsn)
    try:
        rows = conn.execute("SELECT * FROM chain_trades_canonical WHERE chain=%s AND method_version=%s AND confidence='confirmed' "
                            "ORDER BY block_number, id", (chain, method_version)).fetchall()
    finally:
        conn.close()
    marks, ledgers = {}, defaultdict(list)
    for r in rows:
        marks[token_key(chain, r["token"])] = r["price_usd"]
        ledgers[r["wallet"]].append({"kind": r["side"], "ts": r["ts"], "qty": r["qty"], "usd": r["usd"], "fee_usd": r["gas_usd"],
                                     "token": r["token"], "chain": chain, "tx_hash": r["tx_hash"],
                                     "log_index": r["evidence"]["first_log_index"], "block_number": r["block_number"]})
    return {w: compute_pnl(e, method=method, marks=marks) for w, e in ledgers.items()}
