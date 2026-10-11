# Smart Copy Trading v0.4.5

Research/paper-only crypto wallet intelligence system. **Live execution is permanently disabled.** Since v0.4.4 the raw on-chain layer has been run on real Ethereum and Base data (GitHub Actions, see `docs/LIVE_TEST_2026-10-11.md`); v0.4.5 adds wallet attribution and USD pricing for a verified watch-list of Uniswap V2/V3 pools on Ethereum (`docs/WALLET_ATTRIBUTION.md`). Not yet done: Base attribution, behaviour-based wallet selection, comparison with an external PnL tracker, a real reorg observed on a live chain.

## What v0.4.5 adds
- **Market layer** (`app/chain/market.py`): pools are accepted only if the Uniswap factory itself returns the same pool address for its tokens; reference tokens (WETH, USDC, USDT, DAI) are re-checked on-chain (symbol, decimals) at run time; USD value comes from execution prices of the swaps themselves (stables = 1 USD, ETH from WETH/stable swaps with an outlier filter). Chainlink is used only as an independent cross-check.
- **Attribution pipeline** (`app/chain/pipeline.py`): `discover_pools` (rank, verify, top-K by USD volume + ETH reference pools) -> `collect_txs` (receipts: `tx.from`, `tx.to`, status, gas, ERC-20 transfers; cross-checked against the stored `eth_getLogs` view) -> `derive_trades` (wallet = `tx.from`; a trade is `confirmed` only when the sender's own Transfer delta matches the priced swap flow within 2%, `mismatch` otherwise; everything else is stored in `chain_trade_skips` with a reason) -> `wallet_pnl` (confirmed trades into `app.pnl`).
- **Migration 006** (`chain_tokens`, `chain_pools`, `chain_txs`, `chain_transfers`, `chain_trades`, `chain_trade_skips`, view `chain_trades_canonical`); fresh schema equals migrated schema from every baseline.
- **Real-run script** `scripts/market_run.py` (+ workflow step): independent checks of ETH price vs Chainlink, receipts and `tx.from` re-fetched through a second provider, `balanceOf` state before/after the block vs the log-based delta, cross-pool price consistency, attribution rates. Endpoint URLs and hosts never reach the reports.
- Provider selection now prefers keyed private endpoints as primary (public gateways rate-limit during long runs).
- Tests: a synthetic world with hidden true prices and ground-truth trades (direct, router with fee, relayer, two-hop, arbitrage, quote-for-quote, impostor pool, manipulated ETH print); 23 mutation checks.

## What v0.4.4 adds
- **Engine safety**: *every* route except `GET /health` needs `X-Research-Key` (constant-time compare; 10 failures / 60 s per client -> `429`); `/health` is minimal (status/mode/live_execution); `GET /status` (auth) shows store connectivity; OpenAPI/docs are disabled; request bodies are capped (32 MiB, `413`) and list sizes bounded. `GET /config` returns the effective config, its SHA-256 and which whitelisted env overrides were applied; invalid values stop the process at start (`ConfigError`). `live_execution` can never be `True`.
- **Database failure behaviour** (tested on PostgreSQL): unreachable DB / killed backend / read-only DB -> `503` + `Retry-After: 5`; integrity or other SQL errors -> generic `500`; neither leaks DSN, SQL or tracebacks; lock/statement timeouts; a failed request leaves no half-written state and the same app instance recovers by itself when the database returns.
- **Candle-independent exit**: a background sweeper (`PAPER_SWEEP_INTERVAL_SEC`, default 30 s, live clock only) and `POST /paper/sweep` close positions whose `expires_ts` has passed even if no new bar arrived. Such exits use the last known close and are labelled `price_basis='stale_last_close'` with `price_age_sec` on the closed trade - they never pretend to be a fresh quote.
- **Wallet PnL** (`POST /wallet/pnl`, `app/pnl.py`): Decimal accounting over a ledger of buys, sells, transfers in/out and fees; FIFO or average cost; buy fees capitalised, sell fees deducted; explicit policies for transfers (`unknown_basis`/`fair_value`/`cost_basis_usd`; `no_pnl`/`dispose_at_value`); initial balances; unknown-basis proceeds reported separately instead of invented profit; oversells and duplicate rows (same tx/log/kind/token) flagged; a cash-flow identity is checked independently of lot matching. Validated against an independent unit-by-unit `Fraction` implementation (`tests/reference_pnl.py`) on 3000 random ledgers and hand-computed examples (`docs/PNL_VALIDATION.md`).
- **Walk-forward without look-ahead** (`POST /backtest/walkforward`, `app/walkforward.py`): train / validation / out-of-sample phases split on BUY-event time; events whose whole life (latency + entry delay + horizon) would cross a phase end are purged; bars are clipped at the phase end; parameters are chosen on train only, the validation gate decides, OOS is run exactly once; latency x slippage sensitivity grid is reported as a diagnostic.
- **Raw chain ingestion** (`app/chain/`, `python -m app.chain --chain eth`): JSON-RPC source (URL from `CHAIN_RPC_URL`, never stored/printed), confirmations depth, resumable cursor, parent-hash continuity, reorg walk-back (orphaned blocks kept with `canonical=false`, `chain_reorgs` audit rows), refetch when logs and headers disagree, per-chain advisory lock, adaptive batch halving, strict decoders for ERC-20 `Transfer`, Uniswap V2/V3 `Swap` (topic hashes verified by keccak256 in tests); undecodable logs are recorded in `chain_decode_errors`.
- **Deployment tests** on a real PostgreSQL cluster that the tests start/stop themselves: upgrade from each older schema and then use the service; `pg_dump`/`pg_restore` with per-table content hashes; hard crash (`pg_ctl -m immediate`) with concurrent writers and automatic recovery of the running app; clean restart.

## What v0.4.3 added
- **Numeric validation**: NaN / +-Infinity (also as strings) are rejected in every model with a standard `422 {"detail":[{loc,msg,type}]}` (the offending input is not echoed). Sane upper bounds on prices, USD amounts, timestamps, percentages (stop-loss < 100, slippage < 10000 bps) remove several other paths that used to end in HTTP 500.
- **Time-based exit**: every position has `max_hold_sec` (per signal, default `paper_max_hold_sec` = 24h, same as the backtest horizon) and `expires_ts = entry_ts + max_hold_sec`. The first bar whose END >= `expires_ts` closes it at that bar's close (reason `time`); stop/target of that bar win first; no cooldown after a time exit. Evaluated when that token's bars arrive.
- **One token identity** (`app/ids.py`): EVM contracts/addresses are lower-case everywhere (API, store, backtest, and `CHECK` constraints on `tokens` and `price_bars`); Solana-style ids keep their case. Migration 004 merges legacy mixed-case rows (bar duplicates go to `legacy_quarantine`).
- **Independent PostgreSQL verification**: `python scripts/pg_verify.py` boots its own temporary cluster and writes the raw test output to `docs/PG_EVIDENCE.txt`; new concurrency / rollback / concurrent-migration tests.

## What v0.4.2 added
- **Durable state**: portfolio, positions, price book, cooldowns, bars, signals, fills and closed trades live in PostgreSQL (row-locked unit of work; safe across restarts and several workers). No database configured => the API refuses to start (`STORE_BACKEND=memory` is an explicit throw-away opt-in).
- **Migration runner** `python -m app.migrate`: empty DB -> `schema.sql`; v0.3 -> 001..006; v0.4/v0.4.1 -> 002..006; v0.4.2 -> 004..006; v0.4.3 -> 005..006; v0.4.4 -> 006; repeat runs are no-ops; legacy rows that violate new constraints go to `legacy_quarantine` (nothing silently dropped).
- Paper engine fixes found in the v0.4.1 review (see `docs/REVIEW_REPORT_V042.md`).

## Run
```bash
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://user:pass@host:5432/db PAPER_API_KEY=<long random>
python -m app.migrate
uvicorn app.main:app
```
`PAPER_CLOCK=live` (default) uses wall time; `replay` uses the latest ingested bar end as "now" (for historical bars; never mix on one portfolio).

## Tests
```bash
python -m pytest -q                                   # PG tests are skipped without TEST_DATABASE_URL
TEST_DATABASE_URL=postgresql://user@host/postgres scripts/ci_local.sh   # emulates CI, fails on any skip
```
Docker: copy `.env.example` to `.env`, then `docker compose up --build` (the API container runs migrations first).

## API (paper)
`POST /paper/replay/bar` (auth) -> `POST /paper/signal` (auth) -> stop/target evaluated atomically at bar ingest -> `GET /paper`. Also: `/status`, `/config`, `/score`, `/backtest`, `/backtest/walkforward`, `/wallet/pnl`, `/paper/mark`, `/paper/sweep` (all need the key).
`POST /paper/exit/{chain}/{token}` accepts only `manual`/`risk` (stop/target/time are engine-only). `/paper/step` was removed.
Prices are never client-supplied for entries; a fresh trusted bar close must exist.

## Execution model (identical to the backtest)
Entry fill = close*(1+slippage); fee bps + gas per side; exit = level*(1-slippage); stop before target in one bar; gaps fill at bar open; a bar counts only if it opened at/after the time the entry price became known (no look-ahead). Time exit: see above. Sizing: 5% per signal, 15% total exposure, $25 minimum notional. These are research assumptions, not exchange behavior.

## Known limitations
- **No real-chain validation.** Ingestion was verified only against a scripted fake chain and a local mock JSON-RPC server; no real endpoint was reachable. Public RPCs differ (log limits, pruning, finality, `removed` flags), so a first real run needs supervision.
- Swaps are stored/decoded as *pool* events. Wallet attribution (`tx.from`, routers, aggregators), token decimals/metadata and USD pricing are **not** implemented, so the PnL endpoint takes a ledger supplied by the caller; it has not been compared with an external tracker on real wallet samples.
- Walk-forward / PnL results on synthetic fixtures prove the mechanics, not any trading edge.
- Stale-price sweep exits use the last known close; a gap since that bar is not reflected (it is labelled, not hidden).
- Time/stale exits still need `PAPER_CLOCK=live` for the background sweeper; with the replay clock use `POST /paper/sweep`.
- GitHub Actions and Docker were not executable in the build environment (workflow YAML parsed, logic reproduced locally by `scripts/ci_local.sh` and `scripts/pg_verify.py`); local Python is 3.13, CI uses 3.12.
- After a hard database crash PostgreSQL may skip ahead in sequences (ids have gaps, never repeat).

## Not in this version
Wallet clustering, DEX pair discovery, historical liquidity snapshots, CEX flow classification, a market-data adapter and any live execution (stays disabled).
