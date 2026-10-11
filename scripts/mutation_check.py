#!/usr/bin/env python3
"""Deliberate-bug check: apply one small mutation to the source, run the relevant tests, require them to FAIL, restore.
A mutation the tests do not notice means a missing test.   TEST_DATABASE_URL must be set (PostgreSQL 16).
    python scripts/mutation_check.py [-k substring]"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = [  # (name, file, old, new, tests)
    ("auth removed from /paper/sweep", "app/main.py", "    @app.post(\"/paper/sweep\", dependencies=secured)", "    @app.post(\"/paper/sweep\")", ["tests/test_security_config.py"]),
    ("auth throttle never records failures", "app/security.py", "            q.append(t)\n", "            pass\n", ["tests/test_security_config.py"]),
    ("body limit disabled", "app/main.py", "    app.add_middleware(BodyLimitMiddleware,", "    (lambda *a, **k: None)(BodyLimitMiddleware,", ["tests/test_security_config.py"]),
    ("read-only DB handler removed", "app/main.py", "@app.exception_handler(psycopg.errors.ReadOnlySqlTransaction)", "@app.exception_handler(KeyError)", ["tests/test_db_failures.py"]),
    ("sweep exit not labelled stale", "app/paper.py", 'price_basis="stale_last_close"', 'price_basis="bar"', ["tests/test_sweeper.py"]),
    ("FIFO consumes newest lot first", "app/pnl.py", "lq, lc = self.lots[0]", "lq, lc = self.lots[-1]", ["tests/test_pnl.py"]),
    ("walk-forward: purge disabled", "app/walkforward.py", "e.ts + reach <= end or e.side not in BUY_SIDES", "True", ["tests/test_walkforward.py"]),
    ("walk-forward: bars not clipped", "app/walkforward.py", "prices = [p for p in req.prices if end is None or p.ts <= end]", "prices = list(req.prices)", ["tests/test_walkforward.py"]),
    ("ingest: reorg detection off", "app/chain/ingest.py", "    if prev <= head and source.block(prev)[\"hash\"] == _canonical_hash(conn, chain, prev):\n        return next_block", "    if True:\n        return next_block", ["tests/test_chain_ingest.py"]),
    ("ingest: confirmations ignored", "app/chain/ingest.py", "safe = head - confirmations", "safe = head", ["tests/test_chain_ingest.py"]),
    ("ingest: logs not checked against headers", "app/chain/ingest.py", 'if h is None or h["hash"] != l["block_hash"]:', "if h is None:", ["tests/test_chain_ingest.py"]),
    ("ingest: cursor not advanced", "app/chain/ingest.py", 'conn.execute("UPDATE chain_cursor SET next_block=%s, updated_at=now() WHERE chain=%s", (hi + 1, chain))', "pass", ["tests/test_chain_ingest.py"]),
    ("schema: log identity not unique (fresh != migrated)", "data/schema.sql", "CONSTRAINT uq_chain_logs_identity UNIQUE (chain, block_hash, tx_hash, log_index)", "CONSTRAINT uq_chain_logs_identity UNIQUE (chain, block_hash, tx_hash)", ["tests/test_postgres.py"]),
    ("market: pool accepted without factory registry check", "app/chain/market.py", "if gp is not None and dec_address(gp) == pool:\n            return Pool(pool, \"uniswap_v3\"", "if gp is not None:\n            return Pool(pool, \"uniswap_v3\"", ["tests/test_market.py", "tests/test_pipeline.py"]),
    ("market: V3 swap sign flipped", "app/chain/market.py", "return int(fields[\"amount0\"]), int(fields[\"amount1\"])", "return -int(fields[\"amount0\"]), -int(fields[\"amount1\"])", ["tests/test_market.py"]),
    ("pipeline: wallet is not tx.from", "app/chain/pipeline.py", 'wallet = tx["from_addr"]', 'wallet = pools[sw[0]["pool"]].token0', ["tests/test_pipeline.py"]),
    ("pipeline: sender-delta check skipped", "app/chain/pipeline.py", 'conf = "confirmed" if (_sign(delta) == _sign(net[t]) and rel <= tol) else "mismatch"', 'conf = "confirmed"', ["tests/test_pipeline.py"]),
    ("pipeline: zero sender delta attributed anyway", "app/chain/pipeline.py", "                if delta == 0:\n", "                if False:\n", ["tests/test_pipeline.py"]),
    ("pipeline: ETH outliers kept", "app/chain/pipeline.py", "if med > 0 and abs(px - med) / med > tol:", "if False:", ["tests/test_pipeline.py"]),
    ("pipeline: receipt not cross-checked with getLogs", "app/chain/pipeline.py", "if rc[\"block_hash\"] != block_hash or not stored <= got:", "if False:", ["tests/test_pipeline.py"]),
    ("pipeline: gas attached to every trade", "app/chain/pipeline.py", "m[\"gas_usd\"] = gas if i == 0 else Decimal(0)", "m[\"gas_usd\"] = gas", ["tests/test_pipeline.py"]),
    ("pipeline: mismatch trades enter PnL", "app/chain/pipeline.py", "AND confidence='confirmed' \"", "\"", ["tests/test_pipeline.py"]),
    ("decoder: V3 tick unsigned", "app/chain/abi.py", '"tick": _int(data, 4, 24)', '"tick": _uint(data, 4, 24)', ["tests/test_chain_abi.py"]),
]


def run(name, f, old, new, tests):
    p = ROOT / f
    src = p.read_text()
    if src.count(old) < 1:
        return "NOT-APPLICABLE (pattern missing)"
    p.write_text(src.replace(old, new, 1))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests], cwd=ROOT,
                           capture_output=True, text=True, timeout=500)
    finally:
        p.write_text(src)
    if not r.returncode:
        return "SURVIVED  <-- missing test"
    failed = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
    if not failed:                                        # collection/import error is not a detection
        return "ERROR (mutation broke the import, not a real detection)"
    return "DETECTED by " + failed[0][7:].split(" - ")[0].split("::")[-1]


if __name__ == "__main__":
    flt = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else ""
    bad = 0
    for m in M:
        if flt in m[0]:
            t0 = time.time()
            res = run(*m)
            bad += not res.startswith("DETECTED")
            print(f"{m[0]:52s} {res}  ({time.time() - t0:.0f}s)", flush=True)
    sys.exit(1 if bad else 0)
