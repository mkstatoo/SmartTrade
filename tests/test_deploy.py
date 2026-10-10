"""Deployment tests on a real PostgreSQL cluster that the tests start, kill and restore themselves:
  * upgrade from every historical schema, then use the app (not just inspect the catalog);
  * pg_dump / pg_restore of a populated database: state identical, migration a no-op, service works on the copy;
  * hard crash (pg_ctl -m immediate): committed data survives WAL recovery, uncommitted data does not, the SAME app
    instance recovers without a restart;
  * clean restart under a running app.
Synthetic bars / chain data are engine-test fixtures."""
import hashlib
import os
import threading
import time
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.chain.ingest import ingest
from app.clock import ReplayClock
from app.main import create_app
from app.migrate import migrate
from app.store import PostgresStore
from conftest import H, MIN, T0, bar, signal
from fake_chain import FakeChain, addr, transfer_log, v2_swap_log
from pgcluster import Cluster, find_bin
from test_postgres import FIX, signature

_BIN = find_bin()
if _BIN is None and os.getenv("CI"):
    raise RuntimeError("PostgreSQL server binaries (initdb/pg_ctl) are required in CI")
pytestmark = pytest.mark.skipif(_BIN is None, reason="initdb/pg_ctl not installed")
TOK_A, TOK_B = "0xaaaa", "0xbbbb"


@pytest.fixture(scope="module")
def cluster():
    c = Cluster(_BIN).init()
    c.start()
    yield c
    c.destroy()


@pytest.fixture
def freshdb(cluster):
    name = f"d{time.time_ns()}"
    dsn = cluster.create_db(name)
    yield name, dsn
    cluster.drop_db(name)


def app(dsn):
    return TestClient(create_app(PostgresStore(dsn), ReplayClock()), headers=H, raise_server_exceptions=False)


def use_app(c):
    """target exit on token A (closed trade + cooldown), open position on token B."""
    bar(c, TOK_A, T0, 100, 100.5, 99.5, 100)
    assert signal(c, TOK_A, T0 + MIN, stop_loss_pct=2.0, target_return_pct=5.0)["action"] == "ENTER"
    out = bar(c, TOK_A, T0 + MIN, 100, 101, 99.9, 100.5)
    out = bar(c, TOK_A, T0 + 2 * MIN, 108, 109, 107, 108)
    assert out["bar_evaluation"]["reason"] == "target"
    bar(c, TOK_B, T0 + 2 * MIN, 50, 50.5, 49.5, 50)
    assert signal(c, TOK_B, T0 + 3 * MIN, stop_loss_pct=2.0, target_return_pct=50.0)["action"] == "ENTER"


def fingerprint(dsn):
    """Content hash of every table + every sequence position, independent of physical storage."""
    out = {}
    with psycopg.connect(dsn) as c:
        for (t,) in c.execute("select tablename from pg_tables where schemaname='public' order by 1").fetchall():
            rows = c.execute(f'select t::text from "{t}" t order by 1').fetchall()
            out[t] = (len(rows), hashlib.sha256("\n".join(r[0] for r in rows).encode()).hexdigest())
        for (s,) in c.execute("select sequencename from pg_sequences where schemaname='public' order by 1").fetchall():
            out["seq:" + s] = c.execute(f'select last_value, is_called from "{s}"').fetchone()
    return out


def populate(dsn):
    migrate(dsn)
    with app(dsn) as c:
        use_app(c)
    ch = FakeChain(40, logs_at={n: [transfer_log(addr(9), addr(1), addr(2), 10 + n), v2_swap_log(addr(5), addr(1), addr(2), n + 1, 0, 0, 3)] for n in range(0, 40, 3)})
    ingest(ch, dsn, "eth", start_block=0, confirmations=4)


