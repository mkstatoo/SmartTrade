# Smart Copy Trading v0.4 — Remediation Report

## Scope
This release addresses the P0/P1 findings supplied in the v0.3 technical review. It is a remediation build, not an independent audit.

## Fixed
1. Client-controlled paper prices removed from HTTP signal/exit/mark flows; paper requires an internal trusted price book.
2. Prices are finite and strictly positive.
3. Stop/target execution is applied at bar level with conservative stop-first semantics.
4. Last prices persist; GET status is observational; initial cash/peak equity are synchronized.
5. Sizing uses equity, default 5%, and a 15% total exposure cap; stop cooldown added.
6. Strict as-of requires signal_ts, rejects future timestamps and stale statistics.
7. Unknown clusters collapse into one non-independent bucket per chain.
8. Backtest deduplicates event identity, prevents overlapping wallet-token observations, reports effective_n, and keys prices by chain+token.
9. PostgreSQL schema adds tokens, checks, block/reorg provenance, timeframe, stats_as_of_ts and safer event uniqueness.
10. README, .env.example, dependency pins and v0.3→v0.4 migration are included.

## Verification
- Python test suite: **57 passed**.
- Python compile check: passed.
- Live PostgreSQL execution: **not run in this build environment** because neither Docker nor psql/psycopg is available. A conditional integration test is included for CI (`TEST_DATABASE_URL`).

## Still not production-ready
- FastAPI still uses an in-memory portfolio.
- No SQLAlchemy repository wiring yet.
- No real blockchain/indexer ingestion.
- No DEX decoder.
- No historical as-of statistics engine.
- No actual wallet clustering/entity resolution.
- The internal price hook is still an in-process adapter seam, not a live market-data service.
- No live execution.
