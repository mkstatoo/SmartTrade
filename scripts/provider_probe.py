#!/usr/bin/env python3
"""Measure candidate JSON-RPC providers for log ingestion and pick the best per chain. Writes reports/probe.json,
reports/probe.md and reports/selection.json. Endpoint URLs from secrets are never written (only their label).

What is measured (nothing is assumed): correct chain id; latency p50/p95 of eth_blockNumber; burst tolerance (rate limits);
largest eth_getLogs block range accepted for the three watched topics; header parent-link consistency; how far back
blocks / logs can be read; and AGREEMENT with the other providers on block hashes and log counts of the same blocks."""
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.chain.abi import WATCHED_TOPICS  # noqa: E402
from app.chain.rpc import JsonRpcSource, RpcError  # noqa: E402

OUT = Path(os.getenv("REPORTS_DIR", ROOT / "reports"))
RANGES = [1, 10, 100, 500, 2000]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None


def timed(fn):
    t = time.time()
    try:
        return fn(), time.time() - t, None
    except Exception as exc:  # noqa: BLE001
        return None, time.time() - t, f"{type(exc).__name__}: {str(exc)[:120]}"


def candidates(cfg):
    for chain, c in cfg["chains"].items():
        for p in c["providers"]:
            yield chain, c["chain_id"], p["name"], p["url"]
        i = 1
        while os.getenv(f"RPC_{chain.upper()}_{i}"):
            yield chain, c["chain_id"], f"private-{i}", os.environ[f"RPC_{chain.upper()}_{i}"]
            i += 1


def probe(chain, chain_id, name, url):
    r = {"chain": chain, "provider": name, "ok": False, "errors": []}
    src = JsonRpcSource(url, timeout=20, retries=0)
    r["host"] = src.source if not name.startswith("private") else "(secret)"
    cid, _, err = timed(lambda: int(src._call("eth_chainId", []), 16))
    if err or cid != chain_id:
        r["errors"].append(err or f"wrong chain id {cid}")
        return r, src
    head, _, err = timed(src.head)
    if err:
        r["errors"].append(err)
        return r, src
    r["head"] = head
    lat = []
    for _ in range(10):
        _, dt, e = timed(src.head)
        if not e:
            lat.append(dt)
    r["latency_p50_ms"] = round(1000 * statistics.median(lat)) if lat else None
    r["latency_p95_ms"] = round(1000 * pct(lat, 0.95)) if lat else None
    burst = [timed(src.head)[2] for _ in range(30)]
    r["burst_30_errors"] = sum(1 for e in burst if e)
    base = head - 500
    hdr, _, err = timed(lambda: [src.block(base + i) for i in range(10)])
    r["headers_linked"] = bool(hdr) and all(hdr[i + 1]["parent"] == hdr[i]["hash"] for i in range(9))
    if err:
        r["errors"].append("headers: " + err)
    max_range, rng = 0, {}
    for n in RANGES:
        lg, dt, err = timed(lambda: src.logs(base, base + n - 1, WATCHED_TOPICS))
        rng[n] = {"ok": err is None, "seconds": round(dt, 2), "logs": None if err else len(lg), "error": err}
        if err is None:
            max_range = n
        else:
            break
    r["logs_by_range"], r["max_log_range_blocks"] = rng, max_range
    depth = {}
    for d in (10_000, 100_000, 1_000_000):
        _, _, err = timed(lambda: src.block(head - d))
        depth[d] = err is None
    r["block_depth_ok"] = depth
    r["ok"] = max_range >= 1 and r["headers_linked"]
    return r, src


def logs_chunked(src, lo, hi, step):
    out = []
    for a in range(lo, hi + 1, max(1, step)):
        out += src.logs(a, min(a + step - 1, hi), WATCHED_TOPICS)
    return out


