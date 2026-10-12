# Wallet attribution (v0.4.5): method, real-chain results, limits

All numbers below are measurements of ONE real run (GitHub Actions job `live-chain-test`, 2026-10-11, Ethereum mainnet, blocks 26,168,026-26,169,825: 300 blocks of discovery + 1,500 blocks of watching, about 6 hours of chain). They describe that window only. Nothing was tuned to make them look better, and no market data is hard-coded: the only constants are five contract addresses that are re-checked on-chain at every run.

## Method
1. **Discovery.** All Uniswap V2/V3 `Swap` logs of the discovery window are stored. Candidates (top 300 pools by swap count) are accepted only if the pool says which factory made it AND that factory (`getPool` / `getPair`) returns the same pool address for the pool's tokens. Token symbol/decimals are read on-chain. Swaps are valued in USD from their own execution price: USDC/USDT/DAI = 1 USD, WETH priced from swaps in WETH/stable pools (dust swaps below 0.05 WETH ignored; the series is strictly causal: a print is judged only against the median of the previous accepted prints and dropped if it is more than 3% away; the first 5 prints only seed the reference, so a trade before the first usable ETH price is skipped as `no_eth_price` and a later price is never attached to an earlier moment). The top 30 pools by USD volume with exactly one quote leg become the watch-list; the most active WETH/stable pools are added as price references.
2. **Watching.** Swap logs of the watch-list only (address-filtered `eth_getLogs`). For each transaction the receipt is fetched (`from`, `to`, status, gas, every ERC-20 `Transfer` of the watched tokens) and cross-checked against the logs already stored; a disagreement rejects the transaction.
3. **Trades.** wallet = `tx.from`. For each non-quote token the net flow of all priced swaps in the transaction is compared with the sender's own `Transfer` delta of that token: same direction and within 2% -> `confirmed`; otherwise `mismatch`; zero delta -> not attributed (`no_sender_transfer`). Other stored reasons: `quote_only` (WETH/stable swap), `zero_net_flow` (round trip), `no_quote_leg`, `no_eth_price`, `degenerate_swap`, `tx_failed`. Gas is priced once per transaction at the swap-derived ETH price (causal, as above) and attached to the first CONFIRMED trade of the transaction, so PnL, which reads only confirmed trades, never loses it; a transaction with only mismatched trades is excluded from PnL together with its gas. If no ETH price existed yet the gas is 0 and flagged (`gas_unpriced_trades`).
4. **PnL.** Confirmed trades per wallet go through `app.pnl.compute_pnl` (FIFO), marks = last observed execution price.

## Real-run results (Ethereum, window above)
| item | result |
|---|---|
| swap logs: discovery / watch | 6,543 / 13,962 (0 decode errors, 0 reorgs seen) |
| candidates / verified through the factory / rejected | 300 / 264 / 36 |
| pools watched | 33 (30 by volume + 3 ETH references) |
| receipts stored / errors / disagreeing with `eth_getLogs` | 11,799 / 0 / 0 |
| trades | 2,630: 2,501 confirmed, 129 mismatch |
| swap txs (excluding WETH/stable) that became a trade | 50.5% |
| wallets with a confirmed trade | 1,088 |
| ETH price from swaps vs Chainlink (6 recent blocks) | median 0.14%, max 0.16% (pass; Chainlink only updates on 0.5% moves) |
| second provider: 50 receipts (from, status, gas, every watched transfer) and 50 `tx.from` of trades | 0 differences |
| `balanceOf` after minus before the block vs the log-based delta (60 trades in the last 100 blocks) | 58 exact; the 2 others have a state delta exactly twice the log delta and identical numbers, consistent with two transactions of the same wallet in the same block (not verified individually) |
| same token, same 20-block bucket, two different pools: price deviation | median 0.08%, p90 0.43%, max 1.40% (79 buckets, 5 tokens) |
| PnL | 403 closed trades, only 36 with a known cost; 559,816 USD of sells have an unknown basis |

The tables above come from the run with the earlier (non-causal) outlier filter. A smaller earlier run (300 blocks) gave the same picture (1,087 confirmed of 1,099; Chainlink median 0.03%; state check 60/60).

## Final version: causal pricing and the ~13-hour run with profit and loss
Review points applied before this run: (1) the ETH price is strictly causal (see Method; nothing later can reach an earlier moment, proven by a regression test that shocks ETH by +60% after a block and shows every earlier trade is byte-identical), (2) gas stays on a confirmed trade, (3) PnL was checked against an independent exact-fraction implementation on the derived ledgers (FIFO and average cost agree for every wallet).

Run: Ethereum blocks 26,168,191-26,172,090 (300 discovery + 3,600 watch, about 13 hours), job `live-chain-test` on 2026-10-11. The report file of this run was later overwritten by a failed re-run (see below), so the figures here were copied from the job output at the time.

