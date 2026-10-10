"""Walk-forward evaluation with no look-ahead: train / validation / out-of-sample, purge+embargo, sensitivity.

Rules enforced here (and checked again in `leakage_checks` of every report):
  * Phases are separated by time boundaries chosen from the BUY-event timestamps.
  * A trade's whole life (event -> latency -> entry delay -> horizon) must fit inside its phase: events whose reach
    crosses the phase end are PURGED (that is the embargo), and bars after the phase end are not even handed to the
    simulator. So no phase can see another phase's prices.
  * Parameters are chosen on TRAIN only; VALIDATION is a gate (must stay profitable); the out-of-sample phase is run
    once, with the chosen parameters, and only if the gate passed. Sensitivity runs on the OOS phase afterwards, as a
    diagnostic - nothing is re-selected from it.
Nothing here fabricates data: it only re-slices what the caller supplies.
"""
from __future__ import annotations

from itertools import product

from .backtest import BUY_SIDES, run_backtest
from .models import BacktestRequest


def _metrics(res: dict) -> dict:
    return {k: res[k] for k in ("events", "effective_n", "hits", "hit_rate_pct", "win_rate_pct", "avg_net_return_pct",
                                "profit_factor", "skipped")} | {"skip_reasons": res["skip_reasons"]}


def _reach(req: BacktestRequest) -> int:
    return int(req.detection_latency_sec + req.block_latency_sec + req.max_entry_delay_hours * 3600 + req.horizon_hours * 3600)


def split_phases(req: BacktestRequest, train_frac: float, val_frac: float, extra_reach_sec: int = 0) -> dict:
    ts = sorted(e.ts for e in req.events if e.side in BUY_SIDES)
    if len(ts) < 3:
        raise ValueError("need at least 3 BUY events")
    if not (0 < train_frac < 1 and 0 < val_frac < 1 and train_frac + val_frac < 1):
        raise ValueError("train_frac and val_frac must be in (0,1) with train_frac + val_frac < 1")
    b1 = ts[int(len(ts) * train_frac)]
    b2 = ts[int(len(ts) * (train_frac + val_frac))]
    if not (ts[0] < b1 < b2):
        raise ValueError("phases would be empty; supply events spread over a longer period")
    reach = _reach(req) + extra_reach_sec
    return {"reach_sec": reach,
            "train": {"start": ts[0], "end": b1}, "validation": {"start": b1, "end": b2},
            "test": {"start": b2, "end": None}}


def _phase_req(req: BacktestRequest, start: int, end, reach: int, **over) -> tuple[BacktestRequest, int]:
    """Events whose whole life fits before `end`; bars only up to `end`. Returns (request, purged_count)."""
    in_window = [e for e in req.events if e.ts >= start and (end is None or e.ts < end)]
    kept = [e for e in in_window if end is None or e.ts + reach <= end or e.side not in BUY_SIDES]
    buys_in = sum(1 for e in in_window if e.side in BUY_SIDES)
    buys_kept = sum(1 for e in kept if e.side in BUY_SIDES)
    prices = [p for p in req.prices if end is None or p.ts <= end]
    return req.model_copy(update={"events": kept, "prices": prices, **over}), buys_in - buys_kept


def _leak_check(name, res, start, end):
    rs = res["results"]
    return {"phase": name,
            "events_start_inside": all(r["event_ts"] >= start for r in rs),
            "lifecycle_ends_inside": end is None or all(r["exit_ts"] <= end for r in rs),
            "max_exit_ts": max((r["exit_ts"] for r in rs), default=None), "phase_end": end}


