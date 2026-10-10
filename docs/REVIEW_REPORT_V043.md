# v0.4.3 – what was found, changed and executed

## Found by running v0.4.2 (before the fix)
| Input | v0.4.2 behaviour |
|---|---|
| `NaN`, `Infinity`, `-Infinity` as a float in `/paper/replay/bar` | HTTP 500 |
| `Infinity` for `slippage_bps` or `NaN` for `stop_loss_pct` in `/backtest` | HTTP 500 |
| (strings `"nan"`/`"inf"`) | accepted by Pydantic lax mode, then rejected later by accident |
| huge `ts` (1e30), price 1e13+, stop-loss >= 100% | paths to 500 / invalid prices |
| mixed-case EVM token in `tokens` / `price_bars` | stored as distinct assets |
| `time` exit reason existed in the schema but nothing produced it | positions could be held forever |

## Changes
Stage 1 (numbers): `StrictModel(allow_inf_nan=False)` base, bounds, custom `RequestValidationError` handler (drops `input`/`ctx`).
Stage 2 (PostgreSQL): see `docs/PG_EVIDENCE.txt` (raw output of `scripts/pg_verify.py` on a self-booted PostgreSQL 16 cluster).
Stage 3: time exit + canonical token id + migration 004.

## Mutation checks (each injected bug must make the suite fail)
allow_inf_nan removed; validation handler removed; stop-loss bound removed; timestamp bound removed; deadline `>=` -> `>`; time exit before stop; cooldown after time exit; expires_ts not persisted; address canonicalisation removed; tokens CHECK removed; migration price_bars de-duplication disabled -> all detected (a first attempt at the last mutation was a no-op and was redone).

## Not done / limits
* Stage 4 (Blockchain Data Engine, DEX decoder, real wallet PnL, historical backtest): needs RPC/indexer network access and verified historical data, unavailable here. Nothing was simulated as if real.
* GitHub Actions and Docker/compose were still not executable here (new workflow step installs postgresql-16 on the runner and runs `pg_verify.py`; only actionlint-validated).
* Time exit fires only when that token's own bar arrives; open positions from v0.4.2 keep `NULL` (no time exit).
