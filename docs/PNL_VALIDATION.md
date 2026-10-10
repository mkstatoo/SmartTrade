# Wallet PnL: how the numbers were validated

All ledgers below are accounting fixtures (made-up numbers chosen so they can be checked by hand). They say nothing about real wallets.
**Not done:** comparison with an external tracker on real wallet samples - the build environment had no chain/indexer access. Do this before trusting the output for real wallets (see "Independent samples to bring").

## Worked example 1 (also `tests/test_pnl.py::test_example1_*`)
Ledger: buy 10 for $100 (fee $1); buy 10 for $200 (fee $1); sell 15 for $450 (fee $3); mark price 25.

* Buy fees are capitalised: lot 1 basis 101 (10.10/unit), lot 2 basis 201 (20.10/unit). Sell fee is deducted: net proceeds 450 - 3 = 447.
* **FIFO**: cost of the 15 units = 101 + 5 x 20.10 = 201.50 -> realised 447 - 201.50 = **245.50**. Remaining 5 units basis 100.50, value 125 -> unrealised **24.50**. Total **270**.
* **Average**: basis per unit 302 / 20 = 15.10; cost of 15 units = 226.50 -> realised **220.50**; remaining basis 75.50 -> unrealised **49.50**. Total **270**.
* Cash-flow identity (independent of lot matching): -101 - 201 + 447 + 125 (remaining value) = **270** for both methods. The method only moves PnL between realised and unrealised.

## Worked example 2: initial balance and sold tokens (`test_example2_*`)
The wallet starts with 100 units; the ledger sells 40 for $400 (fee $4); mark 11.
* Basis of the starting balance unknown: net proceeds 396 are reported as `realized_unknown_basis_proceeds_usd`; realised PnL **0**; the remaining 60 units are shown as unknown-basis value 660 and unrealised PnL **0** - the system never fakes a gain.
* Starting balance with `unit_cost_usd = 5`: realised 396 - 40 x 5 = **196**; unrealised 60 x 11 - 60 x 5 = **360**.

## Worked example 3: selling more than held (`test_example3_*`)
Buy 5 for $50, sell 8 for $120, mark 1. Only 5 of the 8 units have a known origin: realised = 5/8 x 120 - 50 = **25**; the other 3/8 x 120 = **45** is `unknown_basis_proceeds`; an `oversold` data error (missing_qty = 3) is raised.

## Worked example 4: transfers and fees (`test_example4_*`)
Buy 10 for $100. Transfer out 4 (gas $2), mark 12: `no_pnl` keeps basis with the tokens (40 leaves, 60 stays), expense 2, total = 6 x 12 - 60 - 2 = **10**. With `dispose_at_value` (transfer valued at $60): realised (60 - 2) - 4 x 10 = **18**. Transfer in 3 units valued at $33 then sold for $60: `unknown_basis` -> realised 0, unknown proceeds 60; `fair_value` -> realised **27**; with `cost_basis_usd = 30` -> realised **30**. A standalone fee of $7 followed by a $10 buy marked at 10 gives total **-7**.

## Automatic checks
| check | what it proves |
|---|---|
| 3000 random ledgers (1500 per method) vs `tests/reference_pnl.py` | an independent implementation (exact `Fraction`, unit-by-unit lot walking, written without sharing code) gives the same realised / unrealised / unknown-basis / remaining-qty numbers |
| conservation identity on every case | cash in/out + remaining value = realised + unrealised, recomputed without lot matching |
| metamorphic: scaling USD x3 / quantity x7 | PnL scales x3 / unchanged |
| splitting a sell pro rata | FIFO realised unchanged |
| FIFO vs average | same total, different split |
| bad data: oversell, duplicate (tx, log, kind, token), malformed rows, out-of-order input, missing mark price | flagged in `data_errors` / `checks`, never silently absorbed or guessed |

## Independent samples to bring (next step)
Pick 3-5 real wallets with a few dozen swaps, export the same ledger from a source you trust (DEX explorer CSV, an exchange export, or a tracker), and compare per-token realised PnL under the same basis method and fee treatment. Differences normally come from: price source for `usd`, treatment of gas, airdrops/transfers (basis policy) and rebasing tokens. Those are exactly the knobs exposed here.
