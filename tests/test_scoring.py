import pytest
from pydantic import ValidationError

from app.config import CONFIG
from app.models import ScoreRequest, WalletStats
from app.scoring import (cohort_score, evaluate_cohort, flow_ratio,
                         is_eligible_confirmer, score_wallet, wallet_status)


def mk(wallet="a", events=40, wins=36, losses=4, avg_return=3.0, token_events=10, token_wins=9,
       acc=1_000_000, dist=0, cluster=None, pump=0, cex=1.0, anomaly=2.0, indep=0):
    return WalletStats(wallet=wallet, events=events, wins=wins, losses=losses, avg_return=avg_return,
                       token_events=token_events, token_wins=token_wins,
                       accumulation_usd=acc, distribution_usd=dist, cluster_id=cluster,
                       pump_distance_pct=pump, cex_outflow_share=cex, volume_anomaly=anomaly,
                       independent_confirmations=indep)


LIQ = 10_000_000


# ------------------------------------------------------------------ wallet score
def test_small_sample_is_shrunk():
    one_hit = mk(events=1, wins=1, losses=0, token_events=1, token_wins=1, indep=3)
    veteran = mk(events=40, wins=40, losses=0, token_events=10, token_wins=10, indep=3)
    assert score_wallet(one_hit) < 100
    assert score_wallet(one_hit) < score_wallet(veteran) - 5      # clearly discounted vs. a real record


def test_distributing_wallet_is_capped_despite_perfect_history():
    w = mk(events=50, wins=50, losses=0, token_events=10, token_wins=10,
           acc=0, dist=1_000_000, indep=5)
    assert wallet_status(w) == "DISTRIBUTING"
    assert score_wallet(w) <= CONFIG.distributing_score_cap


def test_flow_classification():
    assert wallet_status(mk(acc=0, dist=0)) == "NO_FLOW" and flow_ratio(mk(acc=0, dist=0)) is None
    assert wallet_status(mk(acc=600, dist=400)) == "ACCUMULATING"     # ratio +0.2 (boundary)
    assert wallet_status(mk(acc=550, dist=450)) == "NEUTRAL"
    assert wallet_status(mk(acc=400, dist=600)) == "DISTRIBUTING"


def test_eligible_confirmer_rules():
    assert is_eligible_confirmer(mk())
    assert not is_eligible_confirmer(mk(events=19, wins=18, losses=1))          # history too short
    assert not is_eligible_confirmer(mk(wins=15, losses=25))                    # hit rate < 50%
    assert not is_eligible_confirmer(mk(avg_return=-1))                         # negative PnL
    assert not is_eligible_confirmer(mk(acc=0, dist=1_000))                     # distributing


def test_inconsistent_wallet_counts_rejected():
    with pytest.raises(ValidationError):
        mk(events=10, wins=8, losses=5)
    with pytest.raises(ValidationError):
        mk(token_events=2, token_wins=3)


# ------------------------------------------------------------------ cohort score
def test_cohort_score_has_no_confirmation_bonus():
    assert cohort_score([80, 80], LIQ) == 80          # signature no longer takes confirmations
    assert cohort_score([80, 80], 1_000_000) == 60    # liquidity penalty still applies
    assert cohort_score([], LIQ) == 0


# ------------------------------------------------------------------ evaluate_cohort
def test_two_independent_wallets_form_a_valid_signal():
    ev = evaluate_cohort([mk("a", cluster="c1"), mk("b", cluster="c2")], LIQ)
    assert ev["independent_confirmations"] == 2
    assert ev["signal_valid"] is True and ev["reasons"] == []
    assert ev["cohort_score"] >= CONFIG.strong_signal_score
    assert ev["confidence"] >= CONFIG.min_confidence


def test_same_cluster_counts_as_one_confirmation():
    ev = evaluate_cohort([mk("a", cluster="same"), mk("b", cluster="same")], LIQ)
    assert ev["independent_confirmations"] == 1
    assert "insufficient_independent_confirmations" in ev["reasons"]
    assert ev["signal_valid"] is False


def test_len_of_wallets_is_not_confirmations():
    # 3 wallets, but only one is an eligible accumulating confirmer
    ws = [mk("a"), mk("b", acc=0, dist=1_000_000), mk("c", events=3, wins=3, losses=0)]
    ev = evaluate_cohort(ws, LIQ)
    assert ev["independent_confirmations"] == 1 and ev["signal_valid"] is False


def test_client_supplied_confirmations_are_ignored():
    base = [mk("a", cluster="x"), mk("b", cluster="x")]
    spoof = [mk("a", cluster="x", indep=5), mk("b", cluster="x", indep=5)]
    a, b = evaluate_cohort(base, LIQ), evaluate_cohort(spoof, LIQ)
    assert [r["score"] for r in a["wallets"]] == [r["score"] for r in b["wallets"]]
    assert a["signal_valid"] == b["signal_valid"] is False


def test_confirmation_is_counted_once_not_twice():
    # Each wallet already includes the other cluster (15% term). Cohort score must equal the plain mean.
    ev = evaluate_cohort([mk("a", cluster="c1"), mk("b", cluster="c2")], LIQ)
    scores = [r["score"] for r in ev["wallets"]]
    assert ev["cohort_score"] == round(sum(scores) / len(scores), 2)


def test_distributing_cohort_blocks_signal():
    ws = [mk("a", cluster="c1"), mk("b", cluster="c2"),
          mk("whale", cluster="c3", acc=0, dist=10_000_000)]
    ev = evaluate_cohort(ws, LIQ)
    assert ev["distribution_share"] > CONFIG.max_distribution_share
    assert "cohort_distributing" in ev["reasons"] and ev["signal_valid"] is False
    whale = next(r for r in ev["wallets"] if r["wallet"] == "whale")
    assert whale["status"] == "DISTRIBUTING" and whale["score"] <= CONFIG.distributing_score_cap
    assert whale["qualified"] is False


def test_moderate_distribution_lowers_confidence():
    clean = evaluate_cohort([mk("a", cluster="c1"), mk("b", cluster="c2")], LIQ)
    mixed = evaluate_cohort([mk("a", cluster="c1", acc=1_000_000, dist=200_000),
                             mk("b", cluster="c2")], LIQ)
    assert mixed["confidence"] < clean["confidence"]


def test_low_liquidity_is_reported_not_assumed():
    ev = evaluate_cohort([mk("a", cluster="c1"), mk("b", cluster="c2")], 500_000)
    assert "low_liquidity" in ev["reasons"] and ev["signal_valid"] is False


def test_liquidity_is_a_required_input():
    with pytest.raises(ValidationError):
        ScoreRequest(token="QNT", wallets=[mk("a")])          # no liquidity_usd -> must fail
    with pytest.raises(ValidationError):
        ScoreRequest(token="QNT", wallets=[mk("a")], liquidity_usd=-1)


def test_duplicate_wallets_rejected():
    with pytest.raises(ValidationError):
        ScoreRequest(token="QNT", wallets=[mk("a"), mk("a")], liquidity_usd=LIQ)
