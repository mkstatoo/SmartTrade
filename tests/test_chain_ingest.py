import threading

import psycopg
import pytest
from psycopg.rows import dict_row

from app.chain.ingest import IngestBusy, IngestError, ReorgTooDeep, ingest
from app.chain.rpc import RpcError
from app.migrate import migrate
from tests.conftest import needs_pg
from tests.fake_chain import FakeChain, addr, transfer_log, v2_swap_log, v3_swap_log

pytestmark = needs_pg


@pytest.fixture
def db(pgdb):
    migrate(pgdb)
    return pgdb


def q(dsn, sql, *a):
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        return c.execute(sql, a).fetchall()


def logs_for(blocks):
    return {n: [transfer_log(addr(9), addr(1), addr(2), 100 + n), v2_swap_log(addr(5), addr(1), addr(2), n + 1, 0, 0, 3)] for n in blocks}


def test_provenance_fields_and_confirmations(db):
    ch = FakeChain(30, logs_at=logs_for([3, 10, 25]))
    r = ingest(ch, db, "eth", start_block=0, confirmations=12)
    assert r.next_block == 18 and r.blocks == 18          # head 29 - 12 = 17 is the last confirmed block
    rows = q(db, "SELECT * FROM chain_logs_canonical ORDER BY block_number, log_index")
    assert [x["block_number"] for x in rows] == [3, 3, 10, 10]                 # block 25 is not yet 12 deep
    for x in rows:
        b = ch.blocks[x["block_number"]]
        assert x["block_hash"] == b["hash"] and x["block_ts"] == b["ts"] and x["source"] == "fake://node"
        assert x["tx_hash"].startswith("0x") and len(x["tx_hash"]) == 66 and x["chain"] == "eth"
    assert q(db, "SELECT next_block FROM chain_cursor")[0]["next_block"] == 18


def test_decoded_rows_match_input_and_decode_errors_recorded(db):
    bad = {"address": addr(9), "topics": transfer_log(addr(9), addr(1), addr(2), 1)["topics"], "data": "0x" + "00" * 31}
    ch = FakeChain(20, logs_at={2: [transfer_log(addr(9), addr(1), addr(2), 777), v3_swap_log(addr(5), addr(1), addr(2), -5, 9, 1 << 90, 1 << 60, -42), bad]})
    r = ingest(ch, db, "eth", start_block=0, confirmations=0)
    assert (r.logs, r.decoded, r.decode_errors) == (3, 2, 1)
    dec = {x["kind"]: x["fields"] for x in q(db, "SELECT kind, fields FROM chain_decoded")}
    assert dec["erc20_transfer"]["amount"] == "777" and dec["uniswap_v3_swap"]["amount0"] == "-5" and dec["uniswap_v3_swap"]["tick"] == -42
    err = q(db, "SELECT error FROM chain_decode_errors")
    assert len(err) == 1 and "32 bytes" in err[0]["error"]
    assert q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"] == 3         # the bad log is still stored raw


def test_idempotent_rerun_and_resume(db):
    ch = FakeChain(40, logs_at=logs_for(range(0, 40, 4)))
    ingest(ch, db, "eth", start_block=0, confirmations=5, max_blocks=10)
    assert q(db, "SELECT next_block FROM chain_cursor")[0]["next_block"] == 10
    ingest(ch, db, "eth", confirmations=5)                       # resume: no start_block needed
    first = q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"]
    again = ingest(ch, db, "eth", confirmations=5)
    assert again.blocks == 0 and again.logs == 0
    assert q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"] == first
    assert q(db, "SELECT count(*) AS n FROM chain_blocks")[0]["n"] == 35


def test_first_run_requires_explicit_start(db):
    with pytest.raises(IngestError, match="start_block"):
        ingest(FakeChain(10), db, "eth", confirmations=0)
    assert q(db, "SELECT count(*) AS n FROM chain_cursor")[0]["n"] == 0


def test_resume_after_midway_failure_loses_nothing_and_duplicates_nothing(db):
    ch = FakeChain(60, logs_at=logs_for(range(60)))
    state = {"fail": True}

    def hook(c, name, args):
        if name == "logs" and args[0] >= 20 and state["fail"]:
            raise RpcError("boom")
    ch.hook = hook
    with pytest.raises(RpcError):
        ingest(ch, db, "eth", start_block=0, confirmations=0, batch=10)
    assert q(db, "SELECT next_block FROM chain_cursor")[0]["next_block"] == 20          # committed batches survive
    state["fail"] = False
    ingest(ch, db, "eth", confirmations=0, batch=10)
    rows = q(db, "SELECT block_number, log_index, count(*) AS n FROM chain_logs GROUP BY 1,2 HAVING count(*)>1")
    assert rows == []
    assert q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"] == 120


