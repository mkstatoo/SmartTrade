from .config import CONFIG, Config


def validate_asof(wallets, signal_ts: int, now: int, cfg: Config = CONFIG) -> None:
    """Strict as-of provenance. `now` comes from the server clock, never from the client.
    Raises ValueError with a precise reason."""
    if signal_ts is None or signal_ts <= 0:
        raise ValueError("signal_ts is required")
    if signal_ts > now + cfg.signal_clock_skew_sec:
        raise ValueError("signal_ts is too far in the future")
    if signal_ts < now - cfg.signal_clock_skew_sec:
        raise ValueError("signal_ts is outside the permitted window around the server clock")
    for w in wallets:
        if "as_of_ts" not in w.model_fields_set or w.as_of_ts <= 0:
            raise ValueError("as_of_ts is required for every wallet")
        if w.as_of_ts > signal_ts:
            raise ValueError("wallet statistics are newer than signal_ts")
        if now - w.as_of_ts > cfg.strict_max_stats_age_sec:
            raise ValueError("wallet statistics are stale")
