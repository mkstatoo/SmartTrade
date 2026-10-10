"""Read-path protection, request limits, auth throttle and configuration control."""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.config import CONFIG, Config, ConfigError, config_from_env
from app.main import create_app
from app.models import BacktestRequest
from app.security import AuthThrottle
from app.store import MemoryStore
from conftest import H, KEY, MIN, T0, bar, good_wallets

ROOT = Path(__file__).resolve().parents[1]
NOKEY = {"X-Research-Key": ""}


def mk(**kw):
    return TestClient(create_app(MemoryStore(), ReplayClock(), **kw), headers=H)


@pytest.fixture
def c():
    with mk() as c:
        yield c


# ------------------------------------------------------------------ every route except /health needs the key
def test_every_route_except_health_requires_the_key(c):
    routes = [r for r in c.app.routes if isinstance(r, APIRoute)]
    assert {r.path for r in routes} >= {"/health", "/status", "/config", "/score", "/backtest", "/paper", "/paper/mark",
                                        "/paper/replay/bar", "/paper/signal", "/paper/exit/{chain}/{token}", "/paper/sweep"}
    for r in routes:
        for method in r.methods - {"HEAD", "OPTIONS"}:
            url = r.path.replace("{chain}", "base").replace("{token}", "0xa")
            with mk() as fresh:          # fresh app per probe: the brute-force throttle (tested separately) must not mask 401
                resp = fresh.request(method, url, headers=NOKEY, content=b"{}")
            if r.path == "/health":
                assert resp.status_code == 200
            else:
                assert resp.status_code == 401, (method, r.path, resp.status_code)
                assert resp.json() == {"detail": "invalid research API key"}


def test_wrong_key_rejected_everywhere_it_matters(c):
    for url in ("/paper", "/config", "/status"):
        assert c.get(url, headers={"X-Research-Key": "x" * len(KEY)}).status_code == 401


def test_no_key_configured_disables_api_but_not_health(c, monkeypatch):
    monkeypatch.setenv("PAPER_API_KEY", "")
    assert c.get("/paper").status_code == 503
    assert c.get("/health").status_code == 200


def test_public_schema_and_docs_are_not_served(c):
    for u in ("/openapi.json", "/docs", "/redoc"):
        assert c.get(u, headers=NOKEY).status_code in (401, 404)


def test_health_exposes_nothing_internal(c):
    assert set(c.get("/health", headers=NOKEY).json()) == {"status", "mode", "live_execution"}


# ------------------------------------------------------------------ throttle
def test_failed_auth_throttle_and_recovery():
    t = [1000.0]
    thr = AuthThrottle(limit=3, window_sec=60, now=lambda: t[0])
    with mk() as c:
        c.app.state.throttle = thr
        for _ in range(3):
            assert c.get("/paper", headers={"X-Research-Key": "bad"}).status_code == 401
        r = c.get("/paper", headers={"X-Research-Key": "bad"})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert c.get("/paper").status_code == 429                      # even the right key is refused while locked
        t[0] += 61
        assert c.get("/paper").status_code == 200
        assert c.get("/paper", headers={"X-Research-Key": "bad"}).status_code == 401   # counter restarted


def test_success_resets_failure_counter():
    thr = AuthThrottle(limit=3, window_sec=60, now=lambda: 0.0)
    with mk() as c:
        c.app.state.throttle = thr
        for _ in range(2):
            c.get("/paper", headers={"X-Research-Key": "bad"})
        assert c.get("/paper").status_code == 200
        for _ in range(2):
            assert c.get("/paper", headers={"X-Research-Key": "bad"}).status_code == 401


# ------------------------------------------------------------------ size limits
def test_body_limit_content_length_and_chunked():
    with mk(max_body_bytes=2048) as c:
        big = json.dumps({"events": [], "prices": [], "pad": "x" * 5000})
        assert c.post("/backtest", content=big).status_code == 413
        def gen():
            for _ in range(10):
                yield b" " * 1000
        assert c.post("/backtest", content=gen()).status_code == 413
        small = json.dumps({"events": [], "prices": []})
        assert c.post("/backtest", content=small, headers={**H, "Content-Type": "application/json"}).status_code == 200


