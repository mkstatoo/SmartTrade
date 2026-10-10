from .config import CONFIG, Config
from .models import WalletStats


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ----------------------------------------------------------------- wallet level

def flow_ratio(w: WalletStats) -> float | None:
    """(accumulation - distribution) / total, in [-1, 1]. None when there is no flow data."""
    total = w.accumulation_usd + w.distribution_usd
    if total <= 0:
        return None
    return (w.accumulation_usd - w.distribution_usd) / total


def wallet_status(w: WalletStats, cfg: Config = CONFIG) -> str:
    r = flow_ratio(w)
    if r is None:
        return "NO_FLOW"
    if r >= cfg.flow_threshold:
        return "ACCUMULATING"
    if r <= -cfg.flow_threshold:
        return "DISTRIBUTING"
    return "NEUTRAL"


def score_wallet(w: WalletStats, cfg: Config = CONFIG) -> float:
    # Historical consistency: shrink small samples toward 50.
    raw = (w.wins / w.events * 100) if w.events else 50
    sample_factor = min(1.0, w.events / 20)
    consistency = 50 + (raw - 50) * sample_factor

    token_raw = (w.token_wins / w.token_events * 100) if w.token_events else 50
    token_factor = min(1.0, w.token_events / 8)
    token_specific = 50 + (token_raw - 50) * token_factor

    total_flow = w.accumulation_usd + w.distribution_usd
    accum = (w.accumulation_usd / total_flow * 100) if total_flow else 50

    confirmations = min(100, w.independent_confirmations / 5 * 100)
    # Lower distance from a recent pump is better for copying a fresh entry.
    distance = clamp(100 - max(0, w.pump_distance_pct) * 2)

    cex = clamp(w.cex_outflow_share * 100)
    anomaly = clamp(w.volume_anomaly * 50)

    score = (
        .25 * consistency +
        .20 * token_specific +
        .20 * accum +
        .15 * confirmations +
        .10 * distance +
        .05 * cex +
        .05 * anomaly
    )
    score = clamp(score)
    # A wallet that is net-selling right now is not a buy signal, however good its history.
    if wallet_status(w, cfg) == "DISTRIBUTING":
        score = min(score, cfg.distributing_score_cap)
    return round(score, 2)


def is_eligible_confirmer(w: WalletStats, cfg: Config = CONFIG) -> bool:
    """Can this wallet count as an independent confirmation? (METHODOLOGY section A/D)"""
    return (
        wallet_status(w, cfg) == "ACCUMULATING"
        and w.events >= cfg.min_history_events
        and w.wins / w.events >= cfg.min_confirmer_hit_rate
        and w.avg_return > 0
    )


# ----------------------------------------------------------------- cohort level

def cohort_score(wallet_scores: list[float], liquidity_usd: float,
                 min_liquidity: float = CONFIG.min_liquidity_usd) -> float:
    """Mean wallet score minus a liquidity penalty.

    Confirmations are intentionally NOT added here: they already enter each
    wallet's score (15% weight) and act as a hard gate in evaluate_cohort().
    """
    if not wallet_scores:
        return 0.0
    base = sum(wallet_scores) / len(wallet_scores)
    liquidity_penalty = 0 if liquidity_usd >= min_liquidity else 20
    return round(clamp(base - liquidity_penalty), 2)


def _key(w: WalletStats) -> str:
    # Unknown clustering is deliberately conservative: all unknown wallets on a chain
    # belong to one non-independent bucket. Unknown != independent.
    return f"{w.chain}:unknown" if not w.cluster_id else f"{w.chain}:{w.cluster_id}"


def evaluate_cohort(wallets: list[WalletStats], liquidity_usd: float,
                    cfg: Config = CONFIG) -> dict:
    """Server-side signal evaluation. Nothing here is trusted from the caller
    except raw wallet statistics and the measured liquidity."""
    # Independent confirmers = distinct clusters among eligible wallets.
    eligible_keys = {_key(w) for w in wallets if is_eligible_confirmer(w, cfg)}

    rows = []
    for w in wallets:
        others = len(eligible_keys - {_key(w)})
        # Client-supplied independent_confirmations is overwritten with the derived value.
        w_scored = w.model_copy(update={"independent_confirmations": others})
        score = score_wallet(w_scored, cfg)
        eligible = is_eligible_confirmer(w, cfg)
        rows.append({
            "wallet": w.wallet,
            "cluster": _key(w),
            "score": score,
            "status": wallet_status(w, cfg),
            "eligible_confirmer": eligible,
            "qualified": eligible and score >= cfg.min_wallet_score,
        })
    rows.sort(key=lambda r: r["score"], reverse=True)

    qualified = [r for r in rows if r["qualified"]]
    independent = len({r["cluster"] for r in qualified})
    cohort = cohort_score([r["score"] for r in qualified], liquidity_usd, cfg.min_liquidity_usd)

    acc = sum(w.accumulation_usd for w in wallets)
    dist = sum(w.distribution_usd for w in wallets)
    dist_share = dist / (acc + dist) if (acc + dist) > 0 else 0.0

    confidence = round(max(0.0, min(1.0, cohort / 100 * (1 - dist_share))), 4)

    reasons = []
    if independent < cfg.min_confirmations:
        reasons.append("insufficient_independent_confirmations")
    if dist_share > cfg.max_distribution_share:
        reasons.append("cohort_distributing")
    if liquidity_usd < cfg.min_liquidity_usd:
        reasons.append("low_liquidity")
    if cohort < cfg.strong_signal_score:
        reasons.append("cohort_score_below_threshold")
    if confidence < cfg.min_confidence:
        reasons.append("confidence_below_threshold")

    return {
        "wallets": rows,
        "cohort_score": cohort,
        "independent_confirmations": independent,
        "distribution_share": round(dist_share, 4),
        "confidence": confidence,
        "liquidity_usd": liquidity_usd,
        "signal_valid": not reasons,
        "reasons": reasons,
    }
