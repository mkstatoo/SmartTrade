"""INDEPENDENT reference for wallet PnL, used only to cross-check app/pnl.py.

Deliberately a different algorithm: integer quantities, one cost per UNIT in a deque (Fractions, exact), instead of the
production chunk/lot arithmetic in Decimal. Same accounting rules, none of the same code."""
from collections import deque
from fractions import Fraction as F


def ref_pnl(ops, initial, method, marks, in_policy="unknown_basis"):
    """ops: dicts kind/qty(int)/usd(F|None)/fee(F)/cb(F|None) already in replay order. initial: {tok: (qty, unit_cost F|None)}."""
    units, pools = {}, {}
    realized = unknown = expenses = F(0)
    excess_total = {}
    for tok, (q, uc) in initial.items():
        units[tok] = deque([uc] * q)
        pools[tok] = [q if uc is not None else 0, (uc * q) if uc is not None else F(0), 0 if uc is not None else q]
    def ensure(t):
        units.setdefault(t, deque())
        pools.setdefault(t, [0, F(0), 0])
    for o in ops:
        t, k, q = o.get("tok"), o["kind"], o.get("qty", 0)
        if k == "fee":
            expenses += o["fee"]
            continue
        ensure(t)
        if k in ("buy", "transfer_in"):
            if k == "buy":
                cost = o["usd"] + o["fee"]
            elif o.get("cb") is not None:
                cost = o["cb"] + o["fee"]
            elif in_policy == "fair_value":
                cost = o["usd"] + o["fee"]
            else:
                cost = None
                expenses += o["fee"]
            if method == "fifo":
                units[t].extend([None if cost is None else cost / q] * q)
            elif cost is None:
                pools[t][2] += q
            else:
                pools[t][0] += q
                pools[t][1] += cost
        elif k in ("sell", "transfer_out"):
            sale = k == "sell"
            net = (o["usd"] - o["fee"]) if sale else None
            if not sale:
                expenses += o["fee"]
            if method == "fifo":
                took = min(q, len(units[t]))
                for _ in range(took):
                    c = units[t].popleft()
                    if sale:
                        if c is None:
                            unknown += net / q
                        else:
                            realized += net / q - c
                if sale:
                    unknown += net / q * (q - took)
                if q - took:
                    excess_total[t] = excess_total.get(t, 0) + (q - took)
            else:
                kq, kc, uq = pools[t]
                total = kq + uq
                take = min(q, total)
                if total > 0 and take > 0:
                    tk, tu = F(take) * kq / total, F(take) * uq / total
                    cost_k = kc * tk / kq if kq else F(0)
                    if sale:
                        realized += net * tk / q - cost_k
                        unknown += net * tu / q
                    pools[t] = [kq - tk, kc - cost_k, uq - tu]
                if sale:
                    unknown += net * F(q - take) / q
                if q > take:
                    excess_total[t] = excess_total.get(t, 0) + (q - take)
    unreal = F(0)
    for t in units:
        if method == "fifo":
            kn = [c for c in units[t] if c is not None]
            unreal += len(kn) * marks[t] - sum(kn, F(0))
        else:
            unreal += pools[t][0] * marks[t] - pools[t][1]
    return {"realized": realized, "unrealized": unreal, "unknown": unknown, "expenses": expenses}