def walk_forward(req: BacktestRequest, *, train_frac=0.5, val_frac=0.2, target_grid=(2.0, 5.0, 10.0),
                 stop_grid=(None, 2.0, 5.0), min_trades=5, latency_grid=(0, 60, 300, 900),
                 slippage_grid=(0.0, 30.0, 100.0, 300.0)) -> dict:
    ph = split_phases(req, train_frac, val_frac, extra_reach_sec=0)
    reach = ph["reach_sec"]
    tr_req, tr_purged = _phase_req(req, ph["train"]["start"], ph["train"]["end"], reach)
    va_req, va_purged = _phase_req(req, ph["validation"]["start"], ph["validation"]["end"], reach)
    te_req, te_purged = _phase_req(req, ph["test"]["start"], None, reach)

    grid = []
    for tgt, stp in product(target_grid, stop_grid):
        res = run_backtest(tr_req.model_copy(update={"target_return_pct": tgt, "stop_loss_pct": stp}))
        grid.append({"target_return_pct": tgt, "stop_loss_pct": stp, "train": _metrics(res),
                     "_res": res})
    eligible = [g for g in grid if g["train"]["effective_n"] >= min_trades]
    checks = [_leak_check("train", g["_res"], ph["train"]["start"], ph["train"]["end"]) for g in grid]
    leak = [{"phase": "train", "events_start_inside": all(c["events_start_inside"] for c in checks),
             "lifecycle_ends_inside": all(c["lifecycle_ends_inside"] for c in checks),
             "max_exit_ts": max((c["max_exit_ts"] for c in checks if c["max_exit_ts"] is not None), default=None),
             "phase_end": ph["train"]["end"], "grid_cells_checked": len(checks)}]
    for g in grid:
        g.pop("_res")
    report = {"phases": ph, "purged_events": {"train": tr_purged, "validation": va_purged, "test": te_purged},
              "grid": grid, "min_trades": min_trades, "selected": None, "validation": None, "gate_passed": False,
              "oos": None, "sensitivity": None, "leakage_checks": leak,
              "notes": ["parameters chosen on TRAIN only", "validation is a gate, not a selector",
                        "OOS runs once with the chosen parameters, only if the gate passed"]}
    if not eligible:
        report["notes"].append("no parameter set reached min_trades on train; nothing selected")
        return report
    best = max(eligible, key=lambda g: (g["train"]["avg_net_return_pct"], -(g["stop_loss_pct"] or 0), g["target_return_pct"]))
    params = {"target_return_pct": best["target_return_pct"], "stop_loss_pct": best["stop_loss_pct"]}
    report["selected"] = params
    vres = run_backtest(va_req.model_copy(update=params))
    leak.append(_leak_check("validation", vres, ph["validation"]["start"], ph["validation"]["end"]))
    report["validation"] = _metrics(vres)
    report["gate_passed"] = vres["effective_n"] >= min_trades and vres["avg_net_return_pct"] > 0
    if not report["gate_passed"]:
        report["notes"].append("validation gate failed: out-of-sample phase NOT evaluated (no snooping)")
        return report
    ores = run_backtest(te_req.model_copy(update=params))
    leak.append(_leak_check("test", ores, ph["test"]["start"], None))
    report["oos"] = _metrics(ores)

    cells = []
    for lat, slip in product(latency_grid, slippage_grid):
        r = run_backtest(te_req.model_copy(update={**params, "detection_latency_sec": lat, "slippage_bps": slip}))
        cells.append({"detection_latency_sec": lat, "slippage_bps": slip, "effective_n": r["effective_n"],
                      "avg_net_return_pct": r["avg_net_return_pct"], "win_rate_pct": r["win_rate_pct"]})
    pos = [c for c in cells if c["effective_n"] > 0 and c["avg_net_return_pct"] > 0]
    base = next((c for c in cells if c["detection_latency_sec"] == req.detection_latency_sec
                 and c["slippage_bps"] == req.slippage_bps), None)
    report["sensitivity"] = {
        "cells": cells, "share_of_cells_profitable": round(len(pos) / len(cells), 4),
        "fragile": bool(base and base["avg_net_return_pct"] > 0 and len(pos) / len(cells) < 0.5),
        "note": "diagnostic on the OOS phase; nothing was re-selected from it"}
    return report
