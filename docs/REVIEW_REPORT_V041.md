# v0.4.1 remediation report

This report describes changes and local test evidence; it is not an independent audit.

## Implemented
- Authenticated paper replay-bar ingress populates a timestamped in-memory price book and invokes bar evaluation; `GET /paper` is observational.
- Server-only strict as-of age/skew settings; client `max_stats_age_sec` removed; missing `as_of_ts` is rejected by request validation.
- Paper fills use follower-side entry slippage, entry/exit fees, gas estimate, entry timestamp, and stop/target evaluation. API exits require `X-Research-Key` and a constrained reason.
- EVM token/wallet keys are lowercased; Solana addresses preserve case; signal chain must match wallet chain.
- Backtest uses exact requested timeframe, deduplicates events with/without provider IDs, applies overlap suppression only after a trade actually executes, and reports `effective_n` from executed results.
- Fresh schema adds NULLS NOT DISTINCT event uniqueness, address/as-of/token/status constraints and fee/slippage/gas fields. Migration 002 is included and designed for repeat application.
- PostgreSQL 16 CI service and constraint/migration probes added.

## Local verification
- `python -m pytest -q`: 62 passed, 2 skipped. Both skips are PostgreSQL integration tests because no local PostgreSQL server/client or psycopg driver was available in this runtime.
- `python -m compileall -q app tests`: passed.
- Manual mutation-style guard probes: zero, negative, NaN, infinite prices and inconsistent OHLC rejected. This is not a full mutation-testing framework run.

## Important limits
- I could not execute the migration against a live PostgreSQL instance in this runtime. The CI workflow is configured to run these tests on PostgreSQL 16, but until that CI job runs green, do not treat migration compatibility as proven.
- Paper price book is in-memory and resets on restart; replay ingress is for local research and must not be exposed publicly.
- No real blockchain ingestion or live trading was added.