def test_batch_halves_on_range_limit_and_still_completes(db):
    ch = FakeChain(40, logs_at=logs_for(range(40)))
    ch.max_range = 3
    r = ingest(ch, db, "eth", start_block=0, confirmations=0, batch=64)
    assert q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"] == 80
    assert any("halved" in n for n in r.notes)
    assert max(hi - lo + 1 for name, (lo, hi) in [(c[0], c[1]) for c in ch.calls if c[0] == "logs"] if True) <= 64


def test_range_limit_at_single_block_is_an_error(db):
    ch = FakeChain(5); ch.max_range = 0
    with pytest.raises(RpcError):
        ingest(ch, db, "eth", start_block=0, confirmations=0)


def test_reorg_between_runs_marks_old_blocks_noncanonical(db):
    ch = FakeChain(40, logs_at=logs_for(range(40)))
    ingest(ch, db, "eth", start_block=0, confirmations=0)
    old = {n: ch.blocks[n]["hash"] for n in range(30, 40)}
    ch.reorg(29, 11, salt="b", logs_at={n: [transfer_log(addr(9), addr(7), addr(8), 5000 + n)] for n in range(30, 41)})
    r = ingest(ch, db, "eth", confirmations=0)
    assert r.reorgs == 1
    canon = {x["block_number"]: x["block_hash"] for x in q(db, "SELECT block_number, block_hash FROM chain_blocks WHERE canonical")}
    assert sorted(canon) == list(range(0, 41)) and all(canon[n] == ch.blocks[n]["hash"] for n in canon)
    orphans = q(db, "SELECT block_number, block_hash FROM chain_blocks WHERE NOT canonical")
    assert {x["block_hash"] for x in orphans} == set(old.values())               # kept, not deleted
    amounts = {x["fields"]["amount"] for x in q(db, "SELECT fields FROM chain_decoded d JOIN chain_logs_canonical l ON l.id=d.log_id WHERE kind='erc20_transfer' AND l.block_number>=30")}
    assert amounts == {str(5000 + n) for n in range(30, 41)}                     # canonical view carries only the new branch
    ro = q(db, "SELECT fork_block, depth, orphaned_blocks FROM chain_reorgs")[0]
    assert (ro["fork_block"], ro["orphaned_blocks"]) == (29, 10)


def test_reorg_back_to_original_branch_reuses_rows(db):
    ch = FakeChain(20, logs_at=logs_for(range(20)))
    ingest(ch, db, "eth", start_block=0, confirmations=0)
    snap = {n: dict(b) for n, b in ch.blocks.items()}
    ch.reorg(14, 6, salt="b")
    ingest(ch, db, "eth", confirmations=0)
    ch.blocks = {n: dict(b) for n, b in snap.items()}; ch.tip = 19                 # original branch wins again
    ingest(ch, db, "eth", confirmations=0)
    canon = q(db, "SELECT block_number, block_hash FROM chain_blocks WHERE canonical ORDER BY 1")
    assert [x["block_hash"] for x in canon] == [snap[n]["hash"] for n in range(20)]     # node head fell from 20 to 19
    assert q(db, "SELECT count(*) AS n FROM chain_blocks WHERE NOT canonical")[0]["n"] == 6    # exactly branch b blocks 15..20
    assert q(db, "SELECT count(*) AS n FROM chain_reorgs")[0]["n"] == 2


def test_reorg_during_fetch_is_refetched_not_stored_mixed(db):
    ch = FakeChain(30, logs_at=logs_for(range(30)))
    fired = {"n": 0}

    def hook(c, name, args):
        if name == "logs" and fired["n"] == 0:
            fired["n"] = 1
            c.reorg(9, 21, salt="z", logs_at=logs_for(range(10, 31)))      # chain changes after headers were read
    ch.hook = hook
    r = ingest(ch, db, "eth", start_block=0, confirmations=0, batch=30)
    assert any("reorg during fetch" in n for n in r.notes)
    mism = q(db, "SELECT count(*) AS n FROM chain_logs l JOIN chain_blocks b USING (chain, block_hash) WHERE b.canonical AND l.block_number<>b.block_number")
    assert mism[0]["n"] == 0
    canon = {x["block_number"]: x["block_hash"] for x in q(db, "SELECT block_number, block_hash FROM chain_blocks WHERE canonical")}
    assert all(canon[n] == ch.blocks[n]["hash"] for n in canon)


def test_too_deep_reorg_refuses_and_changes_nothing(db):
    ch = FakeChain(60, logs_at=logs_for(range(60)))
    ingest(ch, db, "eth", start_block=0, confirmations=0)
    ch.reorg(5, 60, salt="deep")
    with pytest.raises(ReorgTooDeep):
        ingest(ch, db, "eth", confirmations=0, max_reorg_depth=10)
    assert q(db, "SELECT count(*) AS n FROM chain_blocks WHERE NOT canonical")[0]["n"] == 0
    assert q(db, "SELECT next_block FROM chain_cursor")[0]["next_block"] == 60


