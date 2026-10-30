#!/usr/bin/env python3
"""Merge many market_run trade exports into one history and test, WALK-FORWARD, whether wallets that looked skilled in the first part of the
history keep doing better in the second part, after follower costs. One pre-specified test; it is allowed to answer "no evidence".

  python scripts/aggregate.py --runs DIR_WITH_trades_*.jsonl.gz --out reports_dir

Method (fixed before looking at any real data, see docs/WALK_FORWARD.md):
  * only CONFIRMED trades; duplicates from overlapping runs are merged by (tx, token, wallet, side); contradicting duplicates are counted;
  * split the history in time at the midpoint (or --split-ts); selection uses ONLY trades before the split;
  * eligible = wallets with >= MIN_CLOSED closed trades of fully known cost in period A (the future is never used for eligibility);
  * selected = eligible wallets with positive realized PnL in A, best return first, top K (K = min(TOP, 10 % of eligible));
  * evaluation = realized PnL of closed trades after the split (lots bought before it carry over); inactive wallets count as 0;
  * control = the same statistic for random sets of K eligible wallets (fixed seed): p = share of random sets doing at least as well;
  * robustness = rank correlation (Spearman) of A return vs B return, and the result after follower haircuts of 0 / 0.3 % / 1 % per leg;
  * verdict: insufficient_data (< 14 days, < 100 eligible or < 10 selected) / signal (p < 0.05, mean B > 0 at the 0.3 % haircut, rho > 0)
    / no_evidence."""
import argparse
import glob
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ids import token_key  # noqa: E402
from app.pnl import compute_pnl  # noqa: E402

HAIRCUTS = (Decimal(0), Decimal("0.003"), Decimal("0.01"))
PERMUTATIONS = 20000
SEED = 20261012


def load_runs(paths):
    """-> (trades, runs, conflicts). Trades are merged across overlapping runs; first occurrence wins."""
    merged, runs, conflicts = {}, [], 0
    for p in sorted(paths):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            head = json.loads(f.readline())["header"]
            n = 0
            for line in f:
                t = json.loads(line)
                k = (t["tx"], t["t"], t["w"], t["s"])
                old = merged.get(k)
                if old is None:
                    merged[k] = t
                elif (old["q"], old["u"]) != (t["q"], t["u"]):
                    conflicts += 1
                n += 1
            runs.append({"file": Path(p).name, "trades": n, "window": head.get("window"), "chain": head.get("chain"),
                         "method_version": head.get("method_version")})
    return sorted(merged.values(), key=lambda t: (t["ts"], t["b"], t["li"])), runs, conflicts


def newest_method_only(paths):
    """Trades derived by different method versions are not comparable: keep only the files of the newest version (the rest is reported)."""
    vers = {}
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            vers[p] = json.loads(f.readline())["header"].get("method_version") or 0
    if not vers:
        return [], []
    top = max(vers.values())
    return [p for p, v in vers.items() if v == top], sorted(Path(p).name for p, v in vers.items() if v != top)


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r, i = [0.0] * len(v), 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def _entries(trades, chain):
    return [{"kind": t["s"], "ts": t["ts"], "qty": t["q"], "usd": t["u"], "fee_usd": t["g"], "token": t["t"], "chain": chain,
             "tx_hash": t["tx"], "log_index": t["li"], "block_number": t["b"]} for t in trades]