# ---------------------------------------------------------------- upgrade from every baseline, then use the app
@pytest.mark.parametrize("kind", ["v0_3", "v0_4", "v0_4_2", "v0_4_3"])
def test_upgrade_from_each_release_then_run_the_service(cluster, kind):
    name = f"up_{kind}_{time.time_ns()}"
    dsn = cluster.create_db(name)
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((FIX / f"schema_{kind}.sql").read_text())
        applied = migrate(dsn)
        assert applied and migrate(dsn) == []
        fresh = cluster.create_db(name + "_f")
        migrate(fresh)
        assert signature(dsn) == signature(fresh)
        cluster.drop_db(name + "_f")
        populate(dsn)
        with app(dsn) as c:
            p = c.get("/paper").json()
            assert p["portfolio"]["open_positions"] == 1 and len(p["closed_trades"]) == 1
            assert p["closed_trades"][0]["price_basis"] == "bar"
        with psycopg.connect(dsn) as c:
            assert c.execute("select count(*) from chain_logs_canonical").fetchone()[0] > 0
    finally:
        cluster.drop_db(name)


# ---------------------------------------------------------------- backup / restore
def test_dump_and_restore_reproduce_state_and_service(cluster, freshdb):
    name, dsn = freshdb
    populate(dsn)
    before = fingerprint(dsn)
    assert before["paper_closed_trades"][0] == 1 and before["chain_logs"][0] > 0 and before["paper_positions"][0] == 1
    dump = cluster.base / f"{name}.dump"
    cluster.dump(name, dump)
    cluster.create_db(name + "_r")
    try:
        rdsn = cluster.dsn(name + "_r")
        cluster.restore(name + "_r", dump)
        assert fingerprint(rdsn) == before                              # every table and sequence identical
        assert signature(rdsn) == signature(dsn)
        assert migrate(rdsn) == []                                      # restored DB is recognised as current
        with app(dsn) as a, app(rdsn) as b:
            pa, pb = a.get("/paper").json(), b.get("/paper").json()
            assert pa == pb
            # the restored copy keeps working: close B on a later bar and insert new rows (sequences were restored)
            bar(b, TOK_B, T0 + 3 * MIN, 50, 50, 40, 41)
            p2 = b.get("/paper").json()
            assert p2["portfolio"]["open_positions"] == 0 and len(p2["closed_trades"]) == 2
        ch = FakeChain(60, logs_at={50: [transfer_log(addr(9), addr(1), addr(2), 1)]})
        r = ingest(ch, rdsn, "eth", confirmations=4)                    # chain cursor restored: resumes, no start_block
        assert r.blocks > 0 and r.next_block == 56
        # the original is untouched by work on the copy
        assert fingerprint(dsn) == before
    finally:
        cluster.drop_db(name + "_r")


def test_restore_of_dump_taken_from_older_release_then_migrate(cluster):
    name = f"old_{time.time_ns()}"
    dsn = cluster.create_db(name)
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((FIX / "schema_v0_4_3.sql").read_text())
        cluster.dump(name, cluster.base / f"{name}.dump")
        cluster.create_db(name + "_r")
        cluster.restore(name + "_r", cluster.base / f"{name}.dump")
        rdsn = cluster.dsn(name + "_r")
        assert migrate(rdsn) == ["005_v0_4_4"]
        populate(rdsn)
        with app(rdsn) as c:
            assert c.get("/paper").json()["portfolio"]["open_positions"] == 1
    finally:
        cluster.drop_db(name); cluster.drop_db(name + "_r")


