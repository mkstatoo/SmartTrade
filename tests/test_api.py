import pytest

from conftest import H, T0, MIN, bar, good_wallets, signal


def test_config_single_source_of_truth(client):
    c = client.get("/config").json()
    assert c["min_confirmations"] == 2 and c["live_execution"] is False and "api_key" not in str(c).lower()


def test_score_requires_liquidity_and_signal_ts(client):
    assert client.post("/score", json={"token": "Q", "wallets": []}).status_code == 422


def test_score_uses_supplied_liquidity(client):
    bar(client, "0xq", T0, 1, 1, 1, 1)
    def sc(liq):
        return client.post("/score", json={"token": "0xq", "chain": "base", "wallets": good_wallets(T0 + MIN),
                                           "liquidity_usd": liq, "signal_ts": T0 + MIN}).json()
    hi, lo = sc(10_000_000), sc(100_000)
    assert hi["signal_valid"] and not lo["signal_valid"] and "low_liquidity" in lo["reasons"]


def test_signal_rejects_client_supplied_score(client):
    body = {"token": "0xq", "chain": "base", "wallets": [], "liquidity_usd": 1e7, "signal_ts": T0, "score": 99}
    assert client.post("/paper/signal", headers=H, json=body).status_code == 422


def test_asof_rules_are_enforced_server_side(client):
    bar(client, "0xq", T0, 1, 1, 1, 1)
    ts = T0 + MIN
    def post(ws, sts=ts):
        return client.post("/score", json={"token": "0xq", "chain": "base", "wallets": ws,
                                           "liquidity_usd": 1e7, "signal_ts": sts})
    assert post(good_wallets(ts)).status_code == 200
    assert post(good_wallets(ts + 1)).status_code == 422                    # stats newer than signal
    assert post([{**good_wallets(ts)[0]}] and [dict(good_wallets(ts)[0], as_of_ts=0)]).status_code == 422
    assert post(good_wallets(ts), sts=ts + 10_000).status_code == 422       # far future
    assert post(good_wallets(ts - 90_000)).status_code == 422               # stale stats


def test_invalid_cohort_waits_and_is_audited(client):
    bar(client, "0xq", T0, 1, 1, 1, 1)
    ws = good_wallets(T0 + MIN)
    for w in ws:
        w["cluster_id"] = "same"
    r = client.post("/paper/signal", headers=H, json={"token": "0xq", "chain": "base", "wallets": ws,
                    "liquidity_usd": 1e7, "signal_ts": T0 + MIN}).json()
    assert r["action"] == "WAIT" and "insufficient_independent_confirmations" in r["reasons"]


def test_wallet_chain_mismatch_rejected(client):
    bar(client, "0xq", T0, 1, 1, 1, 1)
    r = client.post("/paper/signal", headers=H, json={"token": "0xq", "chain": "ethereum",
                    "wallets": good_wallets(T0 + MIN, "base"), "liquidity_usd": 1e7, "signal_ts": T0 + MIN})
    assert r.status_code == 422
