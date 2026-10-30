# Multi-day collection and the walk-forward test

**Question this answers:** do wallets that looked skilled in the first part of a long history keep doing better in the second part, after the costs a
follower would pay? One pre-specified test; "no evidence" is an acceptable and expected answer.

## Collection
* `.github/workflows/live-test.yml` runs the real Ethereum pipeline (≈ 13 h of blocks per run). `deploy/scheduled-live-test.yml` (installed on the
  default branch) starts it twice a day (02:30 and 14:30 UTC) so consecutive runs overlap slightly.
* Each run exports its trades (`reports/trades_ethereum.jsonl.gz`) and appends them to the branch **`live-test-data`** (append-only, one file per run).
* The same job then runs `scripts/aggregate.py` over all stored files and publishes `reports/aggregate.json|md` on `live-test-reports`.
* Overlapping runs are merged by (tx, token, wallet, side); contradicting duplicates are counted and reported; files of an older `method_version`
  are ignored (reported in `ignored_older_method_files`).

## The test (fixed before any real multi-day data exists)
1. Only confirmed trades. Split the history in time at the midpoint.
2. Eligible = ≥ 5 closed trades of fully known cost before the split (only the past decides eligibility).
3. Selected = eligible wallets with positive realized PnL before the split, best return first, top min(20, 10 % of eligible).
4. Evaluate on closed trades after the split (lots bought earlier carry over); wallets inactive after the split count as 0.
5. Control: 20 000 random sets of the same size from the eligible wallets (fixed seed) → p-value. Also Spearman rank correlation of before/after returns,
   and results after follower haircuts of 0 / 0.3 % / 1 % per leg.
6. Verdict: `insufficient_data` (history < 14 days, < 100 eligible or < 10 selected) · `signal` (p < 0.05, mean after 0.3 % haircut > 0, rho > 0) · `no_evidence`.
`signal` only means "look closer with more data and another split". It is never a reason to trade.

## What the tests prove (tests/test_aggregate.py, synthetic fixtures with a fixed seed)
Planted skill is found; pure luck is called a signal in ≤ 1 of 12 seeds; skill that vanishes after the split is not a signal; costs can erase a small edge;
the selection is identical when the future is altered (look-ahead guard); mismatch trades are ignored; overlapping runs merge once.
A deliberate look-ahead mutation (selecting by the future return) produced 3 false signals in 12 seeds against 0 for the real code.

## Known limits
Only wallets that trade from their own address (≈ 29 % of USD volume) are visible; windows between runs may have small gaps if a run fails; marks for
unrealized PnL are last execution prices (not used in the verdict); no slippage model beyond the fixed haircuts.
