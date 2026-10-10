"""Raw on-chain log ingestion into PostgreSQL with provenance, confirmations, resumable cursor and reorg handling.

Guarantees (each covered by tests/test_chain_ingest.py against a scripted fake chain; NOT yet exercised on a real chain):
  * every stored log carries chain, block_hash, block_number, tx_hash, log_index and the RPC source label;
  * only blocks at least `confirmations` deep are ingested; the cursor moves in the same transaction as the data;
  * block headers form a parent-hash chain; a mismatch with what is stored triggers a reorg walk-back: the orphaned
    blocks are flagged canonical=false (kept for audit), a chain_reorgs row is written and ingestion restarts after the fork;
  * logs returned by the node must belong to the headers fetched for the same batch (else the batch is refetched);
  * one ingester per chain at a time (advisory lock); inserts are idempotent;
  * a log that fails decoding is recorded in chain_decode_errors, never dropped and never guessed.
Not done: attributing swaps to wallets and pricing them in USD (needs tx.from, token metadata and a price source)."""
from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field

from app.chain import abi
from app.chain.rpc import RpcError

CHAIN_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class IngestError(RuntimeError):
    pass


class IngestBusy(IngestError):
    pass


class ReorgTooDeep(IngestError):
    pass


@dataclass
class IngestResult:
    chain: str
    blocks: int = 0
    logs: int = 0
    decoded: int = 0
    decode_errors: int = 0
    reorgs: int = 0
    next_block: int = 0
    head: int = 0
    batches: int = 0
    notes: list = field(default_factory=list)


def _lock_key(chain: str) -> int:
    return struct.unpack(">q", hashlib.sha256(b"chain-ingest:" + chain.encode()).digest()[:8])[0]


def _looks_like_range_limit(exc: RpcError) -> bool:
    return exc.code is not None          # node-level refusal (range/size/result-count limits use JSON-RPC error codes)


def ingest(source, dsn: str, chain: str, *, start_block: int | None = None, confirmations: int = 12,
           batch: int = 500, max_reorg_depth: int = 64, max_blocks: int | None = None,
           topics0=abi.WATCHED_TOPICS, addresses=None, refetch_attempts: int = 3) -> IngestResult:
    import psycopg
    from psycopg.rows import dict_row
    if not CHAIN_RE.match(chain):
        raise ValueError("chain must match [a-z0-9_-]{1,32}")
    if confirmations < 0 or batch < 1 or max_reorg_depth < 1:
        raise ValueError("confirmations>=0, batch>=1, max_reorg_depth>=1 required")
    res = IngestResult(chain)
    conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
    try:
        if not conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (_lock_key(chain),)).fetchone()["ok"]:
            raise IngestBusy(f"another ingester holds the lock for {chain}")
        try:
            _run(conn, source, chain, res, start_block, confirmations, batch, max_reorg_depth, max_blocks,
                 list(topics0), addresses, refetch_attempts)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_lock_key(chain),))
    finally:
        conn.close()
    return res


def _canonical_hash(conn, chain, number):
    r = conn.execute("SELECT block_hash FROM chain_blocks WHERE chain=%s AND block_number=%s AND canonical",
                     (chain, number)).fetchone()
    return r["block_hash"] if r else None


def _reorg_check(conn, source, chain, next_block, max_depth, res, head):
    """If the stored canonical block next_block-1 is no longer on the node's chain, roll the cursor back to the fork.
    A node whose head is below a block we stored is treated the same way: the node is the source of truth."""
    prev = next_block - 1
    if prev < 0 or _canonical_hash(conn, chain, prev) is None:
        return next_block
    if prev <= head and source.block(prev)["hash"] == _canonical_hash(conn, chain, prev):
        return next_block
    fork, depth = prev, 0
    while True:
        depth += 1
        if depth > max_depth:
            raise ReorgTooDeep(f"reorg deeper than {max_depth} blocks below {prev}; refusing to rewrite history automatically")
        fork -= 1
        stored = _canonical_hash(conn, chain, fork)
        if stored is None:                       # fell off what we have: nothing older to compare
            break
        if fork <= head and source.block(fork)["hash"] == stored:
            break
    first_bad = fork + 1
    with conn.transaction():
        n = conn.execute("UPDATE chain_blocks SET canonical=false WHERE chain=%s AND block_number>=%s AND canonical",
                         (chain, first_bad)).rowcount
        conn.execute("INSERT INTO chain_reorgs(chain, fork_block, depth, orphaned_blocks) VALUES (%s,%s,%s,%s)",
                     (chain, max(fork, 0), depth, n))
        conn.execute("UPDATE chain_cursor SET next_block=%s, updated_at=now() WHERE chain=%s", (first_bad, chain))
    res.reorgs += 1
    return first_bad