| item | result |
|---|---|
| receipts stored / errors / disagreeing with `eth_getLogs` | 29,291 / 0 / 0 |
| trades | 5,421: 5,196 confirmed (95.9%), 225 mismatch |
| skipped (tx level reasons) | `quote_only` 19,468, `no_sender_transfer` 6,346, `zero_net_flow` 128 |
| non-quote swap txs that became a trade | 55.2% |
| wallets seen / with a confirmed trade | 1,843 / 1,712 |
| ETH price points (causal) / dropped as outliers | 12,704 / 4 |
| Chainlink cross-check, second-provider re-fetch of receipts and `tx.from` | pass, pass |
| same token, two pools, same 20-block bucket | 169 buckets, 3 tokens: median 0.09%, p90 0.31%, max 2.10% |
| `balanceOf` state check | not done in this run (only 1 trade was still inside the node's recent-state window after the slow receipt stage); earlier 1,800-block runs: 60/60 and 58/60 exact. The code now fetches the last 80 blocks first so the check can run; that change is only tested on mock nodes |

**Profit and loss (confirmed trades only, FIFO, execution price, gas included, cost basis only from trades inside the window):**
- 1,887 closed trades in total, but only **642 (199 wallets) have a known cost**; the rest sold tokens bought before the window, their proceeds are reported separately and never turned into profit or loss.
- On those 642: win rate 44.4%, realised result +101,865 USD in total (sum over wallets, dominated by a few wallets with one large trade each).
- Unrealised result of all wallets is +447,728 USD but it is marked at the LAST execution price seen in the window, which in thin meme-token pools is not a price one could sell at: indicative only.
- Typical pattern: wallets with 20+ closed trades, 0 wins and a result of about -8 USD are bots round-tripping dust and paying gas; wallets with +500 to +1,300 USD have one closed trade each. **None of this is evidence of skill; a single window cannot rank wallets.**

A re-run of the same job to repeat the state check failed in `ingest_watch` with HTTP 429 `daily request limit reached` from the public gateway that was chosen as primary (both keyed endpoints were already refused by the probe because of their per-second limits). It is a provider quota problem; nothing in the data or code was at fault.

## What this does NOT show
- About half of the swap transactions are not attributable: the transaction sender is not the owner of the tokens (bots, private contracts, some aggregators). `tx_targets` in `reports/market_run.json` lists the most frequent targets; those that appear only among unattributed transactions are private contracts. Attributing them would need contract-owner resolution, not done.
- The 129 mismatches were not inspected individually (likely fee-on-transfer tokens and router fees above 2%); they are excluded from PnL.
- The window is short: 90% of closed trades have no earlier buy, so their cost is unknown and is NOT turned into a profit or loss. Wallet PnL here is a pipeline check, not a ranking of wallets.
- Only Uniswap V2/V3 on Ethereum; no Base, Sushi, Curve, Balancer or Pancake pools (36 candidates failed factory verification, which is the intended behaviour for non-Uniswap pools).
- No comparison with an external PnL tracker (no internet access from the build environment other than the RPC endpoints).
- Chainlink and `balanceOf` checks only reach recent blocks (non-archive nodes), so they cover the end of the window.
- A real reorg has still not been observed on a live chain.

## Tests behind it
`tests/test_market.py` (selectors verified by keccak, codecs, pool verification against impostors, valuation), `tests/test_pipeline.py` (a synthetic world with hidden true prices: every derived trade equals the ground truth exactly in quantity and within 1e-6 in USD; skips match the expected reasons; manipulated ETH print dropped; orphaned blocks excluded; tampered/missing receipts rejected), `tests/test_live_scripts.py` (the real-run script against local mock nodes, including a lying Chainlink feed, a tampered second provider and a node whose state contradicts the logs). `scripts/mutation_check.py` injects 23 deliberate bugs; all are detected.

## Run of 2026-10-12 (commit "Provider failover…", job 38207590583) — real Ethereum data, all integrity checks passed

300 discovery + 3600 watch blocks (head 26174293), 33 pools, 34 117 receipts (0 errors, 0 inconsistent).
Trades 14 722 (14 463 confirmed / 259 mismatch); skips: quote_only 13 793, no_sender_transfer 7 457, zero_net_flow 180, no_eth_price 5.
Chainlink vs swap-derived ETH price: deviation ≈0.14–0.24 % on samples (pass); second provider: 50/50 receipts and wallets equal;
cross-pool price deviation median 0.065 % / max 0.56 % (243 buckets); **balance-state check on real data: 19 of 19 candidates exact match (pass)**.
Unattributed swap txs (sample 300): final recipient is a contract 207, EOA 18, none 75 → mostly bots/aggregators, so no relayer rule is justified yet.
PnL overview (pipeline check, not a wallet ranking): 471 wallets with a known-cost closed trade, 1 435 closed trades, win rate 50.4 %.
Provider failover (`FailoverSource`) on quota errors is covered by unit tests; this run did not need a switch recorded in the report.

## Base smoke runs (2026-10-12, Option 1 first contact)
Run 1 (600 discovery + 1800 watch blocks, 33 pools): receipts stored 19 243, **errors 1 205** (provider refused older receipts: "archive requests require a personal token"),
trades 12 211 (12 021 confirmed), 279 wallets with a confirmed trade, Chainlink check pass (median 0.17 %), cross-pool price deviation median 0.003 % / max 0.057 %.
The addresses written from memory (factories, WETH, USDC, USDbC, DAI, Chainlink feed) were all accepted by the on-chain checks. The independent second-provider
check **failed** in that run (all 50 receipts refused by the verifier for being too old) → fixed by sampling the newest blocks; the fix is unit-tested but not yet seen
passing on Base. Balance-state check: unavailable. Gas now includes the L1 data fee (migration 007), also not yet seen on real Base data.
Run 2 could not start discovery: the free private endpoint answered "HTTP 402 Out of CU" (credits spent by run 1). Base therefore has NO fully passing real run yet.
The Base step is now opt-in (repository variable RUN_BASE_SMOKE=true). The 5.9 % of Base receipts that could not be fetched are a coverage loss, not a measured result.
Ethereum rerun after the fixes: all integrity checks pass, second-provider 50/50; balance-state check was "unavailable" (0 candidates) this time, unlike the 19/19 run before.
