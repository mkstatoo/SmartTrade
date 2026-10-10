# Changelog

## v0.4.0
- Removed client-supplied paper entry/exit prices from signal/exit APIs; paper entries require an internal trusted price already present in the portfolio price book.
- Added finite positive price validation and conservative stop/target execution.
- Persisted last prices in the paper portfolio; GET status is observational.
- Fixed initial cash/peak equity synchronization.
- Changed sizing to equity-based allocation with 15% total portfolio exposure cap; default allocation remains 5%.
- Added stop cooldown.
- Strict as-of provenance: signal_ts is required, future timestamps are rejected, and stale stats are rejected.
- Unknown wallet clusters no longer count as independent confirmations.
- Backtest now deduplicates events, rejects overlapping wallet-token observations, reports effective_n, and keys price data by (chain, token).
- PostgreSQL schema adds tokens, value CHECK constraints, block/reorg provenance, timeframe, auditable stats_as_of_ts, and safer event uniqueness.
- Added v0.4 regression tests and updated README/.env.example/dependency pins.

## Still pending
- Real PostgreSQL repository/SQLAlchemy integration.
- Real blockchain ingestion and event decoding.
- Historical as-of WalletStats calculation from raw events.
- Actual wallet clustering/entity-resolution engine.
- Real market-data adapter and trusted paper price feed.
- Walk-forward/OOS research harness.
- Authentication/rate limiting before any network exposure.


## v0.4.1
- Added authenticated timestamped bar replay ingress and active stop/target evaluation path.
- Added server-only strict as-of limits, fresh-price checks, follower-side fee/slippage/gas assumptions, entry timestamps, and authenticated constrained exits.
- Added exact-timeframe backtest filtering, stronger duplicate handling, successful-trade effective_n, chain normalization and wallet-chain consistency checks.
- Added PostgreSQL schema constraints, migration 002, migration/constraint integration tests, and PostgreSQL 16 CI workflow.
- Local: 62 passed, 2 PostgreSQL integration tests skipped because PostgreSQL was unavailable. No claim of a local live-Postgres run is made.


## v0.4.2
- Persistence: PostgresStore (portfolio, positions, price book, cooldowns, bars, signals, fills, closed trades) with row-lock unit of work; fail-closed startup; MemoryStore only by explicit opt-in.
- Migration runner (`app.migrate`) + migration 003; `schema.sql` rewritten and proven equal (columns, constraint and index definitions) to the v0.3->v0.4.2 and v0.4.1->v0.4.2 migrated schemas on PostgreSQL 16.
- Fixed: fill price no longer overwrites the market price book; look-ahead rule via `entry_ts`; exit slippage/fee/gas symmetric with entry; replay clock for historical bars; API key removed from `/config`; duplicate Config fields; runner bug where a v0.4 DB re-ran migration 001 on second run; dust entries refused (min $25 notional).
- Removed `/paper/step` (stop/target evaluated atomically at bar ingest). Exit API limited to manual/risk.
- Tests: 160 pass with PostgreSQL 16 (73 pass / 87 skip without it); 10 deliberate mutations all detected.


## v0.4.3
- Validation: every model rejects NaN/Infinity (422, standard body, no input echo). Previously `NaN`/`Infinity` in `/paper/replay/bar` or `/backtest` returned HTTP 500 (error serialisation failed). Bounds added for prices, USD, timestamps, counts, percentages (stop-loss < 100, slippage < 10000 bps, ...).
- Time exit (`max_hold_sec`, `expires_ts`), persisted (migration 004 / schema), boundary-tested.
- Canonical token identity (`app/ids.py`) shared by models, API, store, backtest; DB CHECKs on `tokens` and `price_bars`; migration 004 merges legacy mixed-case tokens.
- API: `POST /paper/signal` accepts optional `max_hold_sec`. `unknown`-chain non-0x ids now keep their case (previously lower-cased in the API only).
- Tests: concurrency (identical bar x8, signal x6), rollback on failure, concurrent migrations, v0.4.2 -> v0.4.3 migration, mixed-case legacy merge, 4 baselines (fresh/v0.3/v0.4/v0.4.2) all converge to the same catalog; `scripts/pg_verify.py` evidence.


## v0.4.4
- Security/ops: auth on every route except `/health`; brute-force throttle; request body cap; minimal `/health`, new `/status`; docs/OpenAPI off; validated, whitelisted env config with `/config` hash; DB errors mapped to clean 503/500 (no leaks), DB timeouts.
- Candle-independent exits: sweeper + `POST /paper/sweep`; migration 005 adds `paper_closed_trades.price_basis/price_age_sec`.
- `POST /wallet/pnl`: real-ledger PnL accounting (fees, transfers, initial balances, sold tokens, data errors), validated against an independent reference implementation.
- `POST /backtest/walkforward`: train/validation/OOS split with purge/embargo, bar clipping, latency x slippage sensitivity.
- Raw chain layer (migration 005 / schema): `chain_blocks`, `chain_logs`, `chain_decoded`, `chain_decode_errors`, `chain_cursor`, `chain_reorgs`, view `chain_logs_canonical`; `app/chain` ingest + CLI; decoders for ERC-20 Transfer and Uniswap V2/V3 Swap.
- Deployment tests (own PostgreSQL cluster): upgrade-then-use, dump/restore, crash recovery, restart. CI installs server binaries first and uploads `PG_EVIDENCE.txt`.
- Behaviour changes: all GET routes except `/health` need the key; `/health` no longer exposes config; stale-price exits exist; request/list size limits; invalid env config aborts start.

