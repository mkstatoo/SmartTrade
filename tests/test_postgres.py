"""Real PostgreSQL 16 tests (skipped without TEST_DATABASE_URL): schema, migrations, constraint probes, store."""
import threading
from pathlib import Path

import psycopg
import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from app.migrate import migrate
from app.store import PostgresStore
from conftest import drop_db, make_db, needs_pg

pytestmark = needs_pg
FIX = Path(__file__).parent / "fixtures"
SIG_SQL = """
select 'col', table_name, column_name, data_type, is_nullable, coalesce(column_default,'') from information_schema.columns where table_schema='public';
select 'con', conrelid::regclass::text, pg_get_constraintdef(oid) from pg_constraint where connamespace='public'::regnamespace;
select 'idx', tablename, regexp_replace(indexdef,'INDEX \\S+ ON','INDEX ON') from pg_indexes where schemaname='public';
"""


def build(kind):
    name, dsn = make_db(kind)
    if kind != "fresh":
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((FIX / f"schema_{kind}.sql").read_text())
    return name, dsn


@pytest.fixture(params=["fresh", "v0_3", "v0_4", "v0_4_2", "v0_4_3"])
def migrated(request):
    name, dsn = build(request.param)
    first = migrate(dsn)
    yield request.param, dsn, first
    drop_db(name)


def signature(dsn):
    out = set()
    with psycopg.connect(dsn) as c:
        for q in [s for s in SIG_SQL.split(";") if s.strip()]:
            out |= {tuple(map(str, r)) for r in c.execute(q).fetchall()}
    return out


def test_migration_chain_and_repeat_are_idempotent(migrated):
    kind, dsn, first = migrated
    assert first == {"fresh": ["schema.sql"], "v0_3": ["001_v03_to_v04", "002_v0_4_1", "003_v0_4_2", "004_v0_4_3", "005_v0_4_4"],
                     "v0_4": ["002_v0_4_1", "003_v0_4_2", "004_v0_4_3", "005_v0_4_4"],
                     "v0_4_2": ["004_v0_4_3", "005_v0_4_4"], "v0_4_3": ["005_v0_4_4"]}[kind]
    assert migrate(dsn) == [] and migrate(dsn) == []
    with psycopg.connect(dsn) as c:
        assert c.execute("select count(*) from pg_constraint where not convalidated").fetchone()[0] == 0
        vers = {r[0] for r in c.execute("select version from schema_migrations")}
    assert {"002_v0_4_1", "003_v0_4_2", "004_v0_4_3", "005_v0_4_4"} <= vers


def test_migrated_schema_equals_fresh_schema():
    names, sigs = [], {}
    try:
        for kind in ("fresh", "v0_3", "v0_4", "v0_4_2", "v0_4_3"):
            n, dsn = build(kind)
            names.append(n)
            migrate(dsn)
            sigs[kind] = signature(dsn)
    finally:
        for n in names:
            drop_db(n)
    assert sigs["fresh"] == sigs["v0_3"] == sigs["v0_4"] == sigs["v0_4_2"] == sigs["v0_4_3"]


def test_schema_sql_twice_is_harmless():
    n, dsn = make_db()
    try:
        migrate(dsn)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((Path(__file__).parents[1] / "data" / "schema.sql").read_text())
        assert migrate(dsn) == []
    finally:
        drop_db(n)


# ------------------------------------------------------------------ probes on the MIGRATED database
def seed(c):
    c.execute("insert into tokens(chain,contract) values ('base','0xt') on conflict do nothing")
    c.execute("insert into wallets(chain,address) values ('base','0xw') on conflict do nothing")


def ev(c, tx="0xtx", log=None, side="BUY", **kw):
    vals = dict(tx_hash=tx, log_index=log, side=side, usd_value=10, price=1, ts="2026-01-01")
    vals.update(kw)
    c.execute("insert into wallet_events(tx_hash,log_index,wallet_chain,wallet_address,token_chain,token_contract,"
              "ts,side,usd_value,price) values (%(tx_hash)s,%(log_index)s,'base','0xw','base','0xt',%(ts)s,%(side)s,"
              "%(usd_value)s,%(price)s)", vals)


def rejects(dsn, exc, fn):
    with psycopg.connect(dsn) as c:
        seed(c)
        c.commit()
        with pytest.raises(exc):
            fn(c)


def test_probe_null_log_index_duplicate_rejected(migrated):
    _, dsn, _ = migrated
    with psycopg.connect(dsn) as c:
        seed(c)
        ev(c)
        c.commit()
    rejects(dsn, UniqueViolation, lambda c: ev(c))                   # NULLS NOT DISTINCT
    rejects(dsn, UniqueViolation, lambda c: (ev(c, log=7), ev(c, log=7)))


