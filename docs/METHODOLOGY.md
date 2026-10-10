# Methodology

## A. What counts as a good wallet?

A wallet is not considered elite from one profitable trade. Minimum recommended gates:
- >= 20 scored events for a mature score
- positive realized or mark-to-market PnL
- no obvious team/treasury/CEX/router identity
- repeated entry behavior
- acceptable copyability

For smaller samples the score is shrunk toward 50 to reduce one-hit-wonder bias.

## B. What counts as a successful entry?

For every observed BUY/CEX_OUT event:
1. Freeze all information at event timestamp.
2. Detect the follower's possible execution timestamp = event timestamp + configured detection latency.
3. Apply slippage and fees.
4. Measure forward returns only after the entry timestamp.
5. Label hit if forward max return exceeds target within horizon.
6. Separately record adverse excursion and time-to-target.

## C. No look-ahead

Never use:
- future whale activity
- future price
- future token liquidity
- future wallet labels
- future realized PnL

to construct a signal at time T.

## D. Cohort confirmation

A single wallet cannot create a BUY signal. Strong signals require at least two independent wallets.
Three or more independent wallets increase confidence, but correlated wallets must be clustered.

## E. Copyability

A leader's PnL is not follower PnL. The backtest must model:
- detection latency
- block latency
- slippage
- DEX fee
- priority/gas fee
- liquidity
- partial fills
- price impact
- token taxes/restrictions where applicable

## F. Risk controls

Default paper rules:
- max 5% portfolio allocation per signal
- max 15% total portfolio exposure (across all tokens); entries below $25 notional are refused (dust)
- no averaging down
- cooldown after stop
- reject low-liquidity tokens
- reject if smart-money cohort is already distributing
- reject if price is too far above the first accumulation zone

## G. Live trading gate

Live execution should remain disabled until:
1. >= 90 days out-of-sample paper test
2. >= 100 qualified signals
3. positive net PnL after fees/slippage
4. profit factor > 1.2
5. max drawdown acceptable
6. no material performance collapse after latency stress test
7. manual review of false positives



## Time-based exit (v0.4.3)
`expires_ts = entry_ts + max_hold_sec` (entry_ts = when the entry price became known, i.e. the END of the bar whose close was used). A bar is evaluated in this order: stop, target, then deadline. If none of the first two fired and `bar.end_ts >= expires_ts`, the position leaves at that bar's close with exit slippage, fee and gas. A bar ending exactly at the deadline closes the position; a bar ending earlier does not. Deadlines that fall inside a bar close the position at the end of that bar. Time exits never start a cooldown.

## Candle-independent exit and stale price (v0.4.4)
A position whose `expires_ts` has passed is closed by the sweeper even when its token produced no new bar. The exit price is the last known close (the freshest price the engine has ever seen), the exit slippage/fee/gas model is the same as for bar exits, and the closed trade carries `price_basis='stale_last_close'` and `price_age_sec = now - end of that bar`. Such trades must be read as "closed at an old price", not as executed quotes; reports should be able to split them from `price_basis='bar'` trades. A bar that arrives later for an already closed position is ignored for that position.

## Wallet PnL accounting (v0.4.4)
Cost basis is FIFO (default) or average. Buy fees (and gas) increase basis; sell fees reduce proceeds. Tokens received by transfer have an *unknown basis* unless the caller supplies `cost_basis_usd` or chooses `fair_value`; selling them produces `unknown_basis_proceeds`, which is reported separately and never counted as profit. Transfers out are `no_pnl` (basis leaves with the tokens) or `dispose_at_value`. Selling more than held is an `oversell` data error: the excess is not given a basis. Rows repeating (tx_hash, log_index, kind, token) are duplicates and are dropped with a warning. A conservation identity (cash in/out vs. positions vs. realised + unrealised) is recomputed without lot matching and must hold. See `docs/PNL_VALIDATION.md`.

## Walk-forward (v0.4.4)
1. Phases come from the timestamps of BUY events (train / validation / test fractions), not from wall time.
2. A trade's reach = latency + entry delay + horizon. Events whose reach crosses their phase end are purged (embargo); bars beyond the phase end are removed before the backtest runs, so nothing after the phase can influence it (tested by mutating all future data and requiring identical results).
3. Parameter grid is evaluated on train only; validation is the gate (selected parameters must still pass there); the out-of-sample phase is evaluated once with the frozen parameters.
4. Sensitivity (latency x slippage grid) is a diagnostic on the OOS phase and is never used for selection.

## On-chain raw layer (v0.4.4)
Raw logs are stored first with (chain, block_hash, block_number, tx_hash, log_index, address, topics, data, RPC source); decoding is a separate, versioned step. Only blocks `confirmations` deep are read. If the stored parent no longer matches the node, blocks above the fork are marked `canonical=false` (never deleted) and re-read. Consumers must use `chain_logs_canonical`. A `Swap` log describes the pool, not a wallet; attributing it to a wallet needs `tx.from`/router context that is not ingested yet.