def analyse(trades, *, chain="ethereum", min_closed=5, top=20, split_ts=None, permutations=PERMUTATIONS, seed=SEED):
    conf = [t for t in trades if t["c"] == "confirmed"]
    out = {"trades_total": len(trades), "trades_confirmed": len(conf)}
    if not conf:
        return out | {"verdict": "insufficient_data", "reason": "no confirmed trades"}
    t0, t1 = min(t["ts"] for t in conf), max(t["ts"] for t in conf)
    split = split_ts if split_ts is not None else (t0 + t1) // 2
    out |= {"first_ts": t0, "last_ts": t1, "span_days": round((t1 - t0) / 86400, 2), "split_ts": split}
    marks = {}
    for t in conf:
        marks[token_key(chain, t["t"])] = t["p"]
    by_w = defaultdict(list)
    for t in conf:
        by_w[t["w"]].append(t)

    A, B = {}, {}
    for w, ts in by_w.items():
        before = [t for t in ts if t["ts"] < split]
        if before:
            r = compute_pnl(_entries(before, chain), marks=marks)
            kn = [c for c in r["closed"] if c["fully_known"]]
            cost = sum((c["known_cost_usd"] for c in kn), Decimal(0))
            A[w] = {"n": len(kn), "pnl": sum((c["pnl_known_usd"] for c in kn), Decimal(0)), "cost": cost}
        full = compute_pnl(_entries(ts, chain), marks=marks)
        kb = [c for c in full["closed"] if c["fully_known"] and c["ts"] >= split]
        B[w] = {"n": len(kb), "pnl": sum((c["pnl_known_usd"] for c in kb), Decimal(0)), "cost": sum((c["known_cost_usd"] for c in kb), Decimal(0)),
                "proceeds": sum((c["net_proceeds_usd"] for c in kb), Decimal(0))}
    elig = [w for w, a in A.items() if a["n"] >= min_closed and a["cost"] > 0]
    ret_a = {w: float(A[w]["pnl"] / A[w]["cost"]) for w in elig}
    sel_pool = sorted((w for w in elig if A[w]["pnl"] > 0), key=lambda w: -ret_a[w])
    k = max(0, min(top, math.ceil(len(elig) * 0.10)))
    selected = sel_pool[:k]
    out |= {"eligible_wallets": len(elig), "wallets_positive_in_A": len(sel_pool), "selected": len(selected)}
    if out["span_days"] < 14 or len(elig) < 100 or len(selected) < 10:
        why = [m for ok, m in ((out["span_days"] >= 14, "history shorter than 14 days"), (len(elig) >= 100, "fewer than 100 eligible wallets"),
                               (len(selected) >= 10, "fewer than 10 selected wallets")) if not ok]
        return out | {"verdict": "insufficient_data", "reason": "; ".join(why)}

    def net_b(w, h):
        b = B.get(w) or {"pnl": Decimal(0), "cost": Decimal(0), "proceeds": Decimal(0)}
        return b["pnl"] - h * (b["cost"] + b["proceeds"])
    out["selected_B"] = {}
    for h in HAIRCUTS:
        vals = [float(net_b(w, h)) for w in selected]
        allv = [float(net_b(w, h)) for w in elig]
        out["selected_B"][f"haircut_{h}"] = {"mean_usd": sum(vals) / len(vals), "median_usd": sorted(vals)[len(vals) // 2],
                                             "wallets_positive": sum(1 for v in vals if v > 0), "all_eligible_mean_usd": sum(allv) / len(allv)}
    rng = random.Random(seed)
    base = [float(net_b(w, Decimal(0))) for w in elig]
    obs = out["selected_B"]["haircut_0"]["mean_usd"]
    ge = sum(1 for _ in range(permutations) if sum(rng.sample(base, len(selected))) / len(selected) >= obs)
    out["p_value_vs_random_sets"] = (1 + ge) / (1 + permutations)
    both = [w for w in elig if B[w]["n"] >= 1 and B[w]["cost"] > 0]
    out["rank_correlation_A_vs_B"] = {"wallets": len(both), "spearman": spearman([ret_a[w] for w in both], [float(B[w]["pnl"] / B[w]["cost"]) for w in both])}
    rho = out["rank_correlation_A_vs_B"]["spearman"]
    h3 = out["selected_B"][f"haircut_{Decimal('0.003')}"]["mean_usd"]
    out["verdict"] = "signal" if (out["p_value_vs_random_sets"] < 0.05 and h3 > 0 and rho is not None and rho > 0) else "no_evidence"
    out["note"] = "one pre-specified test on one split; 'signal' is a reason to look closer (more data, other split), never a go-live decision"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-closed", type=int, default=5)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--split-ts", type=int)
    a = ap.parse_args()
    paths = glob.glob(str(Path(a.runs) / "**" / "trades_*.jsonl.gz"), recursive=True)
    if not paths:
        print("no trade exports found", file=sys.stderr)
        return 2
    paths, ignored = newest_method_only(paths)
    trades, runs, conflicts = load_runs(paths)
    res = analyse(trades, min_closed=a.min_closed, top=a.top, split_ts=a.split_ts)
    rep = {"runs": len(runs), "conflicting_duplicates": conflicts, "ignored_older_method_files": ignored, "result": res, "files": runs}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "aggregate.json").write_text(json.dumps(rep, indent=1, default=str))
    (out / "aggregate.md").write_text("# Walk-forward over merged runs\n\n```json\n" + json.dumps(rep, indent=1, default=str) + "\n```\n")
    print(json.dumps({k: res.get(k) for k in ("verdict", "span_days", "eligible_wallets", "selected", "p_value_vs_random_sets", "reason")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
