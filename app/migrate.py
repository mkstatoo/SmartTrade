"""Schema installer / migration runner:   python -m app.migrate

  * empty database            -> data/schema.sql (full current schema)
  * v0.3 database             -> 001..005
  * v0.4 / v0.4.1 database    -> 002..005
  * recorded in schema_migrations -> only the pending ones
Takes an advisory lock so concurrent starts cannot race, and refuses to finish if any constraint is still NOT VALID.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
MIGRATIONS = [("001_v03_to_v04", "001_v03_to_v04.sql"), ("002_v0_4_1", "002_v0_4_1.sql"),
              ("003_v0_4_2", "003_v0_4_2.sql"), ("004_v0_4_3", "004_v0_4_3.sql"),
              ("005_v0_4_4", "005_v0_4_4.sql")]
LOCK_ID = 5_451_103


def dsn_from_env() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn is None and os.getenv("PGHOST"):
        return ""
    if dsn is None:
        raise RuntimeError("DATABASE_URL (or PG* variables) is required")
    return dsn


def _exists(conn, name: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL AS e", (name,)).fetchone()["e"]


def migrate(dsn: str) -> list[str]:
    import psycopg
    from psycopg.rows import dict_row
    applied_now: list[str] = []
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            if _exists(conn, "schema_migrations"):
                done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
                if _exists(conn, "tokens"):                    # v0.4+ baseline never recorded 001
                    done.add("001_v03_to_v04")
            elif not _exists(conn, "wallet_events"):
                conn.execute((DATA / "schema.sql").read_text(encoding="utf-8"))
                applied_now.append("schema.sql")
                done = {v for v, _ in MIGRATIONS}
            elif not _exists(conn, "tokens"):
                done = set()                                   # v0.3 baseline
            else:
                done = {"001_v03_to_v04"}                      # v0.4 / v0.4.1 baseline
            for version, fname in MIGRATIONS:
                if version in done:
                    continue
                conn.execute((DATA / "migrations" / fname).read_text(encoding="utf-8"))
                conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                             "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                conn.execute("INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING", (version,))
                applied_now.append(version)
            bad = conn.execute("SELECT conrelid::regclass::text AS t, conname FROM pg_constraint "
                               "WHERE NOT convalidated AND connamespace='public'::regnamespace").fetchall()
            if bad:
                raise RuntimeError(f"constraints still NOT VALID after migration: {bad}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return applied_now


if __name__ == "__main__":
    try:
        done = migrate(dsn_from_env())
    except Exception as exc:  # noqa: BLE001
        print(f"migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print("applied:", ", ".join(done) if done else "nothing (already up to date)")
