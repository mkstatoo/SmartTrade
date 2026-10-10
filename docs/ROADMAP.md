# Roadmap

## Phase 1 — Core
- wallet event model
- scoring
- cohort scoring
- follower-side backtest
- paper portfolio accounting
- corrected PostgreSQL schema

## Phase 2 — Data truth (next)
1. Base/Ethereum indexer adapter
2. raw blocks/transactions/logs persistence
3. ERC-20 transfer normalization
4. Uniswap V2/V3 + common aggregator decoding
5. token metadata/decimals
6. DEX pair discovery and historical price/liquidity snapshots
7. CEX deposit/withdraw classification

## Phase 3 — Wallet intelligence
1. as-of wallet statistics engine
2. realized PnL ledger
3. token-specific skill
4. wallet/entity clustering
5. team/treasury/CEX/router/MEV detection
6. distribution and accumulation zones

## Phase 4 — Research engine
1. event study
2. walk-forward validation
3. latency/slippage stress
4. bootstrap confidence intervals
5. regime segmentation
6. false-positive analysis
7. multiple-testing correction
8. strategy leaderboard

## Phase 5 — Persistent paper trading
1. SQLAlchemy repository
2. signal persistence
3. portfolio snapshots
4. trade ledger
5. PnL attribution
6. alerts

## Phase 6 — Mobile
- mobile-first dashboard
- wallet discovery
- wallet detail
- decoded trades
- backtest
- paper portfolio
- alerts

## Phase 7 — Optional live execution
Disabled until all methodology gates pass:
- >=90 days OOS paper
- >=100 qualified signals
- positive net PnL after realistic costs
- profit factor >1.2
- acceptable max drawdown
- latency stress robustness
- manual false-positive review
- explicit user confirmation


## Status after v0.4.4
Done as foundations (synthetic/fake-chain verified only): raw logs persistence with provenance, ERC-20 Transfer and Uniswap V2/V3 Swap decoding, reorg handling, realised PnL ledger, walk-forward harness, stale-price time exits, deployment/crash/restore tests.
Next: run ingestion against a real provider; wallet attribution (tx.from / routers), token metadata/decimals, pool-to-token mapping, USD price source; PnL comparison with an external tracker on real wallets.
