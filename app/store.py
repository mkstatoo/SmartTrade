"""Durable storage for the paper portfolio, the price book and the audit trail.

Both stores expose the same unit-of-work API:

    with store.txn() as s:          # serialises writers, commits on success, rolls back on any exception
        p = s.portfolio             # PaperPortfolio loaded from storage
        ...mutate p / s.record_bar() / s.record_signal()...

    with store.read() as p:         # read-only view, never writes

PostgresStore keeps everything in PostgreSQL (portfolio row lock => safe with several workers and
survives restarts). MemoryStore is an explicit opt-in for tests / throw-away runs only.
"""
from __future__ import annotations

import copy
import os
import threading
from contextlib import contextmanager
from decimal import Decimal
from typing import Optional

from .config import CONFIG, Config
from .paper import PaperPortfolio


def split_key(token_key: str) -> tuple[str, str]:
    chain, _, contract = token_key.partition(":")
    return chain, contract


def _d(x):
    """float -> Decimal via repr so NUMERIC round-trips exactly (float8->numeric would round to 15 digits)."""
    return None if x is None else Decimal(repr(float(x)))


def _f(x):
    return None if x is None else float(x)


def new_portfolio(cfg: Config = CONFIG) -> PaperPortfolio:
    return PaperPortfolio(initial_cash_usd=cfg.paper_initial_cash_usd, slippage_bps=cfg.paper_slippage_bps,
                          fee_bps=cfg.paper_fee_bps, gas_usd=cfg.paper_gas_usd, default_max_hold_sec=cfg.paper_max_hold_sec)


class Session:
    """One unit of work. Collects side records; the store flushes them atomically on commit."""

    def __init__(self, portfolio: PaperPortfolio):
        self.portfolio = portfolio
        self._bars: list[dict] = []
        self._signals: list[dict] = []
        self._signal_seq = 0

    # overridden by stores that can look things up
    def get_bar(self, token_key: str, timeframe: str, ts: int) -> Optional[dict]:
        for b in self._bars:
            if (b["token_key"], b["timeframe"], b["ts"]) == (token_key, timeframe, ts):
                return b
        return None

    def record_bar(self, token_key: str, bar: dict) -> None:
        self._bars.append({"token_key": token_key, **bar})

    def record_signal(self, **row) -> int:
        raise NotImplementedError


# =============================================================================== memory
class _MemorySession(Session):
    def __init__(self, portfolio, store):
        super().__init__(portfolio)
        self._store = store
        self._seq = store._signal_seq

    def get_bar(self, token_key, timeframe, ts):
        return super().get_bar(token_key, timeframe, ts) or self._store.bars.get((token_key, timeframe, ts))

    def record_signal(self, **row) -> int:
        self._seq += 1
        self._signals.append({"id": self._seq, **row})
        return self._seq


class MemoryStore:
    name = "memory"
    persistent = False

    def __init__(self, cfg: Config = CONFIG):
        self._cfg = cfg
        self._state = new_portfolio(cfg)
        self._lock = threading.RLock()
        self.bars: dict = {}
        self.signals: list = []
        self.closed_trades: list = []
        self.fills: list = []
        self._signal_seq = 0

    def ping(self) -> bool:
        return True

    @contextmanager
    def txn(self):
        with self._lock:
            s = _MemorySession(copy.deepcopy(self._state), self)
            yield s                                    # an exception here discards the copy (= rollback)
            p = s.portfolio
            self.closed_trades.extend(p.new_closed_trades)
            self.fills.extend(p.new_fills)
            p.new_closed_trades, p.new_fills = [], []
            for b in s._bars:
                self.bars.setdefault((b["token_key"], b["timeframe"], b["ts"]), b)
            self.signals.extend(s._signals)
            self._signal_seq = s._seq
            self._state = p

    @contextmanager
    def read(self):
        with self._lock:
            yield copy.deepcopy(self._state)

    def recent_closed_trades(self, limit: int = 50) -> list:
        with self._lock:
            return list(reversed(self.closed_trades[-limit:]))

    def recent_fills(self, limit: int = 50) -> list:
        with self._lock:
            return list(reversed(self.fills[-limit:]))


