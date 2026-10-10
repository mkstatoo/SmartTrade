"""Wallet PnL: hand-computed examples, independent differential testing, identities, metamorphic checks, bad data.
All ledgers here are accounting FIXTURES (made-up numbers chosen to be checkable by hand), not market data."""
import random
from decimal import Decimal as D
from fractions import Fraction as F

import pytest
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.main import create_app
from app.pnl import compute_pnl
from app.store import MemoryStore
from conftest import H
from reference_pnl import ref_pnl

TOK = "base:0xt"


def E(kind, ts, qty=0, usd=None, fee=0, **kw):
    d = dict(kind=kind, ts=ts, qty=qty, fee_usd=fee, token="0xT", chain="base", **kw)
    if usd is not None:
        d["usd"] = usd
    return d


def tot(r, k):
    return r["totals"][k]


# ------------------------------------------------------------------ worked examples (arithmetic in docs/PNL_VALIDATION.md)
LEDGER1 = [E("buy", 1, 10, 100, 1), E("buy", 2, 10, 200, 1), E("sell", 3, 15, 450, 3)]


def test_example1_fifo():
    r = compute_pnl(LEDGER1, marks={TOK: 25})
    # lots: 10 @ (100+1)/10 = 10.10 and 10 @ (200+1)/10 = 20.10; sell 15 net 450-3 = 447; cost 101 + 5*20.10 = 201.50
    assert tot(r, "realized_pnl_usd") == D("245.5")
    assert r["tokens"][TOK]["open_known_cost_usd"] == D("100.5") and r["tokens"][TOK]["open_qty"] == 5
    assert tot(r, "unrealized_pnl_usd") == D("24.5")               # 5*25 - 100.5
    assert tot(r, "total_pnl_usd") == D("270")
    assert r["checks"] == {"quantity_conserved": True, "cashflow_identity_ok": True}


def test_example1_average_cost_same_total_different_split():
    r = compute_pnl(LEDGER1, method="average", marks={TOK: 25})
    # pool (101+201)/20 = 15.10 per unit; 15 sold cost 226.50 -> 447 - 226.50 = 220.50
    assert tot(r, "realized_pnl_usd") == D("220.5") and tot(r, "unrealized_pnl_usd") == D("49.5")
    assert tot(r, "total_pnl_usd") == D("270")


def test_example2_initial_balance_with_and_without_cost():
    r = compute_pnl([E("sell", 1, 40, 400, 4)], initial_balances={TOK: {"qty": 100}}, marks={TOK: 11})
    assert tot(r, "realized_pnl_usd") == 0 and tot(r, "realized_unknown_basis_proceeds_usd") == D("396")
    assert r["tokens"][TOK]["open_unknown_qty"] == 60 and r["tokens"][TOK]["open_unknown_basis_value_usd"] == D("660")
    assert tot(r, "unrealized_pnl_usd") == 0                                   # unknown basis never fakes a gain
    r = compute_pnl([E("sell", 1, 40, 400, 4)], initial_balances={TOK: {"qty": 100, "unit_cost_usd": 5}}, marks={TOK: 11})
    assert tot(r, "realized_pnl_usd") == D("196")                              # 396 - 40*5
    assert tot(r, "unrealized_pnl_usd") == D("360")                            # 60*11 - 300


def test_example3_oversell_is_flagged_not_hidden():
    r = compute_pnl([E("buy", 1, 5, 50), E("sell", 2, 8, 120)], marks={TOK: 1})
    assert tot(r, "realized_pnl_usd") == D("25")                               # 5/8*120 = 75 vs cost 50
    assert tot(r, "realized_unknown_basis_proceeds_usd") == D("45")            # 3/8*120
    err = [e for e in r["data_errors"] if e["type"] == "oversold"]
    assert len(err) == 1 and err[0]["missing_qty"] == 3
    assert r["tokens"][TOK]["open_qty"] == 0 and r["checks"]["quantity_conserved"]


