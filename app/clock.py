"""Clocks decide what "now" means for freshness and as-of checks."""
import time


class LiveClock:
    """Wall-clock time: for real-time bar ingestion."""
    name = "live"

    def now(self, portfolio=None) -> int:
        return int(time.time())


class ReplayClock:
    """Data time = end time of the latest ingested bar: for replaying historical bars."""
    name = "replay"

    def now(self, portfolio=None) -> int:
        return int(getattr(portfolio, "now_ts", 0))


def clock_for(mode: str):
    return ReplayClock() if mode == "replay" else LiveClock()
