"""Wallet PnL from a ledger of entries (source-agnostic: works on whatever produced the entries).

Accounting rules (all USD, Decimal arithmetic, nothing is invented):
  buy           token in, paid `usd`; `fee_usd` is added to the lot's cost (capitalised).
  sell          token out, received `usd`; `fee_usd` is deducted from proceeds.
  transfer_in   token in without a purchase. Basis: explicit `cost_basis_usd` (internal transfer carrying its basis) ->
                else policy 'unknown_basis' (default: the lot has NO known cost) or 'fair_value' (basis = `usd`, e.g. airdrop).
  transfer_out  token leaves the wallet, not a sale: lots are consumed, no realised PnL (their known cost is reported as
                `transferred_out_cost_usd`); policy 'dispose_at_value' treats it as a sale at `usd`. `fee_usd` is an expense.
  fee           stand-alone expense (e.g. approval gas), not tied to a lot.
Cost methods: 'fifo' (default) or 'average'.
Unknown-basis units (initial balances without cost, transfers in, oversold excess) can be sold, but their proceeds are
reported separately (`realized_unknown_basis_proceeds_usd`) - they never create a fake profit or loss.
Bad data never crashes or silently changes numbers: it is skipped/flagged in `data_errors`.
"""
from __future__ import annotations

import math
from decimal import Decimal, getcontext
from typing import Any, Iterable, Optional

from .ids import token_key

getcontext().prec = 50
ZERO = Decimal(0)
KINDS = {"buy", "sell", "transfer_in", "transfer_out", "fee"}
METHODS = {"fifo", "average"}
IN_POLICIES = {"unknown_basis", "fair_value"}
OUT_POLICIES = {"no_pnl", "dispose_at_value"}


def _dec(x: Any) -> Optional[Decimal]:
    """float/int/str/Decimal -> finite Decimal, else None. floats go through repr so 0.1 stays 0.1."""
    if x is None or isinstance(x, bool):
        return None
    try:
        d = Decimal(repr(x)) if isinstance(x, float) else Decimal(str(x))
    except Exception:  # noqa: BLE001
        return None
    return d if d.is_finite() else None


class _Book:
    """Inventory of one token. FIFO: ordered lots. Average: pooled (known cost) + pooled unknown units."""

    def __init__(self, method: str):
        self.method = method
        self.lots: list[list] = []                   # fifo: [qty, total_cost or None(unknown)]
        self.k_qty = self.k_cost = self.u_qty = ZERO  # average pools

    def add(self, qty: Decimal, cost: Optional[Decimal]):
        if self.method == "fifo":
            self.lots.append([qty, cost])
        elif cost is None:
            self.u_qty += qty
        else:
            self.k_qty += qty
            self.k_cost += cost

    def qty(self) -> Decimal:
        return sum((l[0] for l in self.lots), ZERO) if self.method == "fifo" else self.k_qty + self.u_qty

    def take(self, qty: Decimal) -> list[tuple[Decimal, Optional[Decimal]]]:
        """Remove up to `qty`; returns chunks (qty, cost or None). Never goes negative."""
        out: list[tuple[Decimal, Optional[Decimal]]] = []
        if self.method == "fifo":
            need = qty
            while need > 0 and self.lots:
                lq, lc = self.lots[0]
                t = min(lq, need)
                part = None if lc is None else (lc if t == lq else lc * t / lq)
                out.append((t, part))
                if t == lq:
                    self.lots.pop(0)
                else:
                    self.lots[0] = [lq - t, None if lc is None else lc - part]
                need -= t
            return out
        total = self.k_qty + self.u_qty
        t = min(qty, total)
        if t <= 0:
            return out
        tk, tu = t * self.k_qty / total, t * self.u_qty / total
        if tk > 0:
            c = self.k_cost * tk / self.k_qty
            out.append((tk, c))
            self.k_cost -= c
            self.k_qty -= tk
        if tu > 0:
            out.append((tu, None))
            self.u_qty -= tu
        if self.k_qty <= 0:
            self.k_qty = self.k_cost = ZERO
        return out

    def open_known_cost(self) -> Decimal:
        return sum((l[1] for l in self.lots if l[1] is not None), ZERO) if self.method == "fifo" else self.k_cost

    def open_known_qty(self) -> Decimal:
        return sum((l[0] for l in self.lots if l[1] is not None), ZERO) if self.method == "fifo" else self.k_qty

    def open_unknown_qty(self) -> Decimal:
        return sum((l[0] for l in self.lots if l[1] is None), ZERO) if self.method == "fifo" else self.u_qty