def test_inconsistent_node_gives_up_loudly(db):
    ch = FakeChain(20, logs_at=logs_for(range(20)))
    orig = ch.logs

    def liar(lo, hi, t=None, a=None):
        out = orig(lo, hi, t, a)
        for l in out:
            l["block_hash"] = "0x" + "ee" * 32
        return out
    ch.logs = liar
    with pytest.raises(IngestError, match="no consistent view"):
        ingest(ch, db, "eth", start_block=0, confirmations=0)
    assert q(db, "SELECT count(*) AS n FROM chain_logs")[0]["n"] == 0


def test_concurrent_ingesters_second_is_refused_or_harmless(db):
    ch = FakeChain(50, logs_at=logs_for(range(50)))
    gate, entered = threading.Event(), threading.Event()
    first_result, errs = {}, []

    def slow(c, name, args):
        if name == "logs" and not entered.is_set():
            entered.set(); gate.wait(10)
    ch.hook = slow
    t = threading.Thread(target=lambda: first_result.setdefault("r", ingest(ch, db, "eth", start_block=0, confirmations=0)))
    t.start()
    assert entered.wait(10)
    with pytest.raises(IngestBusy):
        ingest(FakeChain(50), db, "eth", start_block=0, confirmations=0)
    gate.set(); t.join(30)
    assert first_result["r"].blocks == 50
    ingest(FakeChain(50), db, "other", start_block=0, confirmations=0)            # another chain is independent


def test_two_chains_do_not_mix(db):
    a, b = FakeChain(15, salt="a", logs_at=logs_for(range(15))), FakeChain(15, salt="q", logs_at=logs_for(range(0, 15, 5)))
    ingest(a, db, "eth", start_block=0, confirmations=0)
    ingest(b, db, "bsc", start_block=0, confirmations=0)
    assert q(db, "SELECT count(*) AS n FROM chain_logs WHERE chain='eth'")[0]["n"] == 30
    assert q(db, "SELECT count(*) AS n FROM chain_logs WHERE chain='bsc'")[0]["n"] == 6


def test_address_and_topic_filters_are_passed_to_the_node(db):
    ch = FakeChain(10, logs_at={3: [transfer_log(addr(9), addr(1), addr(2), 1), transfer_log(addr(8), addr(1), addr(2), 2)]})
    ingest(ch, db, "eth", start_block=0, confirmations=0, addresses=[addr(8)])
    rows = q(db, "SELECT address FROM chain_logs")
    assert [r["address"] for r in rows] == [addr(8)]


def test_invalid_arguments():
    with pytest.raises(ValueError):
        ingest(FakeChain(3), "x", "Bad Chain!", start_block=0)
    with pytest.raises(ValueError):
        ingest(FakeChain(3), "x", "eth", start_block=0, batch=0)


# ---------------------------------------------------------------- constraint probes (database refuses bad provenance)
def test_database_rejects_malformed_provenance(db):
    ch = FakeChain(5, logs_at=logs_for([1]))
    ingest(ch, db, "eth", start_block=0, confirmations=0)
    h = ch.blocks[1]["hash"]
    bad = [
        ("INSERT INTO chain_blocks(chain,block_hash,block_number,parent_hash,block_ts,source) VALUES ('eth','0xABC',1,%s,1,'s')", (h,)),
        ("INSERT INTO chain_blocks(chain,block_hash,block_number,parent_hash,block_ts,source) VALUES ('ETH!','" + h + "',1,'" + h + "',1,'s')", ()),
        ("INSERT INTO chain_logs(chain,block_hash,block_number,tx_hash,log_index,address,topic0,topics,data) VALUES ('eth',%s,1,'0x12',0,%s,%s,ARRAY[%s],'0x')", (h, addr(1), h, h)),
        ("INSERT INTO chain_logs(chain,block_hash,block_number,tx_hash,log_index,address,topic0,topics,data) VALUES ('eth','0x" + "99" * 32 + "',1,%s,0,%s,%s,ARRAY[%s],'0x')", (h, addr(1), h, h)),   # FK: unknown block
        ("INSERT INTO chain_logs(chain,block_hash,block_number,tx_hash,log_index,address,topic0,topics,data) VALUES ('eth',%s,1,%s,0,%s,%s,ARRAY[%s],'0xZZ')", (h, h, addr(1), h, h)),
    ]
    for sql, params in bad:
        with psycopg.connect(db) as c:
            with pytest.raises(psycopg.errors.IntegrityError):
                c.execute(sql, params)
    # two canonical blocks at one height are impossible
    with psycopg.connect(db) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("INSERT INTO chain_blocks(chain,block_hash,block_number,parent_hash,block_ts,canonical,source) VALUES ('eth',%s,1,%s,1,true,'s')", ("0x" + "77" * 32, h))
    # duplicate log identity
    row = q(db, "SELECT * FROM chain_logs LIMIT 1")[0]
    with psycopg.connect(db) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("INSERT INTO chain_logs(chain,block_hash,block_number,tx_hash,log_index,address,topic0,topics,data) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (row["chain"], row["block_hash"], row["block_number"], row["tx_hash"], row["log_index"], row["address"], row["topic0"], row["topics"], row["data"]))
