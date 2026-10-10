from typing import Literal, Optional
from math import isfinite
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_PRICE = 1e12            # sanity bounds: keep arithmetic finite and values inside PostgreSQL integer/NUMERIC sanity
MAX_USD = 1e15
MAX_TS = 4_102_444_800       # 2100-01-01 UTC
MAX_I64 = 2**63 - 1
MAX_COUNT = 10**9
MAX_WALLETS = 200
MAX_EVENTS = 100_000
MAX_BARS = 200_000
MAX_PCT = 1e4              # percentages other than stop-loss (which must be < 100)


class StrictModel(BaseModel):
    """Base of every API model: NaN / +-Infinity are rejected for all float fields (also when sent as strings)."""
    model_config = ConfigDict(allow_inf_nan=False)

class WalletEvent(StrictModel):
    wallet: str = Field(min_length=1)
    token: str = Field(min_length=1, description="Token contract/address; chain is separate")
    chain: str = Field(default="unknown", min_length=1)
    ts: int = Field(ge=0, le=MAX_TS)
    side: Literal["BUY", "SELL", "CEX_IN", "CEX_OUT", "TRANSFER"]
    usd_value: float = Field(ge=0, le=MAX_USD)
    price: float = Field(gt=0, le=MAX_PRICE)
    tx_hash: str = ""
    log_index: Optional[int] = Field(default=None, ge=0, le=MAX_I64)

class PriceBar(StrictModel):
    chain: str = Field(default="unknown", min_length=1)
    token: str = Field(min_length=1)
    ts: int = Field(ge=0, le=MAX_TS)
    timeframe: str = Field(default="1m", min_length=1)
    open: float = Field(gt=0, le=MAX_PRICE)
    high: float = Field(gt=0, le=MAX_PRICE)
    low: float = Field(gt=0, le=MAX_PRICE)
    close: float = Field(gt=0, le=MAX_PRICE)
    volume_usd: float = Field(ge=0, le=MAX_USD)
    @model_validator(mode="after")
    def _ohlc_consistent(self):
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("inconsistent OHLC")
        return self

class WalletStats(StrictModel):
    wallet: str = Field(min_length=1)
    events: int = Field(ge=0, le=MAX_COUNT); wins: int = Field(ge=0, le=MAX_COUNT); losses: int = Field(ge=0, le=MAX_COUNT)
    avg_return: float = Field(ge=-MAX_PCT, le=MAX_PCT); token_events: int = Field(default=0, ge=0, le=MAX_COUNT)
    token_wins: int = Field(default=0, ge=0, le=MAX_COUNT); token_avg_return: float = Field(default=0.0, ge=-MAX_PCT, le=MAX_PCT)
    accumulation_usd: float = Field(default=0.0, ge=0, le=MAX_USD); distribution_usd: float = Field(default=0.0, ge=0, le=MAX_USD)
    independent_confirmations: int = Field(default=0, ge=0, le=MAX_COUNT)
    cluster_id: Optional[str] = None; pump_distance_pct: float = Field(default=0.0, ge=-MAX_PCT, le=MAX_PCT)
    cex_outflow_share: float = Field(default=0.0, ge=0, le=1); volume_anomaly: float = Field(default=0.0, ge=0, le=MAX_USD)
    chain: str = Field(default="unknown", min_length=1)
    as_of_ts: int = Field(default=0, ge=0, le=MAX_TS)
    @model_validator(mode="after")
    def _counts_consistent(self):
        if self.wins + self.losses > self.events or self.token_wins > self.token_events:
            raise ValueError("inconsistent event counts")
        return self

from .ids import canonical_address as normalize_address  # noqa: E402  (single source of truth)

def _unique_wallets(v):
    keys = [(w.chain.lower(), normalize_address(w.chain, w.wallet)) for w in v]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate wallet addresses")
    return v

class ScoreRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    token: str = Field(min_length=1); chain: str = Field(default="unknown", min_length=1)
    wallets: list[WalletStats] = Field(max_length=MAX_WALLETS); liquidity_usd: float = Field(ge=0, le=MAX_USD)
    signal_ts: int = Field(ge=1, le=MAX_TS)
    _check = field_validator("wallets")(_unique_wallets)

class BacktestRequest(StrictModel):
    events: list[WalletEvent] = Field(max_length=MAX_EVENTS); prices: list[PriceBar] = Field(max_length=MAX_BARS)
    timeframe: str = Field(default="1m", min_length=1)
    horizon_hours: float = Field(default=24, gt=0, le=24 * 365); target_return_pct: float = Field(default=5, gt=0, le=MAX_PCT)
    stop_loss_pct: Optional[float] = Field(default=None, gt=0, lt=100); max_entry_delay_hours: float = Field(default=24, ge=0, le=24 * 365)
    detection_latency_sec: int = Field(default=60, ge=0, le=86400); block_latency_sec: int = Field(default=12, ge=0, le=86400)
    slippage_bps: float = Field(default=30, ge=0, lt=10_000); fee_bps: float = Field(default=30, ge=0, le=10_000)
    gas_usd: float = Field(default=2, ge=0, le=MAX_USD); notional_usd: float = Field(default=1000, gt=0, le=MAX_USD)
    max_participation_pct: float = Field(default=5, gt=0, le=100)

class PaperSignalRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    token: str = Field(min_length=1); chain: str = Field(default="unknown", min_length=1)
    wallets: list[WalletStats] = Field(max_length=MAX_WALLETS); liquidity_usd: float = Field(ge=0, le=MAX_USD)
    signal_ts: int = Field(ge=1, le=MAX_TS)
    allocation_pct: float = Field(default=.05, gt=0, le=.05)
    target_return_pct: Optional[float] = Field(default=None, gt=0, le=MAX_PCT); stop_loss_pct: Optional[float] = Field(default=None, gt=0, lt=100)
    max_hold_sec: Optional[int] = Field(default=None, gt=0, le=30 * 86400, description="time-exit horizon; default from server config")
    _check = field_validator("wallets")(_unique_wallets)


class PaperBarRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    chain: str = Field(min_length=1)
    token: str = Field(min_length=1)
    ts: int = Field(ge=1, le=MAX_TS)
    timeframe: str = Field(default="1m", min_length=1)
    open: float = Field(gt=0, le=MAX_PRICE)
    high: float = Field(gt=0, le=MAX_PRICE)
    low: float = Field(gt=0, le=MAX_PRICE)
    close: float = Field(gt=0, le=MAX_PRICE)
    volume_usd: float = Field(ge=0, le=MAX_USD)
    @model_validator(mode="after")
    def _ohlc(self):
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("inconsistent OHLC")
        return self


class PnlEntry(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal["buy", "sell", "transfer_in", "transfer_out", "fee"]
    ts: int = Field(ge=0, le=MAX_TS)
    chain: str = Field(default="unknown", min_length=1)
    token: Optional[str] = Field(default=None, min_length=1)
    qty: float = Field(default=0.0, ge=0, le=1e30)
    usd: Optional[float] = Field(default=None, ge=0, le=MAX_USD)
    fee_usd: float = Field(default=0.0, ge=0, le=MAX_USD)
    cost_basis_usd: Optional[float] = Field(default=None, ge=0, le=MAX_USD)
    tx_hash: Optional[str] = None
    log_index: Optional[int] = Field(default=None, ge=0, le=MAX_I64)
    block_number: Optional[int] = Field(default=None, ge=0, le=MAX_I64)


class InitialBalance(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    qty: float = Field(gt=0, le=1e30)
    unit_cost_usd: Optional[float] = Field(default=None, ge=0, le=MAX_USD)


class WalletPnlRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    entries: list[PnlEntry] = Field(max_length=MAX_EVENTS)
    initial_balances: dict[str, InitialBalance] = Field(default_factory=dict, description="token_key (chain:contract) -> balance")
    marks: dict[str, float] = Field(default_factory=dict, description="token_key -> USD price used for unrealised PnL")
    method: Literal["fifo", "average"] = "fifo"
    transfer_in_policy: Literal["unknown_basis", "fair_value"] = "unknown_basis"
    transfer_out_policy: Literal["no_pnl", "dispose_at_value"] = "no_pnl"


class WalkForwardRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    base: BacktestRequest
    train_frac: float = Field(default=0.5, gt=0, lt=1)
    val_frac: float = Field(default=0.2, gt=0, lt=1)
    target_grid: list[float] = Field(default_factory=lambda: [2.0, 5.0, 10.0], min_length=1, max_length=10)
    stop_grid: list[Optional[float]] = Field(default_factory=lambda: [None, 2.0, 5.0], min_length=1, max_length=10)
    min_trades: int = Field(default=5, ge=1, le=100_000)
    latency_grid: list[int] = Field(default_factory=lambda: [0, 60, 300, 900], min_length=1, max_length=8)
    slippage_grid: list[float] = Field(default_factory=lambda: [0.0, 30.0, 100.0, 300.0], min_length=1, max_length=8)

    @model_validator(mode="after")
    def _grids(self):
        if self.train_frac + self.val_frac >= 1:
            raise ValueError("train_frac + val_frac must be < 1")
        if any(t <= 0 or t > MAX_PCT for t in self.target_grid) or any(s is not None and not 0 < s < 100 for s in self.stop_grid):
            raise ValueError("grid values out of range")
        if any(l < 0 or l > 86400 for l in self.latency_grid) or any(not 0 <= s < 10_000 for s in self.slippage_grid):
            raise ValueError("sensitivity grid values out of range")
        return self