def test_example4_transfers_fees_and_policies():
    base = [E("buy", 1, 10, 100)]
    r = compute_pnl(base + [E("transfer_out", 2, 4, fee=2)], marks={TOK: 12})
    assert r["tokens"][TOK]["open_known_cost_usd"] == 60 and tot(r, "transferred_out_cost_usd") == 40
    assert tot(r, "expenses_usd") == 2 and tot(r, "realized_pnl_usd") == 0
    assert tot(r, "total_pnl_usd") == D("10")                                  # 6*12 - 60 - gas 2
    r = compute_pnl(base + [E("transfer_out", 2, 4, usd=60, fee=2)], transfer_out_policy="dispose_at_value", marks={TOK: 12})
    assert tot(r, "realized_pnl_usd") == D("18")                               # (60-2) - 4*10 = 18
    r = compute_pnl([E("transfer_in", 1, 3, 33), E("sell", 2, 3, 60)])
    assert tot(r, "realized_pnl_usd") == 0 and tot(r, "realized_unknown_basis_proceeds_usd") == 60
    r = compute_pnl([E("transfer_in", 1, 3, 33), E("sell", 2, 3, 60)], transfer_in_policy="fair_value")
    assert tot(r, "realized_pnl_usd") == 27                                    # airdrop booked at fair value 33
    r = compute_pnl([E("transfer_in", 1, 3, cost_basis_usd=30), E("sell", 2, 3, 60)])
    assert tot(r, "realized_pnl_usd") == 30                                    # internal transfer carries its basis
    r = compute_pnl([E("fee", 1, fee=7), E("buy", 2, 1, 10)], marks={TOK: 10})
    assert tot(r, "expenses_usd") == 7 and tot(r, "total_pnl_usd") == -7


def test_losses_and_win_rate():
    r = compute_pnl([E("buy", 1, 10, 100), E("sell", 2, 5, 40), E("sell", 3, 5, 70)])
    assert [c["pnl_known_usd"] for c in r["closed"]] == [-10, 20]
    assert r["totals"]["wins"] == 1 and r["totals"]["closed_trades_fully_known"] == 2


# ------------------------------------------------------------------ bad data never crashes or changes the numbers
def test_bad_rows_are_skipped_and_reported():
    clean = compute_pnl(LEDGER1, marks={TOK: 25})
    bad = [E("buy", 5, float("nan"), 1), E("buy", 5, 1, float("inf")), E("buy", 5, 1, -3), E("buy", 5, 1, 1, -1),
           E("sell", 5, 0, 1), {"kind": "bogus", "ts": 1}, E("buy", -1, 1, 1), E("buy", 1.5, 1, 1), E("sell", 5, 1),
           dict(kind="buy", ts=5, qty=1, usd=1), E("buy", 5, True, 1)]
    r = compute_pnl(LEDGER1 + bad, marks={TOK: 25})
    assert {k: tot(r, k) for k in ("realized_pnl_usd", "unrealized_pnl_usd", "total_pnl_usd")} == \
           {k: tot(clean, k) for k in ("realized_pnl_usd", "unrealized_pnl_usd", "total_pnl_usd")}
    kinds = [e["type"] for e in r["data_errors"]]
    assert kinds.count("invalid_entry") >= 8 and "missing_usd_value" in kinds


def test_duplicates_by_tx_and_log_are_ignored_once():
    a = E("buy", 1, 10, 100, tx_hash="0xAA", log_index=3)
    r = compute_pnl([a, dict(a), dict(a, log_index=4)], marks={TOK: 10})
    assert r["tokens"][TOK]["bought_qty"] == 20 and sum(e["type"] == "duplicate_entry" for e in r["data_errors"]) == 1


def test_out_of_order_input_is_sorted_and_flagged():
    shuffled = [LEDGER1[2], LEDGER1[0], LEDGER1[1]]
    r = compute_pnl(shuffled, marks={TOK: 25})
    assert tot(r, "total_pnl_usd") == D("270") and any(e["type"] == "out_of_order_input" for e in r["data_errors"])


def test_same_timestamp_uses_block_and_log_index():
    led = [E("sell", 5, 5, 60, block_number=10, log_index=2), E("buy", 5, 5, 40, block_number=10, log_index=1)]
    r = compute_pnl(led)
    assert tot(r, "realized_pnl_usd") == 20 and not any(e["type"] == "oversold" for e in r["data_errors"])