def test_list_caps_declared():
    assert BacktestRequest.model_fields["events"].metadata[0].max_length == 100_000
    assert BacktestRequest.model_fields["prices"].metadata[0].max_length == 200_000


def test_too_many_wallets_422(c):
    bar(c, "0xa", T0, 1, 1, 1, 1)
    ws = good_wallets(T0 + MIN) * 101
    r = c.post("/score", json={"token": "0xa", "chain": "base", "wallets": ws, "liquidity_usd": 1e7, "signal_ts": T0 + MIN})
    assert r.status_code == 422


# ------------------------------------------------------------------ configuration control
def test_env_overrides_are_whitelisted_parsed_and_validated():
    cfg, used = config_from_env({"PAPER_SLIPPAGE_BPS": "25", "PAPER_MAX_HOLD_SEC": "7200", "LIVE_EXECUTION": "1",
                                 "PAPER_API_KEY": "secret", "SOMETHING_ELSE": "1"})
    assert cfg.paper_slippage_bps == 25 and cfg.paper_max_hold_sec == 7200 and cfg.live_execution is False
    assert sorted(used) == ["PAPER_MAX_HOLD_SEC", "PAPER_SLIPPAGE_BPS"]


@pytest.mark.parametrize("env", [
    {"PAPER_SLIPPAGE_BPS": "nan"}, {"PAPER_SLIPPAGE_BPS": "inf"}, {"PAPER_SLIPPAGE_BPS": "10000"},
    {"PAPER_SLIPPAGE_BPS": "-1"}, {"PAPER_FEE_BPS": "abc"}, {"PAPER_GAS_USD": "-5"}, {"PAPER_INITIAL_CASH_USD": "0"},
    {"PAPER_MAX_HOLD_SEC": "0"}, {"PAPER_MAX_HOLD_SEC": "1.5"}, {"PAPER_CLOCK": "sometimes"},
    {"PAPER_PORTFOLIO_ID": "bad id; drop table"}, {"PAPER_SWEEP_INTERVAL_SEC": "-1"}, {"MAX_BODY_BYTES": "10"},
    {"DB_LOCK_TIMEOUT_MS": "1"}, {"AUTH_FAIL_LIMIT": "0"},
])
def test_invalid_env_values_refuse_to_start(env):
    with pytest.raises(ConfigError):
        config_from_env(env)


def test_live_execution_cannot_be_enabled():
    with pytest.raises(ConfigError):
        replace(Config(), live_execution=True).validate()


def test_bad_env_makes_the_process_exit_with_a_clear_message():
    r = subprocess.run([sys.executable, "-c", "import app.config"], cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PAPER_SLIPPAGE_BPS": "nan"})
    assert r.returncode != 0 and "PAPER_SLIPPAGE_BPS" in r.stderr


def test_config_endpoint_has_hash_overrides_and_no_secrets(c):
    body = c.get("/config").json()
    assert body["config_sha256"] == CONFIG.sha256() and body["live_execution"] is False
    assert "env_overrides" in body
    assert KEY not in json.dumps(body) and "api_key" not in json.dumps(body).lower()
    assert replace(CONFIG, paper_fee_bps=CONFIG.paper_fee_bps + 1).sha256() != CONFIG.sha256()


def test_assumption_drift_is_reported_not_hidden():
    other = replace(CONFIG, paper_slippage_bps=CONFIG.paper_slippage_bps + 7)
    with TestClient(create_app(MemoryStore(other), ReplayClock()), headers=H) as c:
        drift = c.get("/paper").json()["assumption_drift"]
    assert drift == {"slippage_bps": {"stored": CONFIG.paper_slippage_bps + 7, "configured": CONFIG.paper_slippage_bps}}
    with mk() as c:
        assert c.get("/paper").json()["assumption_drift"] == {}