def agreement(chain, results, srcs):
    """All usable providers must return the same block hashes and the same set of (block, tx, log index) for one window.
    The window is as wide as the most restrictive provider allows (never more than 20 blocks); each provider is asked in
    chunks it accepts."""
    ok = [r for r in results if r["chain"] == chain and r["ok"]]
    if len(ok) < 2:
        return
    span = max(1, min(20, min(r["max_log_range_blocks"] for r in ok)))
    span = max(span, 3) if all(r["max_log_range_blocks"] >= 1 for r in ok) else span
    ref = min(r["head"] for r in ok) - 100
    facts = {}
    for r in ok:
        s = srcs[(chain, r["provider"])]
        try:
            hashes = tuple(s.block(ref + i)["hash"] for i in range(span))
            lg = logs_chunked(s, ref, ref + span - 1, r["max_log_range_blocks"])
            facts[r["provider"]] = (hashes, frozenset((l["block_number"], l["tx_hash"], l["log_index"]) for l in lg))
        except RpcError as exc:
            r["errors"].append(f"agreement fetch: {exc}")
            facts[r["provider"]] = None
    from collections import Counter
    votes = Counter(v for v in facts.values() if v is not None)
    if not votes:
        return
    majority = votes.most_common(1)[0][0]
    for r in ok:
        f = facts[r["provider"]]
        r["agreement_block_window"] = [ref, ref + span - 1]
        r["agrees_with_majority"] = None if f is None else f == majority
        r["agreement_log_count"] = None if f is None else len(f[1])
    return


def score(r):
    if not r["ok"] or r.get("agrees_with_majority") is False:
        return -1
    if r.get("agrees_with_majority") is None and "agreement_block_window" in r:
        return -1                                          # could not be checked against the others: not trusted
    # keyed private endpoints first: public gateways pass a 30-request burst but rate-limit (HTTP 429) during sustained ingestion
    return (r["provider"].startswith("private-"), r["max_log_range_blocks"], -(r.get("burst_30_errors") or 0), -(r.get("latency_p95_ms") or 10**9))


def main():
    cfg = json.loads(Path(os.getenv("PROVIDERS_FILE", ROOT / "scripts" / "providers.json")).read_text())
    results, srcs = [], {}
    for chain, cid, name, url in candidates(cfg):
        r, s = probe(chain, cid, name, url)
        results.append(r)
        srcs[(chain, name)] = s
        print(f"{chain:9s} {name:14s} ok={r['ok']} range={r.get('max_log_range_blocks')} p95={r.get('latency_p95_ms')}ms errs={r['errors'][:1]}", flush=True)
    for chain in cfg["chains"]:
        agreement(chain, results, srcs)
    selection = {}
    for chain in cfg["chains"]:
        good = sorted([r for r in results if r["chain"] == chain and score(r) != -1], key=score, reverse=True)
        selection[chain] = {"ranked": [r["provider"] for r in good],
                            "primary": good[0]["provider"] if good else None,
                            "verifier": good[1]["provider"] if len(good) > 1 else None,
                            "ranges": {r["provider"]: r["max_log_range_blocks"] for r in good}}
    OUT.mkdir(exist_ok=True)
    (OUT / "probe.json").write_text(json.dumps({"at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "results": results}, indent=1))
    (OUT / "selection.json").write_text(json.dumps(selection, indent=1))
    lines = ["# Provider probe", "", f"UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}", "",
             "| chain | provider | usable | max getLogs range | p50 ms | p95 ms | burst errors /30 | depth 10k/100k/1M | agrees | first error |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        d = r.get("block_depth_ok") or {}
        lines.append(f"| {r['chain']} | {r['provider']} | {r['ok']} | {r.get('max_log_range_blocks')} | {r.get('latency_p50_ms')} | {r.get('latency_p95_ms')} | "
                     f"{r.get('burst_30_errors')} | {'/'.join('Y' if d.get(k) else 'N' for k in (10000, 100000, 1000000)) if d else '-'} | {r.get('agrees_with_majority')} | {(r['errors'] or [''])[0]} |")
    lines += ["", "## Selection", "```", json.dumps(selection, indent=1), "```"]
    (OUT / "probe.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(selection))
    return 0


if __name__ == "__main__":
    sys.exit(main())
