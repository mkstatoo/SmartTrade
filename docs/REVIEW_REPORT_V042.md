# v0.4.2 – review of v0.4.1 and what was executed

## Evidence run on real PostgreSQL 16.15 (local cluster)
| Check | Result |
|---|---|
| v0.4.1 `schema.sql` / PG test on real PostgreSQL | failed (schema stale vs. migration) |
| v0.4.2 `schema.sql` fresh, then run a 2nd time | OK, no change |
| v0.3 DB -> 001,002,003 ; repeat x2 | OK; repeat = "nothing" |
| v0.4 DB -> 002,003 ; repeat x2 | OK after fixing runner bug (001 re-ran on 2nd run) |
| fresh vs migrated schema | identical columns, constraint definitions, index definitions (constraint *names* differ on legacy DBs; v0.4 keeps redundant duplicate CHECKs) |
| Probes on every DB kind (fresh/v0.3/v0.4) | NULLS NOT DISTINCT duplicates rejected; BUY+SELL same log allowed; EVM mixed-case rejected; FKs (signals, paper_trades, events->tokens); CHECKs (as_of<=ts, status, negatives, OHLC, NOT NULL); PK includes timeframe |
| Legacy rows | mixed-case wallets merged, null-volume bar quarantined, signal kept & token registered |
| Real process restart (uvicorn kill/start) | position, price book persisted; stop still fires |
| pytest | 160 passed (with PG) / 73 passed + 87 skipped (without) |
| CI emulation `scripts/ci_local.sh` | OK (migrate x2, pytest with no skips); `actionlint` + YAML parse OK |
| Mutation checks | 10/10 injected bugs detected |

## Not executed (honest limits)
GitHub Actions itself and Docker/compose could not run here (no Docker daemon, no GitHub runner). Python 3.13 locally vs 3.12 in CI. Bars in tests are deterministic engine fixtures, not market data.

## Defects found in v0.4.1 and fixed
1. Fill price (with slippage) was written into the market price book -> later marks/exposure contaminated.
2. Bars formed before the entry could trigger stop/target (look-ahead); now `entry_ts` = time entry price became known, bars must open >= it.
3. Exit slippage/fee/gas asymmetry vs. backtest.
4. Portfolio/price book in memory (lost on restart) -> PostgreSQL.
5. Freshness could not work for historical replay -> `replay` clock.
6. API key exposed through `/config`; duplicate Config fields.
7. `schema.sql` did not match migrations; migration re-run hazards.
8. Dust entries (exposure room of a few dollars) paid more gas than notional (found by the new tests) -> $25 minimum.
