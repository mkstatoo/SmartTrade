"""Single source of truth for thresholds and paper-trading assumptions.

These are *policy / assumption* parameters, not market data. They are not calibrated:
calibrate them with walk-forward backtests before trusting any signal.

Secrets (the research API key, database credentials) are NEVER stored here, so
``Config.as_dict()`` / ``GET /config`` can never leak them.
"""
from dataclasses import dataclass, asdict, fields, replace
import hashlib
import json
import math
import os
import re


class ConfigError(ValueError):
    """Invalid configuration: the process refuses to start rather than run with a silently wrong setting."""


@dataclass(frozen=True)
class Config:
    # signal gates
    min_wallet_score: float = 75.0
    strong_signal_score: float = 80.0
    min_confirmations: int = 2
    min_liquidity_usd: float = 2_000_000.0
    min_confidence: float = 0.75
    # wallet eligibility (METHODOLOGY section A)
    min_history_events: int = 20
    min_confirmer_hit_rate: float = 0.5
    # flow classification
    flow_threshold: float = 0.2
    distributing_score_cap: float = 40.0
    max_distribution_share: float = 0.5
    # execution is permanently disabled in this code base
    live_execution: bool = False
    # strict as-of provenance (server-side only)
    strict_max_stats_age_sec: int = 86400
    signal_clock_skew_sec: int = 300
    # paper trading: follower-side assumptions (same meaning as in the backtest)
    max_market_price_age_sec: int = 300
    paper_slippage_bps: float = 30.0
    paper_fee_bps: float = 30.0
    paper_gas_usd: float = 2.0
    paper_initial_cash_usd: float = 10000.0
    paper_max_hold_sec: int = 86400   # time-exit horizon (same default as the backtest's 24h horizon)
    paper_bar_timeframe: str = "1m"
    paper_portfolio_id: str = "default"
    # 'live': freshness is judged against wall-clock time.
    # 'replay': freshness is judged against the data clock (latest ingested bar), so historical bars can be replayed.
    paper_clock: str = "live"
    # independent expiry sweeper (seconds between sweeps; 0 disables the in-process loop)
    paper_sweep_interval_sec: int = 30
    # request / auth hardening
    max_body_bytes: int = 33_554_432
    auth_fail_limit: int = 10
    auth_fail_window_sec: int = 60
    # database failure behaviour
    db_connect_timeout_sec: int = 5
    db_statement_timeout_ms: int = 10_000
    db_lock_timeout_ms: int = 5_000

    def as_dict(self) -> dict:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    def validate(self) -> "Config":
        def need(ok, msg):
            if not ok:
                raise ConfigError(msg)
        finite = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)  # noqa: E731
        need(self.live_execution is False, "live_execution cannot be enabled: this code base is research/paper only")
        need(self.paper_clock in {"live", "replay"}, "paper_clock must be 'live' or 'replay'")
        need(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", self.paper_portfolio_id) is not None,
             "paper_portfolio_id must match [A-Za-z0-9_.-]{1,64}")
        need(finite(self.paper_slippage_bps) and 0 <= self.paper_slippage_bps < 10_000, "paper_slippage_bps must be in [0, 10000)")
        need(finite(self.paper_fee_bps) and 0 <= self.paper_fee_bps <= 10_000, "paper_fee_bps must be in [0, 10000]")
        need(finite(self.paper_gas_usd) and 0 <= self.paper_gas_usd <= 1e6, "paper_gas_usd must be in [0, 1e6]")
        need(finite(self.paper_initial_cash_usd) and 0 < self.paper_initial_cash_usd <= 1e12, "paper_initial_cash_usd must be in (0, 1e12]")
        need(self.paper_max_hold_sec > 0, "paper_max_hold_sec must be > 0")
        need(self.paper_sweep_interval_sec >= 0, "paper_sweep_interval_sec must be >= 0")
        need(self.max_market_price_age_sec > 0, "max_market_price_age_sec must be > 0")
        need(self.signal_clock_skew_sec >= 0 and self.strict_max_stats_age_sec > 0, "clock skew / stats age must be positive")
        need(0 < self.min_confidence <= 1 and 0 <= self.min_wallet_score <= 100 and 0 <= self.strong_signal_score <= 100,
             "score / confidence thresholds out of range")
        need(self.min_confirmations >= 1, "min_confirmations must be >= 1")
        need(self.min_liquidity_usd >= 0, "min_liquidity_usd must be >= 0")
        need(1024 <= self.max_body_bytes <= 1 << 31, "max_body_bytes must be in [1024, 2^31]")
        need(self.auth_fail_limit >= 1 and self.auth_fail_window_sec >= 1, "auth throttle values must be >= 1")
        need(self.db_connect_timeout_sec >= 1 and self.db_statement_timeout_ms >= 100 and self.db_lock_timeout_ms >= 100,
             "database timeouts too small")
        try:
            from .paper import timeframe_seconds  # noqa: F401  (validated lazily to avoid an import cycle)
        except Exception:  # noqa: BLE001
            pass
        need(re.fullmatch(r"[1-9][0-9]*[smhd]", self.paper_bar_timeframe) is not None, "paper_bar_timeframe must look like 1m, 5m, 1h")
        return self