# ---------------------------------------------------------------- crash and restart
def test_hard_crash_keeps_committed_loses_uncommitted_and_service_self_heals(cluster, freshdb):
    name, dsn = freshdb
    populate(dsn)
    before = fingerprint(dsn)
    store = PostgresStore(dsn)
    c = TestClient(create_app(store, ReplayClock()), headers=H, raise_server_exceptions=False)
    with c:
        p0 = c.get("/paper").json()
        assert p0["portfolio"]["open_positions"] == 1
        # an in-flight transaction that never commits
        pending = psycopg.connect(dsn)
        pending.execute("insert into legacy_quarantine(source_table, reason, row) values ('crash_probe','uncommitted','{}')")
        with psycopg.connect(dsn, autocommit=True) as k:
            k.execute("insert into legacy_quarantine(source_table, reason, row) values ('crash_probe','committed','{}')")
        cluster.stop("immediate")                                       # SIGQUIT: no checkpoint, no clean shutdown
        down = c.get("/paper")
        assert down.status_code == 503 and down.headers["Retry-After"] == "5"
        assert "host=" not in down.text and "postgresql://" not in down.text
        assert c.post("/paper/replay/bar", json={"chain": "base", "token": TOK_B, "ts": T0 + 9 * MIN, "open": 1, "high": 1, "low": 1, "close": 1, "volume_usd": 1}).status_code == 503
        cluster.start()
        assert "automatic recovery in progress" in cluster.log_text()     # WAL replay really happened
        try:
            pending.close()
        except Exception:
            pass
        deadline, r = time.time() + 20, None
        while time.time() < deadline:                                   # same app instance, no restart
            r = c.get("/paper")
            if r.status_code == 200:
                break
            time.sleep(0.5)
        assert r.status_code == 200 and r.json() == p0
        with psycopg.connect(dsn) as k:
            reasons = {x[0] for x in k.execute("select reason from legacy_quarantine where source_table='crash_probe'")}
        assert reasons == {"committed"}
        after = fingerprint(dsn)
        for fp in (before, after):
            fp.pop("legacy_quarantine")
        seq_b = {k: v for k, v in before.items() if k.startswith("seq:")}
        seq_a = {k: v for k, v in after.items() if k.startswith("seq:")}
        assert {k: v for k, v in after.items() if not k.startswith("seq:")} == {k: v for k, v in before.items() if not k.startswith("seq:")}
        # PostgreSQL pre-logs up to 32 sequence values, so after crash recovery a sequence may skip ahead (gaps are
        # normal) but must never move backwards, otherwise ids could repeat.
        assert all(seq_a[k][0] >= seq_b[k][0] for k in seq_b if k != "seq:legacy_quarantine_id_seq")
        bar(c, TOK_B, T0 + 3 * MIN, 50, 50, 40, 41)                     # writes work again
        assert c.get("/paper").json()["portfolio"]["open_positions"] == 0


def test_crash_while_writers_are_active_never_leaves_a_torn_state(cluster, freshdb):
    name, dsn = freshdb
    migrate(dsn)
    c = app(dsn)
    stop = threading.Event()
    results = {"ok": 0, "503": 0, "other": []}

    def writer(k):
        t = T0 + k * 10_000 * MIN
        i = 0
        while not stop.is_set():
            r = c.post("/paper/replay/bar", json={"chain": "base", "token": f"0xw{k}", "ts": t + i * MIN, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume_usd": 1})
            if r.status_code == 200:
                results["ok"] += 1
            elif r.status_code == 503:
                results["503"] += 1
            else:
                results["other"].append((r.status_code, r.text[:80]))
            i += 1
    with c:
        ts = [threading.Thread(target=writer, args=(k,)) for k in range(3)]
        [t.start() for t in ts]
        time.sleep(1.0)
        cluster.stop("immediate")
        time.sleep(0.5)
        cluster.start()
        time.sleep(2.0)
        stop.set()
        [t.join(20) for t in ts]
    assert results["ok"] > 0 and results["503"] > 0, results
    assert results["other"] == [], results["other"]
    with psycopg.connect(dsn) as k:
        n = k.execute("select count(*) from price_bars").fetchone()[0]
        dup = k.execute("select count(*) from (select 1 from price_bars group by chain, token_contract, timeframe, ts having count(*)>1) x").fetchone()[0]
        bad = k.execute("select count(*) from pg_constraint where not convalidated").fetchone()[0]
    assert n >= results["ok"] and dup == 0 and bad == 0       # every acknowledged write is durable; none duplicated


def test_clean_restart_under_running_app(cluster, freshdb):
    name, dsn = freshdb
    populate(dsn)
    with app(dsn) as c:
        p0 = c.get("/paper").json()
        cluster.stop("fast")
        assert c.get("/paper").status_code == 503
        cluster.start()
        assert c.get("/paper").json() == p0
        assert "database system is shut down" in cluster.log_text()          # it was a clean stop, not a crash
