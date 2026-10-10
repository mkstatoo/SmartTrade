"""Shared fixtures.

Synthetic bars used here are ENGINE-TEST FIXTURES: they exercise deterministic accounting rules and say nothing
about markets. Nothing in app/ ever generates or hardcodes market data.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.main import create_app
from app.migrate import migrate
from app.store import MemoryStore, PostgresStore

KEY = "test-research-key-0123456789"
H = {"X-Research-Key": KEY}
T0 = 1_700_000_040          # multiple of 60 -> aligned 1m bar open
MIN = 60

TEST_DSN = os.getenv("TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not TEST_DSN, reason="TEST_DATABASE_URL not set (needs real PostgreSQL 16)")


def _admin():
    import psycopg
    return psycopg.connect(TEST_DSN, autocommit=True)


def make_db(prefix="t"):
    """Create a scratch database, return (name, dsn)."""
    from psycopg.conninfo import make_conninfo
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    with _admin() as c:
        c.execute(f'CREATE DATABASE "{name}"')
    return name, make_conninfo(TEST_DSN, dbname=name)


def drop_db(name):
    with _admin() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def pgdb():
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    name, dsn = make_db()
    yield dsn
    drop_db(name)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("PAPER_API_KEY", KEY)


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    name, dsn = make_db("api")
    migrate(dsn)
    yield PostgresStore(dsn)
    drop_db(name)


@pytest.fixture
def client(store):
    with TestClient(create_app(store, ReplayClock()), headers=H) as c:
        yield c


def wallet(addr, cluster, ts, chain="base", **kw):
    d = dict(wallet=addr, events=40, wins=36, losses=4, avg_return=3.0, token_events=10, token_wins=9,
             accumulation_usd=1_000_000, distribution_usd=0, cluster_id=cluster, pump_distance_pct=0,
             cex_outflow_share=1.0, volume_anomaly=2.0, as_of_ts=ts, chain=chain)
    d.update(kw)
    return d


def good_wallets(ts, chain="base"):
    return [wallet("0xa", "c1", ts, chain), wallet("0xb", "c2", ts, chain)]


def bar(client, token, ts, o, h, l, c, chain="base", vol=1_000_000, expect=200):
    r = client.post("/paper/replay/bar", headers=H, json={"chain": chain, "token": token, "ts": ts, "open": o,
                                                           "high": h, "low": l, "close": c, "volume_usd": vol})
    assert r.status_code == expect, r.text
    return r.json()


def signal(client, token, signal_ts, chain="base", liquidity=10_000_000, expect=200, **extra):
    body = {"token": token, "chain": chain, "wallets": good_wallets(signal_ts, chain), "liquidity_usd": liquidity,
            "signal_ts": signal_ts, **extra}
    r = client.post("/paper/signal", headers=H, json=body)
    assert r.status_code == expect, r.text
    return r.json()