# environment name -> (Config field, parser). Only these can be overridden; everything else is code.
def _num(name):
    def parse(raw):
        try:
            v = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name}={raw!r} is not a number") from exc
        if not math.isfinite(v):
            raise ConfigError(f"{name}={raw!r} must be finite")
        return v
    return parse


def _int(name):
    def parse(raw):
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name}={raw!r} is not an integer") from exc
    return parse


ENV_OVERRIDES = {
    "PAPER_SLIPPAGE_BPS": ("paper_slippage_bps", _num), "PAPER_FEE_BPS": ("paper_fee_bps", _num),
    "PAPER_GAS_USD": ("paper_gas_usd", _num), "PAPER_INITIAL_CASH_USD": ("paper_initial_cash_usd", _num),
    "PAPER_MAX_HOLD_SEC": ("paper_max_hold_sec", _int), "PAPER_SWEEP_INTERVAL_SEC": ("paper_sweep_interval_sec", _int),
    "MAX_MARKET_PRICE_AGE_SEC": ("max_market_price_age_sec", _int), "MAX_BODY_BYTES": ("max_body_bytes", _int),
    "AUTH_FAIL_LIMIT": ("auth_fail_limit", _int), "AUTH_FAIL_WINDOW_SEC": ("auth_fail_window_sec", _int),
    "DB_CONNECT_TIMEOUT_SEC": ("db_connect_timeout_sec", _int), "DB_STATEMENT_TIMEOUT_MS": ("db_statement_timeout_ms", _int),
    "DB_LOCK_TIMEOUT_MS": ("db_lock_timeout_ms", _int),
    "PAPER_CLOCK": ("paper_clock", lambda n: (lambda raw: raw.lower())),
    "PAPER_PORTFOLIO_ID": ("paper_portfolio_id", lambda n: (lambda raw: raw)),
}


def config_from_env(env=None) -> tuple["Config", list[str]]:
    """Defaults + whitelisted environment overrides, validated. Returns (config, names of overridden variables)."""
    env = os.environ if env is None else env
    values, used = {}, []
    for name, (field, mk) in ENV_OVERRIDES.items():
        if env.get(name) not in (None, ""):
            values[field] = mk(name)(env[name])
            used.append(name)
    return replace(Config(), **values).validate(), used


CONFIG, ENV_OVERRIDES_USED = config_from_env()


def paper_api_key() -> str:
    """Read at call time so it is never captured in a config dump. Empty => protected endpoints disabled."""
    return os.getenv("PAPER_API_KEY", "")