def test_missing_mark_is_reported_not_guessed():
    r = compute_pnl([E("buy", 1, 10, 100)])
    assert r["missing_marks"] == [TOK] and tot(r, "unrealized_pnl_usd") == 0 and r["tokens"][TOK]["unrealized_pnl_usd"] is None


def test_invalid_initial_balances_reported():
    r = compute_pnl([], initial_balances={"a": {"qty": 0}, "b": {"qty": float("nan")}, "c": {"qty": 1, "unit_cost_usd": -1}})
    assert [e["type"] for e in r["data_errors"]] == ["invalid_initial_balance"] * 3


def test_token_identity_is_canonical():
    led = [dict(E("buy", 1, 10, 100), token="0xAbC"), dict(E("sell", 2, 10, 150), token="0xabc")]
    assert tot(compute_pnl(led), "realized_pnl_usd") == 50


# ------------------------------------------------------------------ independent differential test
def cents(x: F) -> str:
    return f"{float(x):.2f}"


def gen_case(rng):
    toks = ["0xa", "0xb"]
    initial_prod, initial_ref = {}, {}
    for t in toks:
        if rng.random() < .5:
            q, uc = rng.randint(1, 30), (None if rng.random() < .4 else F(rng.randint(1, 5000), 100))
            initial_prod[f"base:{t}"] = {"qty": q} if uc is None else {"qty": q, "unit_cost_usd": cents(uc)}
            initial_ref[f"base:{t}"] = (q, None if uc is None else F(cents(uc)))
    prod, ref = [], []
    for i in range(rng.randint(1, 25)):
        t, k = rng.choice(toks), rng.choice(["buy", "buy", "sell", "sell", "sell", "transfer_out", "transfer_in", "fee"])
        q = rng.randint(1, 20)
        usd = F(rng.randint(0, 100_000), 100)
        fee = F(rng.randint(0, 500), 100)
        e = {"kind": k, "ts": i + 1, "chain": "base", "token": t, "qty": q, "fee_usd": cents(fee)}
        o = {"kind": k, "tok": f"base:{t}", "qty": q, "fee": F(cents(fee))}
        if k in ("buy", "sell"):
            e["usd"], o["usd"] = cents(usd), F(cents(usd))
        if k == "transfer_in" and rng.random() < .5:
            e["cost_basis_usd"], o["cb"] = cents(usd), F(cents(usd))
        if k == "fee":
            e.pop("token"); e.pop("qty"); o.pop("tok"); o.pop("qty")
        prod.append(e); ref.append(o)
    marks = {f"base:{t}": F(rng.randint(1, 5000), 100) for t in toks}
    return prod, ref, initial_prod, initial_ref, marks


@pytest.mark.parametrize("method", ["fifo", "average"])
def test_differential_against_independent_reference(method):
    rng = random.Random(20261010)
    for n in range(1500):
        prod, ref, ip, ir, marks = gen_case(rng)
        got = compute_pnl(prod, initial_balances=ip, method=method, marks={k: cents(v) for k, v in marks.items()})
        want = ref_pnl(ref, ir, method, {k: F(cents(v)) for k, v in marks.items()})
        for gk, wk in (("realized_pnl_usd", "realized"), ("unrealized_pnl_usd", "unrealized"),
                       ("realized_unknown_basis_proceeds_usd", "unknown"), ("expenses_usd", "expenses")):
            g = got["totals"][gk]
            w = D(want[wk].numerator) / D(want[wk].denominator)
            assert abs(g - w) < D("1e-25"), (method, n, gk, g, w)
        assert got["checks"]["quantity_conserved"]


# ------------------------------------------------------------------ identities and metamorphic properties
def simple_case(rng):
    """Only buys/sells of tokens we hold (no transfers, no oversell, all costs known)."""
    held, led, ts = 0, [], 0
    for _ in range(rng.randint(2, 30)):
        ts += 1
        if held == 0 or rng.random() < .5:
            q = rng.randint(1, 20)
            led.append(E("buy", ts, q, cents(F(rng.randint(1, 90_000), 100)), cents(F(rng.randint(0, 400), 100))))
            held += q
        else:
            q = rng.randint(1, held)
            led.append(E("sell", ts, q, cents(F(rng.randint(1, 90_000), 100)), cents(F(rng.randint(0, 400), 100))))
            held -= q
    return led


