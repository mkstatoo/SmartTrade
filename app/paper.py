"""Paper portfolio: pure accounting + execution rules (no I/O, no clock, no HTTP).

Execution model (kept deliberately identical to the backtest):
  * Entry fills at  market * (1 + slippage);  qty = notional / fill.
  * Entry pays fee (bps of notional) + gas.  Exit fills at  level * (1 - slippage), pays fee + gas.
  * Stop is checked before target inside a bar (conservative); gaps fill at the bar open.
  * Time exit: a position lives at most max_hold_sec from entry_ts; the first bar whose END is >= expires_ts closes it
    at that bar's close (stop/target of the same bar win first).
  * A bar is only evaluated if it OPENED at/after the moment the entry price became known
    (``entry_ts``), so candles that were already formed when we "entered" can never trigger an exit.

The market price book (``last_prices``) holds *market* closes only. Fill prices never leak into it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Optional

from .config import CONFIG

ENGINE_EXIT_REASONS = {"stop", "target", "time"}
API_EXIT_REASONS = {"manual", "risk"}


def positive(value, name: str = "price") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return float(value)


def timeframe_seconds(tf: str) -> int:
    try:
        unit = tf[-1].lower()
        n = int(tf[:-1])
        sec = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid timeframe {tf!r}") from exc
    if sec <= 0:
        raise ValueError(f"invalid timeframe {tf!r}")
    return sec


@dataclass
class PaperPortfolio:
    initial_cash_usd: float = CONFIG.paper_initial_cash_usd
    cash_usd: Optional[float] = None
    positions: dict = field(default_factory=dict)
    realized_pnl_usd: float = 0.0
    peak_equity_usd: Optional[float] = None
    max_drawdown_pct: float = 0.0
    last_prices: dict = field(default_factory=dict)      # token_key -> market close
    last_price_ts: dict = field(default_factory=dict)    # token_key -> time the close became known (bar END)
    last_bar_ts: dict = field(default_factory=dict)      # token_key -> OPEN ts of the last ingested bar
    cooldown_until: dict = field(default_factory=dict)
    now_ts: int = 0                                      # data clock: latest bar END seen
    max_total_exposure_pct: float = 0.15
    default_allocation_pct: float = 0.05
    max_allocation_pct: float = 0.05
    cooldown_sec: int = 3600
    default_max_hold_sec: Optional[int] = CONFIG.paper_max_hold_sec
    min_notional_usd: float = 25.0                       # refuse dust entries (gas would dominate)
    slippage_bps: float = CONFIG.paper_slippage_bps
    fee_bps: float = CONFIG.paper_fee_bps
    gas_usd: float = CONFIG.paper_gas_usd
    # produced during one unit of work; the store persists then discards them
    new_closed_trades: list = field(default_factory=list)
    new_fills: list = field(default_factory=list)

    def __post_init__(self):
        if not isfinite(self.initial_cash_usd) or self.initial_cash_usd <= 0:
            raise ValueError("initial_cash_usd must be finite and > 0")
        if self.cash_usd is None:
            self.cash_usd = float(self.initial_cash_usd)
        if not isfinite(self.cash_usd):
            raise ValueError("cash_usd must be finite")
        if not 0 <= self.slippage_bps < 10_000:
            raise ValueError("slippage_bps must be in [0, 10000)")
        if self.fee_bps < 0 or self.gas_usd < 0:
            raise ValueError("fee_bps and gas_usd must be >= 0")
        if self.peak_equity_usd is None:
            self.peak_equity_usd = self.equity_usd()

    # ------------------------------------------------------------------ valuation
    def exposure_usd(self) -> float:
        return sum(p["qty"] * self.last_prices.get(t, p["entry"]) for t, p in self.positions.items())

    def equity_usd(self) -> float:
        return self.cash_usd + self.exposure_usd()

    def _update_drawdown(self) -> None:
        eq = self.equity_usd()
        self.peak_equity_usd = max(float(self.peak_equity_usd or eq), eq)
        if self.peak_equity_usd > 0:
            self.max_drawdown_pct = max(self.max_drawdown_pct,
                                        (self.peak_equity_usd - eq) / self.peak_equity_usd * 100)

    def snapshot(self) -> dict:
        eq = self.equity_usd()
        unrealized = sum(p["qty"] * self.last_prices.get(t, p["entry"]) - p["cost"]
                         for t, p in self.positions.items())
        return {"equity_usd": round(eq, 2), "cash_usd": round(self.cash_usd, 2),
                "exposure_usd": round(self.exposure_usd(), 2),
                "realized_pnl_usd": round(self.realized_pnl_usd, 2),
                "unrealized_pnl_usd": round(unrealized, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 4),
                "open_positions": len(self.positions), "data_clock_ts": self.now_ts}

    # ------------------------------------------------------------------ market data
    def update_market_price(self, token: str, close: float, price_ts: int) -> None:
        """Record the latest completed-bar close. `price_ts` is the bar END (when the close became known)."""
        self.last_prices[token] = positive(close, "close")
        self.last_price_ts[token] = int(price_ts)
        self.now_ts = max(self.now_ts, int(price_ts))
        self._update_drawdown()

    # ------------------------------------------------------------------ gates
    def can_enter(self, score: float, confidence: float, confirmations: int, liquidity_usd: float,
                  min_score=CONFIG.strong_signal_score, min_conf=CONFIG.min_confidence,
                  min_confirmations=CONFIG.min_confirmations, min_liquidity=CONFIG.min_liquidity_usd) -> bool:
        return (score >= min_score and confidence >= min_conf and
                confirmations >= min_confirmations and liquidity_usd >= min_liquidity)

    # ------------------------------------------------------------------ entry
    def enter(self, token: str, market_price: Optional[float] = None, allocation_pct: Optional[float] = None,
              target_return_pct: Optional[float] = None, stop_loss_pct: Optional[float] = None,
              signal_id: Optional[int] = None, max_hold_sec: Optional[int] = None) -> dict:
        if market_price is None:
            if token not in self.last_prices:
                return {"status": "no_market_price"}
            market_price = self.last_prices[token]
        market = positive(market_price, "market_price")
        pct = self.default_allocation_pct if allocation_pct is None else float(allocation_pct)
        if not 0 < pct <= self.max_allocation_pct:
            raise ValueError(f"allocation_pct must be in (0, {self.max_allocation_pct}]")
        hold = self.default_max_hold_sec if max_hold_sec is None else max_hold_sec
        if hold is not None and (isinstance(hold, bool) or int(hold) != hold or hold <= 0):
            raise ValueError("max_hold_sec must be a positive integer")
        for name, v in (("target_return_pct", target_return_pct), ("stop_loss_pct", stop_loss_pct)):
            if v is not None and (not isfinite(v) or v <= 0):
                raise ValueError(f"{name} must be finite and > 0")
        if token in self.positions:
            return {"status": "already_in_position"}
        if self.now_ts < self.cooldown_until.get(token, 0):
            return {"status": "cooldown", "until_ts": self.cooldown_until[token]}

        equity = self.equity_usd()
        exposure = self.exposure_usd()
        room = max(0.0, equity * self.max_total_exposure_pct - exposure)
        fee_rate = self.fee_bps / 1e4
        affordable = (self.cash_usd - self.gas_usd) / (1 + fee_rate)     # notional + fee + gas must fit in cash
        notional = min(equity * pct, room, affordable)
        if notional < self.min_notional_usd:
            return {"status": "risk_limit_or_no_cash"}

        fill = market * (1 + self.slippage_bps / 1e4)
        qty = notional / fill
        fee = notional * fee_rate
        cost = notional + fee + self.gas_usd
        self.cash_usd -= cost
        entry_ts = self.last_price_ts.get(token, self.now_ts)
        self.positions[token] = {
            "qty": qty, "entry": fill, "cost": cost, "notional": notional,
            "entry_fee_usd": fee, "entry_gas_usd": self.gas_usd, "reference_price": market,
            "fee_bps": self.fee_bps, "slippage_bps": self.slippage_bps, "gas_usd": self.gas_usd,
            "target_return_pct": target_return_pct, "stop_loss_pct": stop_loss_pct,
            "entry_ts": int(entry_ts), "signal_id": signal_id,
            "max_hold_sec": None if hold is None else int(hold),
            "expires_ts": None if hold is None else int(entry_ts) + int(hold),
        }
        self.new_fills.append({"side": "BUY", "token": token, "price": fill, "qty": qty, "notional": notional,
                               "fee_usd": fee, "slippage_usd": qty * (fill - market), "gas_usd": self.gas_usd,
                               "ts": int(entry_ts), "signal_id": signal_id})
        self._update_drawdown()
        return {"status": "entered", "token": token, "qty": qty, "entry": fill, "market_price": market,
                "cost": cost, "fee_usd": fee, "gas_usd": self.gas_usd, "entry_ts": int(entry_ts),
                "token_exposure_pct": notional / equity * 100,
                "total_exposure_pct": (exposure + notional) / equity * 100}

    # ------------------------------------------------------------------ exit
    def exit(self, token: str, level_price: float, reason: str = "manual", ts: Optional[int] = None,
             price_basis: str = "bar", price_age_sec: Optional[int] = None) -> dict:
        """Close at `level_price` (a market level); exit slippage, fee and gas are applied here."""
        level = positive(level_price, "level_price")
        p = self.positions.get(token)
        if not p:
            return {"status": "not_in_position"}
        exit_ts = self.now_ts if ts is None else int(ts)
        slip = p["slippage_bps"] / 1e4
        exit_px = level * (1 - slip)
        proceeds = p["qty"] * exit_px
        fee = proceeds * p["fee_bps"] / 1e4
        gas = p["gas_usd"]
        net = proceeds - fee - gas
        pnl = net - p["cost"]
        self.cash_usd += net
        self.realized_pnl_usd += pnl
        trade = {"token": token, "entry": p["entry"], "exit": exit_px, "market_level": level, "qty": p["qty"],
                 "cost": p["cost"], "pnl_usd": pnl, "exit_fee_usd": fee, "exit_gas_usd": gas, "reason": reason,
                 "entry_ts": p["entry_ts"], "exit_ts": exit_ts, "signal_id": p.get("signal_id"),
                 "price_basis": price_basis, "price_age_sec": price_age_sec}
        self.new_closed_trades.append(trade)
        self.new_fills.append({"side": "SELL", "token": token, "price": exit_px, "qty": p["qty"],
                               "notional": proceeds, "fee_usd": fee, "slippage_usd": p["qty"] * (level - exit_px),
                               "gas_usd": gas, "ts": exit_ts, "signal_id": p.get("signal_id")})
        del self.positions[token]
        if reason == "stop":
            self.cooldown_until[token] = exit_ts + self.cooldown_sec
        self._update_drawdown()
        return {"status": "exited", **trade}

    # ------------------------------------------------------------------ independent expiry
    def sweep_expired(self, now_ts: int) -> list:
        """Close every position whose time deadline has passed, even if no new bar arrived.

        The exit is priced at the LAST KNOWN market close (there is nothing newer to use) and is labelled
        ``price_basis='stale_last_close'`` with the age of that price, so the record never pretends to be a fresh quote.
        Exit slippage, fee and gas apply exactly as for any other exit."""
        closed = []
        for token in sorted(self.positions):
            p = self.positions[token]
            exp = p.get("expires_ts")
            if exp is None or exp > now_ts:
                continue
            price = self.last_prices.get(token, p["reference_price"])
            age = max(0, int(now_ts) - int(self.last_price_ts.get(token, p["entry_ts"])))
            closed.append(self.exit(token, price, "time", ts=int(now_ts), price_basis="stale_last_close",
                                    price_age_sec=age))
        return closed

    # ------------------------------------------------------------------ bar evaluation
    def evaluate_bar(self, token: str, bar: dict) -> dict:
        """Apply stop/target to one COMPLETED bar. Does not touch the price book (the caller does, after)."""
        p = self.positions.get(token)
        if not p:
            return {"status": "no_position"}
        o, h, l, c = (positive(bar[k], k) for k in ("open", "high", "low", "close"))
        if l > min(o, c) or h < max(o, c):
            raise ValueError("inconsistent OHLC")
        if int(bar["ts"]) < p["entry_ts"]:
            return {"status": "ignored_pre_entry_bar"}
        stop, target, entry = p.get("stop_loss_pct"), p.get("target_return_pct"), p["entry"]
        stop_px = entry * (1 - stop / 100) if stop is not None else None
        target_px = entry * (1 + target / 100) if target is not None else None
        if stop_px is not None and l <= stop_px:                     # stop first when both are touched
            self.now_ts = max(self.now_ts, int(bar.get("end_ts", bar["ts"])))
            return self.exit(token, min(stop_px, o), "stop")
        if target_px is not None and h >= target_px:
            self.now_ts = max(self.now_ts, int(bar.get("end_ts", bar["ts"])))
            return self.exit(token, max(target_px, o), "target")
        expires = p.get("expires_ts")
        bar_end = int(bar.get("end_ts", bar["ts"]))
        if expires is not None and bar_end >= expires:               # deadline reached: leave at this bar's close
            self.now_ts = max(self.now_ts, bar_end)
            return self.exit(token, c, "time")
        return {"status": "holding"}
