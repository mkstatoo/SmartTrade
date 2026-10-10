"""How the API behaves when PostgreSQL misbehaves: always a clean 503/500, never a leak, never a half-written state."""
import threading
import time
from dataclasses import replace

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.config import CONFIG
from app.main import create_app
from app.migrate import migrate
from app.store import PostgresStore, _PgSession
from conftest import H, KEY, MIN, T0, bar, drop_db, good_wallets, make_db, needs_pg

pytestmark = needs_pg
SECRETS = ("nonexistent", "password", "postgresql://", "psycopg", "Traceback", "secret detail", "host=")


@pytest.fixture
def db():
    n, dsn = make_db("fail")
    migrate(dsn)
    yield dsn
    drop_db(n)


def app_for(store, raise_exc=False):
    return TestClient(create_app(store, ReplayClock()), headers=H, raise_server_exceptions=raise_exc)


def assert_clean(r, status):
    assert r.status_code == status, (r.status_code, r.text)
    assert not any(s in r.text for s in SECRETS), r.text
    assert set(r.json()) == {"detail"}


BAR = {"chain": "base", "token": "0xa", "ts": T0, "open": 1, "high": 2, "low": 1, "close": 2, "volume_usd": 1}


def rows(dsn, table):
    with psycopg.connect(dsn) as c:
        return c.execute(f"select count(*) from {table}").fetchone()[0]


def test_database_unreachable_is_503_without_leaking_the_dsn():
    store = PostgresStore("postgresql://appuser:hunter2@/nonexistent?host=/nonexistent&port=1")
    with app_for(store) as c:
        r = c.get("/paper")
        assert_clean(r, 503)
        assert r.headers["Retry-After"] == "5" and "hunter2" not in r.text
        assert_clean(c.post("/paper/replay/bar", json=BAR), 503)
        assert_clean(c.post("/paper/sweep"), 503)
        h = c.get("/health")
        assert h.status_code == 503


def test_backend_killed_before_commit_rolls_back_and_service_heals(db, monkeypatch):
    store = PostgresStore(db)
    orig = PostgresStore._save

    def kill_then_save(self, conn, s):
        pid = conn.info.backend_pid
        with psycopg.connect(db, autocommit=True) as admin:
            admin.execute("select pg_terminate_backend(%s)", (pid,))
        time.sleep(0.2)
        return orig(self, conn, s)
    monkeypatch.setattr(PostgresStore, "_save", kill_then_save)
    with app_for(store) as c:
        assert_clean(c.post("/paper/replay/bar", json=BAR), 503)
        assert rows(db, "price_bars") == 0 and rows(db, "paper_price_book") == 0
        monkeypatch.setattr(PostgresStore, "_save", orig)              # the "outage" is over
        assert c.post("/paper/replay/bar", json=BAR).status_code == 200
        assert rows(db, "price_bars") == 1


def test_retry_after_failed_commit_is_safe_for_bars_and_signals(db, monkeypatch):
    store = PostgresStore(db)
    with app_for(store) as c:
        bar(c, "0xa", T0, 100, 100, 100, 100)
        body = {"token": "0xa", "chain": "base", "wallets": good_wallets(T0 + MIN), "liquidity_usd": 1e7, "signal_ts": T0 + MIN}
        orig = PostgresStore._save
        fail = {"on": True}

        def flaky(self, conn, s):
            if fail["on"]:
                raise psycopg.OperationalError("connection lost during commit")
            return orig(self, conn, s)
        monkeypatch.setattr(PostgresStore, "_save", flaky)
        assert_clean(c.post("/paper/signal", json=body), 503)
        assert rows(db, "paper_positions") == 0 and rows(db, "signals") == 0
        fail["on"] = False
        assert c.post("/paper/signal", json=body).json()["action"] == "ENTER"      # client retry works once
        assert c.post("/paper/signal", json=body).json()["reasons"] == ["already_in_position"]
        assert rows(db, "paper_positions") == 1 and rows(db, "paper_trades") == 1


