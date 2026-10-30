"""scripts/aggregate.py: the walk-forward test must find planted skill, must NOT find skill in pure luck, and must never use the future
to select. All data here are SYNTHETIC test fixtures generated with a fixed seed (labelled as such); no real wallet is involved."""
import gzip
import importlib.util
import json
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aggregate", ROOT / "scripts" / "aggregate.py")
agg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agg)

DAY = 86400
T0 = 1_760_000_000
TOKEN = "0x" + "ab" * 20


def wallet(i):
    return "0x" + format(i + 1, "040x")


def synthetic(seed, *, wallets=400, rounds=10, days=28, skilled=0, skill_until=None, edge=0.06, noise=0.06):
    """Each wallet makes `rounds` round trips (buy then sell ~1 day later). Edge of the sell vs the buy price: skilled wallets have a positive
    mean edge (optionally only before `skill_until`), everyone else mean 0. Fixed seed -> deterministic."""
    rng = random.Random(seed)
    out, k = [], 0
    for i in range(wallets):
        is_skilled = i < skilled
        for r in range(rounds):
            tb = T0 + int(rng.uniform(0, days - 2) * DAY)
            ts_ = tb + DAY
            px = rng.uniform(0.5, 2.0)
            good = is_skilled and (skill_until is None or tb < skill_until)
            e = rng.gauss(edge if good else 0.0, noise)
            usd = rng.uniform(200, 2000)
            for side, ts, price in (("buy", tb, px), ("sell", ts_, px * (1 + e))):
                k += 1
                out.append({"tx": "0x" + format(k, "064x"), "b": ts // 12, "ts": ts, "w": wallet(i), "t": TOKEN, "s": side,
                            "q": str(usd / px), "u": str(usd / px * price), "p": str(price), "g": "0.5", "c": "confirmed", "li": 0, "gp": True})
    return sorted(out, key=lambda t: (t["ts"], t["b"]))


def test_pure_luck_is_rarely_called_a_signal():
    hits = 0
    for seed in range(12):
        res = agg.analyse(synthetic(seed), permutations=2000)
        assert res["verdict"] in ("no_evidence", "signal"), res
        hits += res["verdict"] == "signal"
    assert hits <= 1          # nominal false-positive rate is 5 %; the extra conditions make it lower


def test_planted_skill_is_found_after_costs():
    res = agg.analyse(synthetic(1, skilled=60), permutations=3000)
    assert res["verdict"] == "signal", res
    assert res["p_value_vs_random_sets"] < 0.05 and res["rank_correlation_A_vs_B"]["spearman"] > 0
    assert res["selected_B"]["haircut_0.003"]["mean_usd"] > 0


def test_skill_that_disappears_after_the_split_is_not_a_signal():
    split = T0 + 14 * DAY
    res = agg.analyse(synthetic(2, skilled=60, skill_until=split), split_ts=split, permutations=3000)
    assert res["verdict"] == "no_evidence", res


def test_costs_can_erase_a_small_edge():
    res = agg.analyse(synthetic(3, skilled=60, edge=0.012), permutations=2000)
    assert res["selected_B"]["haircut_0.01"]["mean_usd"] < res["selected_B"]["haircut_0"]["mean_usd"]
    assert res["selected_B"]["haircut_0.01"]["mean_usd"] < 0 or res["verdict"] != "signal"


def test_short_history_or_few_wallets_is_insufficient_not_a_verdict():
    assert agg.analyse(synthetic(4, days=9), permutations=500)["verdict"] == "insufficient_data"
    assert agg.analyse(synthetic(4, wallets=60), permutations=500)["verdict"] == "insufficient_data"
    assert agg.analyse([])["verdict"] == "insufficient_data"


def test_selection_never_uses_the_future():
    base = synthetic(5, skilled=40)
    split = T0 + 14 * DAY
    r1 = agg.analyse(base, split_ts=split, permutations=500)
    shocked = [dict(t, u=str(float(t["u"]) * 5)) if (t["ts"] >= split and t["s"] == "sell") else t for t in base]
    r2 = agg.analyse(shocked, split_ts=split, permutations=500)
    assert (r1["eligible_wallets"], r1["wallets_positive_in_A"], r1["selected"]) == (r2["eligible_wallets"], r2["wallets_positive_in_A"], r2["selected"])
    assert r1["selected_B"] != r2["selected_B"]        # the evaluation did change, the selection did not


def test_mismatch_trades_are_ignored():
    base = synthetic(6, skilled=40)
    noisy = base + [dict(t, c="mismatch", u=str(float(t["u"]) * 3), tx=t["tx"] + "x") for t in base if t["s"] == "sell"]
    a, b = agg.analyse(base, permutations=300), agg.analyse(noisy, permutations=300)
    assert a["selected_B"] == b["selected_B"] and b["trades_total"] == 2 * a["trades_total"] - sum(1 for t in base if t["s"] == "buy")


def write(path, trades, window=(0, 1)):
    with gzip.open(path, "wt") as f:
        f.write(json.dumps({"header": {"chain": "ethereum", "window": {"watch": list(window)}, "format": 1}}) + "\n")
        for t in trades:
            f.write(json.dumps(t) + "\n")


def test_overlapping_runs_are_merged_once_and_contradictions_counted(tmp_path):
    base = synthetic(7, wallets=50, rounds=3)
    half = len(base) // 2
    write(tmp_path / "trades_a.jsonl.gz", base[: half + 20])
    write(tmp_path / "trades_b.jsonl.gz", base[half - 20:])            # 40 trades appear in both runs
    merged, runs, conflicts = agg.load_runs([str(tmp_path / "trades_a.jsonl.gz"), str(tmp_path / "trades_b.jsonl.gz")])
    assert len(merged) == len(base) and conflicts == 0 and len(runs) == 2
    bad = [dict(t, u="1.0") if i == 0 else t for i, t in enumerate(base[half - 20:])]
    write(tmp_path / "trades_c.jsonl.gz", bad)
    _, _, conflicts = agg.load_runs([str(tmp_path / "trades_a.jsonl.gz"), str(tmp_path / "trades_c.jsonl.gz")])
    assert conflicts == 1


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys
    write(tmp_path / "trades_x.jsonl.gz", synthetic(8, skilled=40))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "aggregate.py"), "--runs", str(tmp_path), "--out", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads((tmp_path / "o" / "aggregate.json").read_text())
    assert rep["runs"] == 1 and rep["result"]["verdict"] in ("signal", "no_evidence")


def test_only_the_newest_method_version_is_used(tmp_path):
    for name, v in (("trades_old.jsonl.gz", 1), ("trades_new1.jsonl.gz", 2), ("trades_new2.jsonl.gz", 2)):
        with gzip.open(tmp_path / name, "wt") as f:
            f.write(json.dumps({"header": {"chain": "ethereum", "method_version": v}}) + "\n")
    keep, ignored = agg.newest_method_only([str(tmp_path / n) for n in ("trades_old.jsonl.gz", "trades_new1.jsonl.gz", "trades_new2.jsonl.gz")])
    assert sorted(Path(k).name for k in keep) == ["trades_new1.jsonl.gz", "trades_new2.jsonl.gz"] and ignored == ["trades_old.jsonl.gz"]
