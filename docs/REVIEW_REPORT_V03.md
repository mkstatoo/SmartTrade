# Expert Review — smart_copy_trading v0.3

## Verification performed
- v0.2 was extracted and executed.
- Baseline test suite: 42 passed.
- v0.3 regression suite: 46 passed.
- The review did not treat green unit tests as proof of market-data correctness.

## v0.2 fixes independently verified
1. Token isolation in backtest.
2. Follower-side execution with latency and max entry delay.
3. Costs, stop/target/horizon exits, MAE/MFE and skip reasons.
4. Server-side liquidity and confidence; client spoofing rejected.
5. Confirmation counting is cluster-aware at the scoring layer.
6. Distribution can block a cohort.

## v0.3 changes
### A. Paper accounting
Paper portfolio now tracks:
- cash
- market exposure
- equity
- realized PnL
- unrealized PnL
- peak equity
- max drawdown
- closed trades

The portfolio enforces:
- default 5% allocation per signal
- maximum 15% token exposure
- no averaging down while a token is open

### B. Temporal guard
Wallet statistics can carry `as_of_ts`. If a signal has `signal_ts`, statistics newer than the signal are rejected.

Important: this prevents an explicitly future-dated record from entering the API, but it does NOT generate historically correct statistics. The producer must still calculate WalletStats using only data available at T.

### C. Database model correction
The SQL schema now distinguishes:
- chain + wallet address
- chain + token contract
- transaction hash + log index

This avoids cross-chain collisions and the one-tx/multiple-event uniqueness problem.

### D. Container hardening
- non-root API
- Postgres healthcheck
- schema initialization
- no Postgres host exposure
- required password environment variable

## Remaining critical gaps

### P0 — Data truth
The application still needs a raw blockchain/indexer ingestion layer. Until raw logs/fills are stored, wallet PnL and wallet skill are research inputs rather than independently verified facts.

### P0 — As-of statistics
The API guard is not enough. WalletStats must be generated with an as-of query:
`events.ts <= signal_ts`.
Leaderboard selection must also be performed independently for every historical timestamp to avoid survivorship bias.

### P0 — DEX decoding
BUY/SELL must come from decoded swap events and token deltas, not from generic transaction methods alone. Router calls, multicalls, aggregators and LP actions must be separated.

### P1 — Entity clustering
`cluster_id` is currently an input. It is not discovered by the system. Independent confirmations therefore depend on the upstream clustering quality.

### P1 — PnL ledger
A production ledger needs:
- token contract + chain
- decimals
- exact base/quote deltas
- gas
- fees
- FIFO or weighted-average cost policy
- realized/unrealized PnL
- transfers excluded from trading PnL
- LP operations excluded or separately accounted

### P1 — Persistence
The PostgreSQL schema is corrected and initialized by Compose, but the FastAPI application is still in-memory. A repository/SQLAlchemy layer is the next engineering step.

### P1 — Research validity
Next research layer should include:
- walk-forward splits
- OOS-only reporting
- latency stress tests
- slippage stress tests
- bootstrap confidence intervals
- regime segmentation
- false-positive review
- multiple-testing correction when searching hundreds of strategies

### P2 — Security/operations
Before any live integration:
- authentication
- authorization
- rate limiting
- audit logs
- secret management
- kill switch
- maximum daily loss
- maximum position size
- live execution remains disabled

## Decision
v0.3 is suitable as a research/paper-accounting foundation, NOT as a live trading system and NOT as evidence of profitable wallet-copying performance.
