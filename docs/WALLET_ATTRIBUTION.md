# Wallet attribution (v0.4.5): method, real-chain results, limits

All numbers below are measurements of ONE real run (GitHub Actions job `live-chain-test`, 2026-10-11, Ethereum mainnet, blocks 26,168,026-26,169,825: 300 blocks of discovery + 1,500 blocks of watching, about 6 hours of chain). They describe that window only. Nothing was tuned to make them look better, and no market data is hard-coded: the only constants are five contract addresses that are re-checked on-chain at every run.

## Method
1. **Discovery.** All Uniswap V2/V3 `Swap` logs of the discovery window are stored. Candidates (top 300 pools by swap count) are accepted only if the pool says which factory made it AND that factory (`getPool` / `getPair`) returns the same pool address for the pool's tokens. Token symbol/decimals are read on-chain. Swaps are valued in USD from their own execution price: USDC/USDT/DAI = 1 USD, WETH priced from swaps in WETH/stable pools (dust swaps below 0.05 WETH ignored, a point more than 3% from the median of its neighbours dropped). The top 30 pools by USD volume with exactly one quote leg become the watch-list; the most active WETH/stable pools are added as price references.
2. **Watching.** Swap logs of the watch-list only (address-filtered `eth_getLogs`). For each transaction the receipt is fetched (`from`, `to`, status, gas, every ERC-20 `Transfer` of the watched tokens) and cross-checked against the logs already stored; a disagreement rejects the transaction.
3. **Trades.** wallet = `tx.from`. For each non-quote token the net flow of all priced swaps in the transaction is compared with the sender's own `Transfer` delta of that token: same direction and within 2% -> `confirmed`; otherwise `mismatch`; zero delta -> not attributed (`no_sender_transfer`). Other stored reasons: `quote_only` (WETH/stable swap), `zero_net_flow` (round trip), `no_quote_leg`, `no_eth_price`, `degenerate_swap`, `tx_failed`. Gas is priced once per transaction at the swap-derived ETH price.
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

A smaller earlier run (300 blocks) gave the same picture (1,087 confirmed of 1,099; Chainlink median 0.03%; state check 60/60).

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