def _fetch_batch(source, lo, hi, topics0, addresses):
    headers = {}
    for n in range(lo, hi + 1):
        headers[n] = source.block(n)
    for n in range(lo + 1, hi + 1):
        if headers[n]["parent"] != headers[n - 1]["hash"]:
            return headers, None, "headers do not link (chain moved while fetching)"
    logs = source.logs(lo, hi, topics0, addresses)
    for l in logs:
        h = headers.get(l["block_number"])
        if h is None or h["hash"] != l["block_hash"]:
            return headers, None, "log belongs to a block other than the fetched header (reorg during fetch)"
    return headers, logs, None


def _run(conn, source, chain, res, start_block, confirmations, batch, max_depth, max_blocks, topics0, addresses, attempts):
    cur = conn.execute("SELECT next_block FROM chain_cursor WHERE chain=%s", (chain,)).fetchone()
    if cur is None:
        if start_block is None:
            raise IngestError("first run for this chain needs an explicit start_block (no silent default)")
        if start_block < 0:
            raise ValueError("start_block must be >= 0")
        conn.execute("INSERT INTO chain_cursor(chain, next_block) VALUES (%s,%s) ON CONFLICT DO NOTHING", (chain, start_block))
        nxt = start_block
    else:
        nxt = cur["next_block"]
    head = source.head()
    res.head = head
    safe = head - confirmations
    size, done_blocks, mismatches = batch, 0, 0
    nxt = _reorg_check(conn, source, chain, nxt, max_depth, res, head)    # also when there is nothing new to fetch
    while nxt <= safe:
        if max_blocks is not None and done_blocks >= max_blocks:
            res.notes.append("stopped at max_blocks")
            break
        back = _reorg_check(conn, source, chain, nxt, max_depth, res, head)
        if back != nxt:
            nxt = back
            continue
        hi = min(nxt + size - 1, safe)
        if max_blocks is not None:
            hi = min(hi, nxt + (max_blocks - done_blocks) - 1)
        inconsistent = 0
        while True:
            try:
                headers, logs, why = _fetch_batch(source, nxt, hi, topics0, addresses)
            except RpcError as exc:
                if hi > nxt and _looks_like_range_limit(exc):
                    size = max(1, (hi - nxt + 1) // 2)
                    res.notes.append(f"batch halved to {size}: {exc}")
                    hi = nxt + size - 1
                    continue
                raise
            if logs is not None:
                break
            res.notes.append(why)
            inconsistent += 1
            if inconsistent >= attempts:
                raise IngestError(f"no consistent view of blocks {nxt}..{hi} after {attempts} attempts: {why}")
        # the first header must extend what we hold; otherwise the chain moved between reorg check and fetch
        if nxt > 0 and _canonical_hash(conn, chain, nxt - 1) not in (None, headers[nxt]["parent"]):
            res.notes.append("parent mismatch at batch start; re-checking for reorg")
            mismatches += 1
            if mismatches >= attempts:
                raise IngestError("node keeps returning headers that do not extend the stored chain")
            continue
        mismatches = 0
        _store(conn, chain, source.source, headers, logs, nxt, hi, res)
        done_blocks += hi - nxt + 1
        nxt = hi + 1
        res.batches += 1
    res.next_block = nxt


def _store(conn, chain, src, headers, logs, lo, hi, res):
    with conn.transaction():
        # a different block may hold a number we are about to take: demote it first (partial unique index)
        for n in range(lo, hi + 1):
            conn.execute("UPDATE chain_blocks SET canonical=false WHERE chain=%s AND block_number=%s AND canonical AND block_hash<>%s",
                         (chain, n, headers[n]["hash"]))
            conn.execute(
                "INSERT INTO chain_blocks(chain, block_hash, block_number, parent_hash, block_ts, canonical, source) "
                "VALUES (%s,%s,%s,%s,%s,true,%s) ON CONFLICT (chain, block_hash) DO UPDATE SET canonical=true",
                (chain, headers[n]["hash"], n, headers[n]["parent"], headers[n]["ts"], src))
        for l in logs:
            row = conn.execute(
                "INSERT INTO chain_logs(chain, block_hash, block_number, tx_hash, log_index, address, topic0, topics, data) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT ON CONSTRAINT uq_chain_logs_identity DO NOTHING RETURNING id",
                (chain, l["block_hash"], l["block_number"], l["tx_hash"], l["log_index"], l["address"],
                 l["topics"][0] if l["topics"] else "0x" + "0" * 64, l["topics"], l["data"])).fetchone()
            if row is None:
                continue
            res.logs += 1
            try:
                d = abi.decode(l)
            except abi.DecodeError as exc:
                conn.execute("INSERT INTO chain_decode_errors(log_id, decoder_version, error) VALUES (%s,%s,%s)",
                             (row["id"], abi.DECODER_VERSION, str(exc)[:300]))
                res.decode_errors += 1
                continue
            if d is not None:
                import json
                conn.execute("INSERT INTO chain_decoded(log_id, decoder_version, kind, fields) VALUES (%s,%s,%s,%s::jsonb)",
                             (row["id"], abi.DECODER_VERSION, d[0], json.dumps(d[1])))
                res.decoded += 1
        conn.execute("UPDATE chain_cursor SET next_block=%s, updated_at=now() WHERE chain=%s", (hi + 1, chain))
    res.blocks += hi - lo + 1
