#!/usr/bin/env python3
"""End-to-end REAL test: ingest recent blocks of a real chain through the PRIMARY provider into PostgreSQL, then check the
stored result against an INDEPENDENT second provider (block hashes, parent links, per-block log counts, tx hashes), rerun
for idempotency/resume, and report decode statistics. Needs reports/selection.json (from provider_probe.py) and DATABASE_URL.
Writes reports/live_verify.json and reports/live_verify.md. Exit code 1 if any check fails."""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.chain.abi import WATCHED_TOPICS  # noqa: E402
from app.chain.ingest import ingest  # noqa: E402
from app.chain.rpc import JsonRpcSource  # noqa: E402
from app.migrate import migrate  # noqa: E402

CONF, START_BACK, NBLOCKS = 12, int(os.getenv("LIVE_START_BACK", "300")), int(os.getenv("LIVE_BLOCKS", "150"))


def url_for(cfg, chain, name):
    if name.startswith("private-"):
        return os.environ[f"RPC_{chain.upper()}_{name.split('-')[1]}"]
    for p in cfg["chains"][chain]["providers"]:
        if p["name"] == name:
            return p["url"]
    raise KeyError(name)


def check_chain(chain, sel, cfg, dsn):
    rep = {"chain": chain, "checks": {}, "primary": sel["primary"], "verifier": sel["verifier"]}
    if not sel["primary"] or not sel["verifier"]:
        rep["skipped"] = "need two agreeing usable providers (primary + independent verifier)"
        return rep
    prim = JsonRpcSource(url_for(cfg, chain, sel["primary"]), timeout=30, retries=3, backoff=1.0)
    ver = JsonRpcSource(url_for(cfg, chain, sel["verifier"]), timeout=30, retries=3, backoff=1.0)
    start = prim.head() - START_BACK
    t0 = time.time()
    r1 = ingest(prim, dsn, chain, start_block=start, confirmations=CONF, batch=50, max_blocks=NBLOCKS)
    rep["ingest_run1"] = {k: getattr(r1, k) for k in ("blocks", "logs", "decoded", "decode_errors", "reorgs", "next_block", "head")} | {"seconds": round(time.time() - t0, 1), "notes": r1.notes[:5]}
    end = r1.next_block - 1
    rep["range"] = [start, end]
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        blocks = {r["block_number"]: r for r in c.execute("SELECT * FROM chain_blocks WHERE chain=%s AND canonical", (chain,))}
        logs = c.execute("SELECT block_number, block_hash, tx_hash, log_index FROM chain_logs_canonical WHERE chain=%s", (chain,)).fetchall()
        kinds = Counter(r["kind"] for r in c.execute("SELECT kind FROM chain_decoded d JOIN chain_logs l ON l.id=d.log_id WHERE l.chain=%s", (chain,)))
        errs = [r["error"] for r in c.execute("SELECT e.error FROM chain_decode_errors e JOIN chain_logs l ON l.id=e.log_id WHERE l.chain=%s LIMIT 10", (chain,))]
    rep["decoded_by_kind"], rep["decode_error_examples"] = dict(kinds), errs
    ok = rep["checks"]
    ok["blocks_contiguous"] = sorted(blocks) == list(range(start, end + 1))
    ok["stored_parent_chain_linked"] = all(blocks[n + 1]["parent_hash"] == blocks[n]["block_hash"] for n in range(start, end))
    bad_hash = [n for n in blocks if ver.block(n)["hash"] != blocks[n]["block_hash"]]
    ok["block_hashes_match_independent_provider"] = not bad_hash
    ver_logs = []
    for lo in range(start, end + 1, 50):
        ver_logs += ver.logs(lo, min(lo + 49, end), WATCHED_TOPICS)
    mine = Counter((l["block_number"], l["tx_hash"], l["log_index"]) for l in logs)
    theirs = Counter((l["block_number"], l["tx_hash"], l["log_index"]) for l in ver_logs)
    ok["logs_identical_to_independent_provider"] = mine == theirs
    rep["log_counts"] = {"stored": sum(mine.values()), "independent": sum(theirs.values()),
                         "only_stored": len(mine - theirs), "only_independent": len(theirs - mine)}
    r2 = ingest(prim, dsn, chain, confirmations=CONF, batch=50, max_blocks=20)          # resume from the cursor
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        dup = c.execute("SELECT count(*) AS n FROM (SELECT 1 FROM chain_logs WHERE chain=%s GROUP BY block_hash, tx_hash, log_index HAVING count(*)>1) x", (chain,)).fetchone()["n"]
        noncanon = c.execute("SELECT count(*) AS n FROM chain_blocks WHERE chain=%s AND NOT canonical", (chain,)).fetchone()["n"]
    rep["ingest_run2"] = {"blocks": r2.blocks, "logs": r2.logs, "reorgs": r2.reorgs, "next_block": r2.next_block}
    ok["resume_continues_without_duplicates"] = dup == 0 and r2.next_block > r1.next_block - 1
    rep["noncanonical_blocks"] = noncanon
    rep["passed"] = all(ok.values())
    return rep


def main():
    cfg = json.loads(Path(os.getenv("PROVIDERS_FILE", ROOT / "scripts" / "providers.json")).read_text())
    sel = json.loads((Path(os.getenv("REPORTS_DIR", ROOT / "reports")) / "selection.json").read_text())
    dsn = os.environ["DATABASE_URL"]
    migrate(dsn)
    reports = []
    for chain, s in sel.items():
        try:
            reports.append(check_chain(chain, s, cfg, dsn))
        except Exception as exc:  # noqa: BLE001
            reports.append({"chain": chain, "passed": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        print(json.dumps(reports[-1], default=str)[:600], flush=True)
    out = Path(os.getenv("REPORTS_DIR", ROOT / "reports"))
    (out / "live_verify.json").write_text(json.dumps({"at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "reports": reports}, indent=1, default=str))
    md = ["# Live verification (real chain data)", ""]
    for r in reports:
        md.append(f"## {r['chain']}: " + ("PASS" if r.get("passed") else ("SKIPPED" if r.get("skipped") else "FAIL")))
        md.append("```\n" + json.dumps(r, indent=1, default=str) + "\n```")
    (out / "live_verify.md").write_text("\n".join(md) + "\n")
    if all(r.get("skipped") for r in reports):
        print("INCONCLUSIVE: no chain could be verified (no two usable providers)", file=sys.stderr)
        return 2                                         # a run that verified nothing must not look green
    return 0 if all(r.get("passed") or r.get("skipped") for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