def test_cashflow_identity_holds_for_random_ledgers_and_both_methods_agree_on_total():
    rng = random.Random(7)
    for _ in range(800):
        led = simple_case(rng)
        mark = cents(F(rng.randint(1, 9000), 100))
        a = compute_pnl(led, marks={TOK: mark})
        b = compute_pnl(led, method="average", marks={TOK: mark})
        assert a["checks"]["cashflow_identity_ok"] is True and b["checks"]["cashflow_identity_ok"] is True
        assert abs(tot(a, "total_pnl_usd") - tot(b, "total_pnl_usd")) < D("1e-30")      # method only moves PnL between realised/unrealised


def test_scaling_usd_scales_pnl_and_scaling_quantity_changes_nothing():
    rng = random.Random(11)
    for _ in range(200):
        led = simple_case(rng)
        base = compute_pnl(led, marks={TOK: "10"})
        usd_x3 = [dict(e, usd=cents(F(e["usd"]) * 3), fee_usd=cents(F(e["fee_usd"]) * 3)) for e in led]
        r3 = compute_pnl(usd_x3, marks={TOK: "30"})
        assert abs(tot(r3, "total_pnl_usd") - 3 * tot(base, "total_pnl_usd")) < D("1e-25")
        qty_x7 = [dict(e, qty=e["qty"] * 7) for e in led]
        r7 = compute_pnl(qty_x7, marks={TOK: str(D(10) / 7)})
        assert abs(tot(r7, "total_pnl_usd") - tot(base, "total_pnl_usd")) < D("1e-25")


def test_splitting_a_sell_pro_rata_does_not_change_fifo_realised():
    led = [E("buy", 1, 10, 100, 1), E("buy", 2, 10, 300, 2), E("sell", 3, 14, 600, 6)]
    split = [led[0], led[1], E("sell", 3, 6, "257.142857142857142857", "2.571428571428571428"),
             E("sell", 3, 8, "342.857142857142857143", "3.428571428571428572")]
    a, b = compute_pnl(led), compute_pnl(split)
    assert abs(tot(a, "realized_pnl_usd") - tot(b, "realized_pnl_usd")) < D("1e-15")


def test_internal_round_trip_with_carried_basis_changes_nothing():
    base = compute_pnl([E("buy", 1, 10, 100), E("sell", 5, 10, 150)])
    rt = compute_pnl([E("buy", 1, 10, 100), E("transfer_out", 2, 10), E("transfer_in", 3, 10, cost_basis_usd=100),
                      E("sell", 5, 10, 150)])
    assert tot(rt, "realized_pnl_usd") == tot(base, "realized_pnl_usd") == 50


# ------------------------------------------------------------------ API
def test_api_wallet_pnl_roundtrip_and_validation():
    body = {"entries": [{"kind": "buy", "ts": 1, "chain": "base", "token": "0xT", "qty": 10, "usd": 100, "fee_usd": 1},
                        {"kind": "buy", "ts": 2, "chain": "base", "token": "0xT", "qty": 10, "usd": 200, "fee_usd": 1},
                        {"kind": "sell", "ts": 3, "chain": "base", "token": "0xT", "qty": 15, "usd": 450, "fee_usd": 3}],
            "marks": {TOK: 25}}
    with TestClient(create_app(MemoryStore(), ReplayClock()), headers=H) as c:
        r = c.post("/wallet/pnl", json=body).json()
        assert r["totals"]["realized_pnl_usd"] == 245.5 and r["totals"]["total_pnl_usd"] == 270
        assert c.post("/wallet/pnl", json={**body, "method": "lifo"}).status_code == 422
        assert c.post("/wallet/pnl", content='{"entries":[{"kind":"buy","ts":1,"qty":NaN}]}',
                      headers={**H, "Content-Type": "application/json"}).status_code == 422
        assert c.post("/wallet/pnl", json={"entries": [], "marks": {TOK: -1}}).status_code == 422
        assert c.post("/wallet/pnl", json={"entries": []}, headers={"X-Research-Key": ""}).status_code == 401