def test_lock_timeout_gives_503_quickly_instead_of_hanging(db):
    store = PostgresStore(db, cfg=replace(CONFIG, db_lock_timeout_ms=400))
    with app_for(store) as c:
        bar(c, "0xa", T0, 100, 100, 100, 100)                          # creates the portfolio row
        blocker = psycopg.connect(db)
        blocker.execute("select * from paper_portfolios for update")   # another worker holds the portfolio lock
        try:
            t = time.time()
            r = c.post("/paper/replay/bar", json={**BAR, "ts": T0 + MIN})
            elapsed = time.time() - t
            assert_clean(r, 503)
            assert elapsed < 5, elapsed
            assert c.get("/paper").status_code == 200                  # readers are not blocked
        finally:
            blocker.rollback()
            blocker.close()
        assert c.post("/paper/replay/bar", json={**BAR, "ts": T0 + MIN}).status_code == 200


def test_statement_timeout_gives_503(db, monkeypatch):
    store = PostgresStore(db, cfg=replace(CONFIG, db_statement_timeout_ms=200))
    orig = PostgresStore._load

    def slow(self, conn, lock):
        conn.execute("select pg_sleep(2)")
        return orig(self, conn, lock)
    monkeypatch.setattr(PostgresStore, "_load", slow)
    with app_for(store) as c:
        t = time.time()
        assert_clean(c.post("/paper/replay/bar", json=BAR), 503)
        assert time.time() - t < 1.5


def test_integrity_error_is_a_generic_500_and_leaves_no_partial_state(db, monkeypatch):
    store = PostgresStore(db)

    def bad(self, **row):
        raise psycopg.errors.UniqueViolation("secret detail: key (x)=(y) already exists")
    monkeypatch.setattr(_PgSession, "record_signal", bad)
    with app_for(store) as c:
        bar(c, "0xa", T0, 100, 100, 100, 100)
        body = {"token": "0xa", "chain": "base", "wallets": good_wallets(T0 + MIN), "liquidity_usd": 1e7, "signal_ts": T0 + MIN}
        r = c.post("/paper/signal", json=body)
        assert_clean(r, 500)
        assert r.json() == {"detail": "internal storage error"}
        assert rows(db, "paper_positions") == 0


def test_read_only_database_keeps_reads_and_refuses_writes_with_503(db):
    store = PostgresStore(db)
    with app_for(store) as c:
        bar(c, "0xa", T0, 100, 100, 100, 100)
        with psycopg.connect(db, autocommit=True) as admin:
            name = admin.execute("select current_database()").fetchone()[0]
            admin.execute(f'ALTER DATABASE "{name}" SET default_transaction_read_only = on')
        try:
            assert c.get("/paper").status_code == 200
            assert_clean(c.post("/paper/replay/bar", json={**BAR, "ts": T0 + MIN}), 503)
        finally:
            with psycopg.connect(db, autocommit=True) as admin:
                admin.execute("SET default_transaction_read_only = off")     # session override, then lift the DB-level one
                admin.execute(f'ALTER DATABASE "{name}" RESET default_transaction_read_only')
        assert c.post("/paper/replay/bar", json={**BAR, "ts": T0 + MIN}).status_code == 200


def test_pool_exhaustion_like_burst_of_failures_does_not_wedge_the_app(db, monkeypatch):
    """Many concurrent requests while the DB is refusing connections: every one answers 503, then all recover."""
    store = PostgresStore(db)
    real = PostgresStore._connect
    down = {"v": True}

    def maybe(self):
        if down["v"]:
            raise psycopg.OperationalError("server closed the connection unexpectedly")
        return real(self)
    monkeypatch.setattr(PostgresStore, "_connect", maybe)
    codes = []
    with app_for(store) as c:
        def hit():
            codes.append(c.get("/paper").status_code)
        ts = [threading.Thread(target=hit) for _ in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert codes == [503] * 12
        down["v"] = False
        assert c.get("/paper").status_code == 200