def test_probe_buy_and_sell_of_same_log_allowed(migrated):
    _, dsn, _ = migrated
    with psycopg.connect(dsn) as c:
        seed(c)
        ev(c, log=1, side="BUY")
        ev(c, log=1, side="SELL")
        c.commit()


@pytest.mark.parametrize("sql", [
    "insert into wallets(chain,address) values ('base','0xABC')",
    "insert into wallets(chain,address) values ('solana','0xDEF')",
])
def test_probe_evm_address_must_be_lowercase(migrated, sql):
    _, dsn, _ = migrated
    rejects(dsn, CheckViolation, lambda c: c.execute(sql))


def test_probe_solana_case_preserved(migrated):
    _, dsn, _ = migrated
    with psycopg.connect(dsn) as c:
        c.execute("insert into wallets(chain,address) values ('solana','AbCdEf1234')")
        c.commit()


@pytest.mark.parametrize("sql,exc", [
    ("insert into signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action) "
     "values ('base','0xt','2026-01-01','2026-01-02',1,50,.5,'WAIT')", CheckViolation),
    ("insert into signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action) "
     "values ('base','0xnope','2026-01-02','2026-01-01',1,50,.5,'WAIT')", ForeignKeyViolation),
    ("insert into signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action) "
     "values ('base','0xt','2026-01-02','2026-01-01',-1,50,.5,'WAIT')", CheckViolation),
    ("insert into signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action) "
     "values ('base','0xt','2026-01-02','2026-01-01',1,150,.5,'WAIT')", CheckViolation),
    ("insert into signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action) "
     "values ('base','0xt',null,'2026-01-01',1,50,.5,'WAIT')", psycopg.errors.NotNullViolation),
    ("insert into paper_trades(chain,token_contract,side,ts,price,qty,notional_usd,status) "
     "values ('base','0xt','BUY','2026-01-01',1,1,1,'BOGUS')", CheckViolation),
    ("insert into paper_trades(chain,token_contract,side,ts,price,qty,notional_usd,status) "
     "values ('base','0xnope','BUY','2026-01-01',1,1,1,'OPEN')", ForeignKeyViolation),
    ("insert into paper_trades(chain,token_contract,side,ts,price,qty,notional_usd,status) "
     "values ('base','0xt','BUY','2026-01-01',-1,1,1,'OPEN')", CheckViolation),
    ("insert into price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) "
     "values ('base','0xt','2026-01-01','1m',1,1,2,1,0)", CheckViolation),
    ("insert into price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) "
     "values ('base','0xt','2026-01-01','1m',1,1,1,1,null)", psycopg.errors.NotNullViolation),
    ("insert into wallet_events(tx_hash,wallet_chain,wallet_address,token_chain,token_contract,ts,side) "
     "values ('0x1','base','0xw','base','0xmissing','2026-01-01','BUY')", ForeignKeyViolation),
    ("insert into wallet_events(tx_hash,wallet_chain,wallet_address,token_chain,token_contract,ts,side,usd_value) "
     "values ('0x1','base','0xw','base','0xt','2026-01-01','BUY',-5)", CheckViolation),
    ("insert into wallet_events(tx_hash,wallet_chain,wallet_address,token_chain,token_contract,ts,side) "
     "values ('0x1','base','0xw','base','0xt','2026-01-01','HODL')", CheckViolation),
])
def test_probe_constraints(migrated, sql, exc):
    _, dsn, _ = migrated
    rejects(dsn, exc, lambda c: c.execute(sql))


def test_price_bar_pk_includes_timeframe(migrated):
    _, dsn, _ = migrated
    q = ("insert into price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) "
         "values ('base','0xt','2026-01-01',%s,1,1,1,1,0)")
    with psycopg.connect(dsn) as c:
        seed(c)
        c.execute(q, ("1m",))
        c.execute(q, ("5m",))                                         # same ts, other timeframe: allowed
        c.commit()
    rejects(dsn, UniqueViolation, lambda c: c.execute(q, ("1m",)))


# ------------------------------------------------------------------ legacy data survives (quarantine, not deletion)
def test_legacy_v03_rows_are_migrated_or_quarantined_not_lost():
    n, dsn = build("v0_3")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("insert into wallets(chain,address) values ('base','0xABC'),('base','0xdef')")
            c.execute("insert into wallet_events(tx_hash,log_index,wallet_chain,wallet_address,token_chain,"
                      "token_contract,ts,side) values ('0x1',0,'base','0xABC','base','0xt','2026-01-01','BUY')")
            c.execute("insert into price_bars(chain,token_contract,ts,open,high,low,close,volume_usd) "
                      "values ('base','0xt','2026-01-01',1,1,1,1,null)")
            c.execute("insert into signals(chain,token_contract,wallet_count,score,confidence,action) "
                      "values ('base','0xt',2,80,.9,'WAIT')")
        migrate(dsn)
        with psycopg.connect(dsn) as c:
            assert [r[0] for r in c.execute("select address from wallets order by 1")] == ["0xabc", "0xdef"]
            assert c.execute("select wallet_address from wallet_events").fetchone()[0] == "0xabc"
            q = c.execute("select source_table, reason from legacy_quarantine").fetchall()
            assert ("price_bars", "null_volume_or_nonpositive_price") in q
            assert c.execute("select count(*) from signals").fetchone()[0] == 1
            assert c.execute("select count(*) from tokens where contract='0xt'").fetchone()[0] == 1
        assert migrate(dsn) == []
    finally:
        drop_db(n)


