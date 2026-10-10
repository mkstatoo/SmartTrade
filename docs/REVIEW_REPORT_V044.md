# Review report v0.4.4

## What was run (real executions in the build environment)
| check | result |
|---|---|
| full suite, PostgreSQL 16.15 | **650 passed, 0 skipped** |
| full suite, no `TEST_DATABASE_URL` | 458 passed, 192 skipped (PG-backed tests) |
| `scripts/ci_local.sh` (migrate twice on fresh DB, suite, no skips allowed) | OK |
| `scripts/pg_verify.py` (own throw-away cluster, 650 tests + migration twice) | PASS, raw output in `docs/PG_EVIDENCE.txt` |
| `scripts/mutation_check.py` (14 deliberate bugs) | 14/14 detected, each by a named test |
| deployment tests (`tests/test_deploy.py`, 9 tests) | pass: upgrade from v0.3/v0.4/v0.4.2/v0.4.3 + use, dump/restore, hard crash, restart |

## What was NOT run / cannot be claimed
* GitHub Actions and Docker (not available here). The workflow YAML parses; its steps are reproduced by `ci_local.sh` / `pg_verify.py`. Local Python 3.13, CI pins 3.12.
* **No real blockchain was contacted** (all RPC/indexer hosts are blocked from the build environment). Ingestion is verified against a scripted fake chain and a local mock JSON-RPC server (retries, malformed replies, id mismatch, oversize, credential-free labels). Topic hashes are checked with keccak256; ABI encodings with an independent encoder.
* **No real wallet samples**: PnL is validated against hand-computed examples and an independent reference implementation, not against an external tracker.
* All bars, ledgers and chains in tests are labelled engine-test fixtures; nothing in `app/` generates data.

## Roadmap items -> what changed
1. **Engine safety.** Auth on all routes except `/health` (route-introspection test), throttle, body cap, validated env config with SHA-256, DB failures -> 503/500 without leaks, timeouts, read-only DB handling, retry safety, same app instance heals after DB returns (tests on PG: unreachable DB, backend killed before commit, lock timeout, statement timeout, integrity error, read-only DB, failure bursts).
2. **Candle-independent exit.** Sweeper loop + `POST /paper/sweep`; stale exits labelled (`price_basis`, `price_age_sec`, migration 005).
3. **Real data connection.** `app/chain` (RPC source, ingest, decoders, CLI) + tables with tx hash / block number / block hash / log index / source. Reorg walk-back keeps orphaned blocks as `canonical=false`. Found and fixed while testing: a node whose head falls below stored blocks (shorter reorg) was not detected when there was nothing new to ingest; the reorg check now also runs before the loop and treats "node behind stored chain" as a reorg.
4. **Wallet PnL.** `app/pnl.py` + `POST /wallet/pnl`; 3000 differential random ledgers, identities, metamorphic tests (`docs/PNL_VALIDATION.md`).
5. **Walk-forward.** `app/walkforward.py`; future-mutation invariance, purge, single OOS run (spy on the backtest), sensitivity grid.
6. **Deployment.** See table; crash test with concurrent writers: every acknowledged write durable, no duplicates, no 5xx other than the intended 503.

## Findings during the work (worth knowing)
* After `pg_ctl -m immediate` PostgreSQL advanced sequences by up to 32 (pre-logged values). Gaps are normal; the test asserts they never move backwards.
* The old "every route needs the key" test started failing once the route count exceeded the throttle limit (10 failures/min): the test, not the product, needed a fresh app per probe.
* Walk-forward, PnL and ingestion edge cases found by tests are listed in the CHANGELOG-adjacent test names; no known failing case remains.

## Behaviour changes to be aware of
All GET routes except `/health` need `X-Research-Key`; `/health` is minimal; docs/OpenAPI are off; invalid env values stop startup; request size/list caps; stale-price time exits exist; migration 005 adds columns and chain tables.

## Open questions for the next stage
Which chain(s) and which RPC/indexer provider (log-range limits, archive depth, rate limits) will be used, because a first real run must be supervised; then: tx.from/router attribution, token decimals, pool->token mapping and a price source to turn swaps into wallet ledgers that `/wallet/pnl` can consume.