def compute_pnl(entries: Iterable[dict], *, initial_balances: Optional[dict] = None, method: str = "fifo",
                marks: Optional[dict] = None, transfer_in_policy: str = "unknown_basis",
                transfer_out_policy: str = "no_pnl") -> dict:
    if method not in METHODS or transfer_in_policy not in IN_POLICIES or transfer_out_policy not in OUT_POLICIES:
        raise ValueError("unknown method or policy")
    errors: list[dict] = []
    books: dict[str, _Book] = {}
    st: dict[str, dict] = {}

    def book(k):
        if k not in books:
            books[k] = _Book(method)
            st[k] = {"bought_qty": ZERO, "sold_qty": ZERO, "transferred_in_qty": ZERO, "transferred_out_qty": ZERO,
                     "initial_qty": ZERO, "oversold_qty": ZERO, "realized_pnl_usd": ZERO,
                     "realized_unknown_basis_proceeds_usd": ZERO, "transferred_out_cost_usd": ZERO,
                     "buy_cost_usd": ZERO, "initial_cost_usd": ZERO, "sell_net_usd": ZERO}
        return books[k]

    tot = {"fees_in_trades_usd": ZERO, "expenses_usd": ZERO}
    closed: list[dict] = []

    # ---- initial balances
    for k, v in sorted((initial_balances or {}).items()):
        q = _dec(v.get("qty")) if isinstance(v, dict) else None
        uc = _dec(v.get("unit_cost_usd")) if isinstance(v, dict) and v.get("unit_cost_usd") is not None else None
        if q is None or q <= 0 or (isinstance(v, dict) and v.get("unit_cost_usd") is not None and (uc is None or uc < 0)):
            errors.append({"type": "invalid_initial_balance", "token": k})
            continue
        b = book(k)
        cost = None if uc is None else uc * q
        b.add(q, cost)
        st[k]["initial_qty"] += q
        if cost is not None:
            st[k]["initial_cost_usd"] += cost

    # ---- normalise, validate, dedupe, order
    rows, seen = [], set()
    entries = list(entries)
    for i, e in enumerate(entries):
        kind = e.get("kind")
        if kind not in KINDS:
            errors.append({"type": "invalid_entry", "index": i, "reason": "unknown_kind"})
            continue
        fee = _dec(e.get("fee_usd", 0))
        usd = _dec(e.get("usd")) if e.get("usd") is not None else None
        qty = _dec(e.get("qty")) if kind != "fee" else ZERO
        ts = e.get("ts")
        bad = (fee is None or fee < 0 or (e.get("usd") is not None and (usd is None or usd < 0)) or qty is None
               or (kind != "fee" and qty <= 0) or not isinstance(ts, int) or isinstance(ts, bool) or ts < 0)
        if bad:
            errors.append({"type": "invalid_entry", "index": i, "reason": "non_finite_negative_or_malformed"})
            continue
        if kind != "fee" and not e.get("token"):
            errors.append({"type": "invalid_entry", "index": i, "reason": "missing_token"})
            continue
        key = token_key(e.get("chain", "unknown"), e["token"]) if kind != "fee" else None
        tx, li = e.get("tx_hash"), e.get("log_index")
        if tx:
            ident = (str(tx).lower(), li, kind, key)
            if ident in seen:
                errors.append({"type": "duplicate_entry", "index": i, "tx_hash": tx})
                continue
            seen.add(ident)
        cb = _dec(e.get("cost_basis_usd")) if e.get("cost_basis_usd") is not None else None
        if e.get("cost_basis_usd") is not None and (cb is None or cb < 0):
            errors.append({"type": "invalid_entry", "index": i, "reason": "bad_cost_basis"})
            continue
        rows.append({"i": i, "kind": kind, "key": key, "qty": qty, "usd": usd, "fee": fee, "ts": ts, "cb": cb,
                     "tx": tx, "blk": e.get("block_number") or 0, "li": li or 0})
    order = sorted(rows, key=lambda r: (r["ts"], r["blk"], r["li"], r["i"]))
    if [r["i"] for r in order] != [r["i"] for r in rows]:
        errors.append({"type": "out_of_order_input", "note": "entries re-sorted by (ts, block, log_index)"})

    # ---- replay
    for r in order:
        k, kind, q = r["key"], r["kind"], r["qty"]
        if kind == "fee":
            tot["expenses_usd"] += r["fee"]
            continue
        b, s = book(k), st[k]
        if kind in ("buy", "transfer_in"):
            if kind == "buy":
                if r["usd"] is None:
                    errors.append({"type": "missing_usd_value", "index": r["i"], "kind": kind})
                    continue
                cost = r["usd"] + r["fee"]
                s["bought_qty"] += q
                s["buy_cost_usd"] += cost
                tot["fees_in_trades_usd"] += r["fee"]
            else:
                if r["cb"] is not None:
                    cost = r["cb"] + r["fee"]
                elif transfer_in_policy == "fair_value":
                    if r["usd"] is None:
                        errors.append({"type": "missing_usd_value", "index": r["i"], "kind": kind})
                        continue
                    cost = r["usd"] + r["fee"]
                else:
                    cost = None
                    tot["expenses_usd"] += r["fee"]
                s["transferred_in_qty"] += q
                if cost is not None:
                    s["buy_cost_usd"] += cost
            b.add(q, cost)
        elif kind == "sell" or (kind == "transfer_out" and transfer_out_policy == "dispose_at_value"):
            if r["usd"] is None:
                errors.append({"type": "missing_usd_value", "index": r["i"], "kind": kind})
                continue
            net = r["usd"] - r["fee"]
            tot["fees_in_trades_usd"] += r["fee"]
            have = b.qty()
            chunks = b.take(q)
            excess = q - sum((c[0] for c in chunks), ZERO)
            if excess > 0:
                errors.append({"type": "oversold", "token": k, "missing_qty": excess, "tx_hash": r["tx"],
                               "note": "sold more than the ledger holds; excess has unknown basis"})
                s["oversold_qty"] += excess
            if kind == "sell":
                s["sold_qty"] += q                                    # as reported; the oversold part is also booked as `oversold_qty`
            else:
                s["transferred_out_qty"] += q
            s["sell_net_usd"] += net
            pnl_known, unknown_share, known_cost = ZERO, ZERO, ZERO
            for cq, cc in chunks:
                share = net * cq / q
                if cc is None:
                    unknown_share += share
                else:
                    pnl_known += share - cc
                    known_cost += cc
            if excess > 0:
                unknown_share += net * excess / q
            s["realized_pnl_usd"] += pnl_known
            s["realized_unknown_basis_proceeds_usd"] += unknown_share
            closed.append({"token": k, "ts": r["ts"], "qty": q, "net_proceeds_usd": net, "known_cost_usd": known_cost,
                           "pnl_known_usd": pnl_known, "unknown_basis_proceeds_usd": unknown_share,
                           "fully_known": unknown_share == 0, "tx_hash": r["tx"]})
        else:  # transfer_out, no_pnl
            chunks = b.take(q)
            excess = q - sum((c[0] for c in chunks), ZERO)
            if excess > 0:
                errors.append({"type": "oversold", "token": k, "missing_qty": excess, "tx_hash": r["tx"],
                               "note": "transferred out more than the ledger holds"})
                s["oversold_qty"] += excess
            s["transferred_out_qty"] += q
            s["transferred_out_cost_usd"] += sum((c[1] for c in chunks if c[1] is not None), ZERO)
            tot["expenses_usd"] += r["fee"]

    # ---- valuation of what is still held
    marks = {k: _dec(v) for k, v in (marks or {}).items()}
    unreal = ZERO
    missing_marks, tokens = [], {}
    for k, b in books.items():
        s = st[k]
        qk, ck, qu = b.open_known_qty(), b.open_known_cost(), b.open_unknown_qty()
        m = marks.get(k)
        u_known = unk_val = None
        if qk + qu > 0:
            if m is None or m < 0:
                missing_marks.append(k)
            else:
                u_known = qk * m - ck
                unk_val = qu * m
                unreal += u_known
        tokens[k] = {**s, "open_qty": qk + qu, "open_known_qty": qk, "open_known_cost_usd": ck, "open_unknown_qty": qu,
                     "unrealized_pnl_usd": u_known, "open_unknown_basis_value_usd": unk_val,
                     "quantity_conserved": abs(s["initial_qty"] + s["bought_qty"] + s["transferred_in_qty"] + s["oversold_qty"]
                                              - (s["sold_qty"] + s["transferred_out_qty"] + qk + qu)) < Decimal("1e-30")}
    realized = sum((s["realized_pnl_usd"] for s in st.values()), ZERO)
    total = realized + unreal - tot["expenses_usd"]
    # independent cash-flow identity (no lot matching): valid only when every unit has a known cost and nothing left the wallet
    simple = (not any(e["type"] in {"oversold"} for e in errors) and not missing_marks
              and all(s["transferred_out_qty"] == 0 and s["transferred_in_qty"] == 0 for s in st.values())
              and all(b.open_unknown_qty() == 0 for b in books.values())
              and all(s["realized_unknown_basis_proceeds_usd"] == 0 for s in st.values()))
    identity_ok = None
    if simple:
        cash = sum((s["sell_net_usd"] - s["buy_cost_usd"] - s["initial_cost_usd"] for s in st.values()), ZERO)
        value = sum((b.open_known_qty() * marks[k] for k, b in books.items() if b.open_known_qty() > 0), ZERO)
        identity_ok = abs((cash + value - tot["expenses_usd"]) - total) < Decimal("1e-30")
    n_known = [c for c in closed if c["fully_known"]]
    return {
        "method": method, "transfer_in_policy": transfer_in_policy, "transfer_out_policy": transfer_out_policy,
        "totals": {"realized_pnl_usd": realized, "unrealized_pnl_usd": unreal, "expenses_usd": tot["expenses_usd"],
                   "total_pnl_usd": total, "fees_in_trades_usd": tot["fees_in_trades_usd"],
                   "realized_unknown_basis_proceeds_usd": sum((s["realized_unknown_basis_proceeds_usd"] for s in st.values()), ZERO),
                   "transferred_out_cost_usd": sum((s["transferred_out_cost_usd"] for s in st.values()), ZERO),
                   "closed_trades": len(closed), "closed_trades_fully_known": len(n_known),
                   "wins": sum(1 for c in n_known if c["pnl_known_usd"] > 0)},
        "tokens": tokens, "closed": closed, "missing_marks": sorted(missing_marks), "data_errors": errors,
        "checks": {"quantity_conserved": all(t["quantity_conserved"] for t in tokens.values()),
                   "cashflow_identity_ok": identity_ok},
    }


def to_jsonable(x):
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {k: to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x