# ------------------------------------------------------------------ the store itself
@pytest.fixture
def pg():
    n, dsn = make_db("store")
    migrate(dsn)
    yield dsn
    drop_db(n)


def test_store_roundtrip_is_exact_and_atomic(pg):
    st = PostgresStore(pg)
    with st.txn() as s:
        s.portfolio.update_market_price("base:0xt", 0.1 + 0.2, 1_700_000_100)   # float with long repr
        s.portfolio.enter("base:0xt", stop_loss_pct=2)
    with st.read() as p:
        assert p.last_prices["base:0xt"] == 0.1 + 0.2
        assert p.positions["base:0xt"]["entry_ts"] == 1_700_000_100
    with pytest.raises(RuntimeError):
        with st.txn() as s:
            s.portfolio.exit("base:0xt", 1.0, "manual")
            raise RuntimeError("boom")                                # must roll everything back
    with st.read() as p:
        assert "base:0xt" in p.positions
    assert st.recent_closed_trades() == []


def test_two_writers_are_serialised_by_row_lock(pg):
    st = PostgresStore(pg)
    with st.txn() as s:
        s.portfolio.update_market_price("base:0xt", 100, 1_700_000_100)
    results = []

    def worker():
        with PostgresStore(pg).txn() as s:
            results.append(s.portfolio.enter("base:0xt")["status"])

    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(results) == ["already_in_position"] * 5 + ["entered"]
    with st.read() as p:
        assert len(p.positions) == 1


def test_fail_closed_without_database(monkeypatch):
    from app.store import store_from_env
    for k in ("DATABASE_URL", "PGHOST", "STORE_BACKEND"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        store_from_env()


# ------------------------------------------------------------------ v0.4.3: canonical token identity in the database
@pytest.mark.parametrize("sql,exc", [
    ("insert into tokens(chain,contract) values ('base','0xABC')", CheckViolation),
    ("insert into tokens(chain,contract) values ('weirdchain','0xABC')", CheckViolation),
    ("insert into price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) "
     "values ('base','0xABC','2026-01-01','1m',1,1,1,1,0)", CheckViolation),
])
def test_probe_evm_token_must_be_lowercase(migrated, sql, exc):
    _, dsn, _ = migrated
    rejects(dsn, exc, lambda c: c.execute(sql))


def test_probe_solana_token_case_preserved(migrated):
    _, dsn, _ = migrated
    with psycopg.connect(dsn) as c:
        c.execute("insert into tokens(chain,contract) values ('solana','AbC'),('solana','abc')")
        c.commit()


def test_probe_time_exit_columns(migrated):
    _, dsn, _ = migrated
    base = ("insert into paper_portfolios(portfolio_id,initial_cash_usd,cash_usd,peak_equity_usd,slippage_bps,fee_bps,gas_usd) "
            "values ('p',1,1,1,0,0,0) on conflict do nothing")
    pos = ("insert into paper_positions(portfolio_id,token_key,qty,entry,cost,notional,entry_fee_usd,entry_gas_usd,"
           "reference_price,fee_bps,slippage_bps,gas_usd,entry_ts,max_hold_sec,expires_ts) "
           "values ('p','base:0x1',1,1,1,1,0,0,1,0,0,0,100,%s,%s)")
    with psycopg.connect(dsn) as c:
        c.execute(base)
        c.execute(pos, (60, 160))
        c.commit()
    for hold, exp in [(0, 100), (60, 50)]:
        with psycopg.connect(dsn) as c:
            c.execute(base)
            with pytest.raises(CheckViolation):
                c.execute(pos.replace("base:0x1", "base:0x2"), (hold, exp))


def test_legacy_mixed_case_tokens_are_merged_not_lost():
    n, dsn = build("v0_4")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("insert into tokens(chain,contract,symbol) values ('base','0xABC','AAA'),('base','0xabc',null),"
                      "('solana','SolMixed','S')")
            c.execute("insert into wallets(chain,address) values ('base','0xw')")
            c.execute("insert into wallet_events(tx_hash,log_index,wallet_chain,wallet_address,token_chain,token_contract,"
                      "ts,side) values ('0x1',0,'base','0xw','base','0xABC','2026-01-01','BUY')")
            c.execute("insert into price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) values "
                      "('base','0xABC','2026-01-01','1m',1,1,1,1,1),('base','0xabc','2026-01-01','1m',2,2,2,2,2),"
                      "('base','0xABC','2026-01-02','1m',3,3,3,3,3)")
        migrate(dsn)
        with psycopg.connect(dsn) as c:
            assert [r[0] for r in c.execute("select contract from tokens order by 1")] == ["0xabc", "SolMixed"]
            assert c.execute("select symbol from tokens where contract='0xabc'").fetchone()[0] == "AAA"
            assert c.execute("select token_contract from wallet_events").fetchone()[0] == "0xabc"
            bars = c.execute("select ts::date::text, open from price_bars order by ts").fetchall()
            assert [(b[0], float(b[1])) for b in bars] == [("2026-01-01", 2.0), ("2026-01-02", 3.0)]
            q = c.execute("select source_table, reason, row->>'open' from legacy_quarantine").fetchall()
            assert ("price_bars", "duplicate_after_token_normalization", "1") in q
        assert migrate(dsn) == []
    finally:
        drop_db(n)


# ------------------------------------------------------------------ concurrency / transactions through the API
def _app(dsn, raise_exc=True):
    from fastapi.testclient import TestClient
    from app.clock import ReplayClock
    from app.main import create_app
    return TestClient(create_app(PostgresStore(dsn), ReplayClock()), raise_server_exceptions=raise_exc,
                      headers={"X-Research-Key": __import__("conftest").KEY})


def test_concurrent_identical_bar_is_accepted_once(pg):
    from conftest import H, T0
    body = {"chain": "base", "token": "0xc", "ts": T0, "open": 1, "high": 2, "low": 1, "close": 2, "volume_usd": 1}
    out = []

    def worker():
        with _app(pg) as c:
            out.append(c.post("/paper/replay/bar", headers=H, json=body).json()["status"])

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out) == ["accepted"] + ["duplicate"] * 7
    with psycopg.connect(pg) as c:
        assert c.execute("select count(*) from price_bars").fetchone()[0] == 1