# =============================================================================== postgres
class _PgSession(Session):
    def __init__(self, portfolio, conn, portfolio_id):
        super().__init__(portfolio)
        self._conn, self._pid = conn, portfolio_id

    def get_bar(self, token_key, timeframe, ts):
        local = super().get_bar(token_key, timeframe, ts)
        if local:
            return local
        chain, contract = split_key(token_key)
        row = self._conn.execute(
            "SELECT open,high,low,close,volume_usd FROM price_bars "
            "WHERE chain=%s AND token_contract=%s AND timeframe=%s AND ts=to_timestamp(%s)",
            (chain, contract, timeframe, ts)).fetchone()
        return None if row is None else {k: float(v) for k, v in row.items()}

    def record_signal(self, *, token_key, signal_ts, stats_as_of_ts, wallet_count, score, confidence,
                      action, reasons) -> int:
        import json
        chain, contract = split_key(token_key)
        self._conn.execute("INSERT INTO tokens(chain,contract) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                           (chain, contract))
        row = self._conn.execute(
            "INSERT INTO signals(chain,token_contract,ts,stats_as_of_ts,wallet_count,score,confidence,action,reason) "
            "VALUES (%s,%s,to_timestamp(%s),to_timestamp(%s),%s,%s,%s,%s,%s) RETURNING id",
            (chain, contract, signal_ts, stats_as_of_ts, wallet_count, _d(score), _d(confidence), action,
             json.dumps({"reasons": reasons}))).fetchone()
        return int(row["id"])


class PostgresStore:
    name = "postgres"
    persistent = True

    def __init__(self, dsn: str = "", portfolio_id: str = CONFIG.paper_portfolio_id, cfg: Config = CONFIG):
        self.dsn, self.pid, self._cfg = dsn, portfolio_id, cfg

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        c = self._cfg
        opts = (f"-c statement_timeout={c.db_statement_timeout_ms} -c lock_timeout={c.db_lock_timeout_ms} "
                "-c idle_in_transaction_session_timeout=60000")
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=c.db_connect_timeout_sec, options=opts)

    def ping(self) -> bool:
        try:
            with self._connect() as c:
                c.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    # ---------------------------------------------------------------- load / save
    def _ensure_row(self, conn):
        base = new_portfolio(self._cfg)
        conn.execute(
            "INSERT INTO paper_portfolios(portfolio_id,initial_cash_usd,cash_usd,peak_equity_usd,"
            "slippage_bps,fee_bps,gas_usd) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (self.pid, _d(base.initial_cash_usd), _d(base.cash_usd), _d(base.peak_equity_usd),
             _d(base.slippage_bps), _d(base.fee_bps), _d(base.gas_usd)))

    def _load(self, conn, lock: bool) -> PaperPortfolio:
        row = conn.execute("SELECT * FROM paper_portfolios WHERE portfolio_id=%s" + (" FOR UPDATE" if lock else ""),
                           (self.pid,)).fetchone()
        if row is None:                                   # read-only path before first write
            return new_portfolio(self._cfg)
        p = PaperPortfolio(
            initial_cash_usd=_f(row["initial_cash_usd"]), cash_usd=_f(row["cash_usd"]),
            realized_pnl_usd=_f(row["realized_pnl_usd"]), peak_equity_usd=_f(row["peak_equity_usd"]),
            max_drawdown_pct=_f(row["max_drawdown_pct"]), now_ts=int(row["now_ts"]),
            slippage_bps=_f(row["slippage_bps"]), fee_bps=_f(row["fee_bps"]), gas_usd=_f(row["gas_usd"]))
        for r in conn.execute("SELECT * FROM paper_positions WHERE portfolio_id=%s", (self.pid,)):
            p.positions[r["token_key"]] = {
                "qty": _f(r["qty"]), "entry": _f(r["entry"]), "cost": _f(r["cost"]), "notional": _f(r["notional"]),
                "entry_fee_usd": _f(r["entry_fee_usd"]), "entry_gas_usd": _f(r["entry_gas_usd"]),
                "reference_price": _f(r["reference_price"]), "fee_bps": _f(r["fee_bps"]),
                "slippage_bps": _f(r["slippage_bps"]), "gas_usd": _f(r["gas_usd"]),
                "target_return_pct": _f(r["target_return_pct"]), "stop_loss_pct": _f(r["stop_loss_pct"]),
                "entry_ts": int(r["entry_ts"]), "signal_id": r["signal_id"],
                "max_hold_sec": None if r["max_hold_sec"] is None else int(r["max_hold_sec"]),
                "expires_ts": None if r["expires_ts"] is None else int(r["expires_ts"])}
        for r in conn.execute("SELECT * FROM paper_price_book WHERE portfolio_id=%s", (self.pid,)):
            p.last_prices[r["token_key"]] = _f(r["price"])
            p.last_price_ts[r["token_key"]] = int(r["price_ts"])
            p.last_bar_ts[r["token_key"]] = int(r["last_bar_ts"])
        for r in conn.execute("SELECT token_key,until_ts FROM paper_cooldowns WHERE portfolio_id=%s", (self.pid,)):
            p.cooldown_until[r["token_key"]] = int(r["until_ts"])
        return p

    def _save(self, conn, s: _PgSession) -> None:
        p, pid = s.portfolio, self.pid
        conn.execute(
            "UPDATE paper_portfolios SET cash_usd=%s,realized_pnl_usd=%s,peak_equity_usd=%s,max_drawdown_pct=%s,"
            "now_ts=%s,updated_at=now() WHERE portfolio_id=%s",
            (_d(p.cash_usd), _d(p.realized_pnl_usd), _d(p.peak_equity_usd), _d(p.max_drawdown_pct), p.now_ts, pid))
        conn.execute("DELETE FROM paper_positions WHERE portfolio_id=%s", (pid,))
        for tk, x in p.positions.items():
            conn.execute(
                "INSERT INTO paper_positions(portfolio_id,token_key,qty,entry,cost,notional,entry_fee_usd,"
                "entry_gas_usd,reference_price,fee_bps,slippage_bps,gas_usd,target_return_pct,stop_loss_pct,"
                "entry_ts,signal_id,max_hold_sec,expires_ts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (pid, tk, _d(x["qty"]), _d(x["entry"]), _d(x["cost"]), _d(x["notional"]), _d(x["entry_fee_usd"]),
                 _d(x["entry_gas_usd"]), _d(x["reference_price"]), _d(x["fee_bps"]), _d(x["slippage_bps"]),
                 _d(x["gas_usd"]), _d(x["target_return_pct"]), _d(x["stop_loss_pct"]), x["entry_ts"], x["signal_id"],
                 x["max_hold_sec"], x["expires_ts"]))
        for tk, price in p.last_prices.items():
            conn.execute(
                "INSERT INTO paper_price_book(portfolio_id,token_key,price,price_ts,last_bar_ts) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (portfolio_id,token_key) DO UPDATE SET price=EXCLUDED.price,price_ts=EXCLUDED.price_ts,"
                "last_bar_ts=EXCLUDED.last_bar_ts",
                (pid, tk, _d(price), p.last_price_ts[tk], p.last_bar_ts.get(tk, 0)))
        for tk, until in p.cooldown_until.items():
            conn.execute("INSERT INTO paper_cooldowns(portfolio_id,token_key,until_ts) VALUES (%s,%s,%s) "
                         "ON CONFLICT (portfolio_id,token_key) DO UPDATE SET until_ts=EXCLUDED.until_ts",
                         (pid, tk, until))
        for b in s._bars:
            chain, contract = split_key(b["token_key"])
            conn.execute(
                "INSERT INTO price_bars(chain,token_contract,ts,timeframe,open,high,low,close,volume_usd) "
                "VALUES (%s,%s,to_timestamp(%s),%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (chain, contract, b["ts"], b["timeframe"], _d(b["open"]), _d(b["high"]), _d(b["low"]),
                 _d(b["close"]), _d(b["volume_usd"])))
        for f in p.new_fills:
            chain, contract = split_key(f["token"])
            conn.execute("INSERT INTO tokens(chain,contract) VALUES (%s,%s) ON CONFLICT DO NOTHING", (chain, contract))
            conn.execute(
                "INSERT INTO paper_trades(portfolio_id,signal_id,chain,token_contract,side,ts,price,qty,notional_usd,"
                "status,fee_usd,slippage_usd,gas_usd) VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,%s,%s,%s,%s)",
                (pid, f["signal_id"], chain, contract, f["side"], f["ts"], _d(f["price"]), _d(f["qty"]),
                 _d(f["notional"]), "OPEN" if f["side"] == "BUY" else "CLOSED", _d(f["fee_usd"]),
                 _d(f["slippage_usd"]), _d(f["gas_usd"])))
            if f["side"] == "SELL":
                conn.execute("UPDATE paper_trades SET status='CLOSED' WHERE portfolio_id=%s AND chain=%s "
                             "AND token_contract=%s AND side='BUY' AND status='OPEN'", (pid, chain, contract))
        for t in p.new_closed_trades:
            conn.execute(
                "INSERT INTO paper_closed_trades(portfolio_id,token_key,entry,exit_price,market_level,qty,cost,pnl_usd,"
                "exit_fee_usd,exit_gas_usd,reason,entry_ts,exit_ts,signal_id,price_basis,price_age_sec) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (pid, t["token"], _d(t["entry"]), _d(t["exit"]), _d(t["market_level"]), _d(t["qty"]), _d(t["cost"]),
                 _d(t["pnl_usd"]), _d(t["exit_fee_usd"]), _d(t["exit_gas_usd"]), t["reason"], t["entry_ts"],
                 t["exit_ts"], t["signal_id"], t.get("price_basis", "bar"), t.get("price_age_sec")))
        p.new_closed_trades, p.new_fills = [], []

    # ---------------------------------------------------------------- unit of work
    @contextmanager
    def txn(self):
        conn = self._connect()
        try:
            self._ensure_row(conn)
            s = _PgSession(self._load(conn, lock=True), conn, self.pid)
            yield s
            self._save(conn, s)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self):
        conn = self._connect()
        try:
            yield self._load(conn, lock=False)
        finally:
            conn.rollback()
            conn.close()

    def recent_closed_trades(self, limit: int = 50) -> list:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM paper_closed_trades WHERE portfolio_id=%s ORDER BY id DESC LIMIT %s",
                             (self.pid, limit)).fetchall()
        return [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]

    def recent_fills(self, limit: int = 50) -> list:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM paper_trades WHERE portfolio_id=%s ORDER BY id DESC LIMIT %s",
                             (self.pid, limit)).fetchall()
        return [{k: (float(v) if isinstance(v, Decimal) else (v.isoformat() if hasattr(v, "isoformat") else v))
                 for k, v in r.items()} for r in rows]


def store_from_env(cfg: Config = CONFIG):
    """Fail closed: no database configured => refuse to start, unless in-memory is requested explicitly."""
    backend = os.getenv("STORE_BACKEND", "").lower()
    if backend == "memory":
        return MemoryStore(cfg)
    dsn = os.getenv("DATABASE_URL")
    if dsn is None and os.getenv("PGHOST"):
        dsn = ""                                              # libpq reads PGHOST/PGUSER/PGPASSWORD/PGDATABASE
    if dsn is None:
        raise RuntimeError("No database configured: set DATABASE_URL (or PG* variables). "
                           "For throw-away runs only, set STORE_BACKEND=memory explicitly.")
    return PostgresStore(dsn, cfg.paper_portfolio_id, cfg)