def test_concurrent_signals_enter_exactly_once(pg):
    from conftest import H, MIN, T0, bar, good_wallets
    with _app(pg) as c:
        bar(c, "0xc", T0, 100, 100, 100, 100)
    body = {"token": "0xc", "chain": "base", "wallets": good_wallets(T0 + MIN), "liquidity_usd": 1e7, "signal_ts": T0 + MIN}
    out = []

    def worker():
        with _app(pg) as c:
            out.append(c.post("/paper/signal", headers=H, json=body).json())

    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(o["action"] for o in out) == ["ENTER"] + ["WAIT"] * 5
    with psycopg.connect(pg) as c:
        assert c.execute("select count(*) from paper_positions").fetchone()[0] == 1
        assert c.execute("select count(*) from paper_trades where side='BUY'").fetchone()[0] == 1
        assert c.execute("select count(*) from signals").fetchone()[0] == 6        # every decision audited
        cash = float(c.execute("select cash_usd from paper_portfolios").fetchone()[0])
    assert cash == pytest.approx(10000 - 500 - 1.5 - 2)                               # charged once


def test_failed_transaction_rolls_back_everything(pg, monkeypatch):
    from app.store import _PgSession
    from conftest import H, MIN, T0, bar, good_wallets
    with _app(pg) as c:
        bar(c, "0xc", T0, 100, 100, 100, 100)
    body = {"token": "0xc", "chain": "base", "wallets": good_wallets(T0 + MIN), "liquidity_usd": 1e7, "signal_ts": T0 + MIN}

    def boom(self, **row):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(_PgSession, "record_signal", boom)
    with _app(pg, raise_exc=False) as c:
        assert c.post("/paper/signal", headers=H, json=body).status_code == 500
    with psycopg.connect(pg) as c:
        assert c.execute("select count(*) from paper_positions").fetchone()[0] == 0
        assert float(c.execute("select cash_usd from paper_portfolios").fetchone()[0]) == 10000.0
        assert c.execute("select count(*) from paper_trades").fetchone()[0] == 0


def test_concurrent_migrations_from_empty_database():
    n, dsn = make_db("mig")
    try:
        res, errs = [], []

        def worker():
            try:
                res.append(migrate(dsn))
            except Exception as exc:  # noqa: BLE001
                errs.append(exc)
        ts = [threading.Thread(target=worker) for _ in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert not errs
        assert sorted(res, key=len)[-1] == ["schema.sql"] and sum(1 for r in res if r) == 1
        assert migrate(dsn) == []
    finally:
        drop_db(n)
