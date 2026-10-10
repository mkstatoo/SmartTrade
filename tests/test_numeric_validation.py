"""NaN / +-Infinity / out-of-range numbers must be refused with a standard 422 on EVERY endpoint that takes numbers
(they used to produce HTTP 500), and must never change state."""
import copy
import json

import pytest

from fastapi.testclient import TestClient

from app.clock import ReplayClock
from app.main import create_app
from app.store import MemoryStore
from conftest import H, T0, MIN, good_wallets


@pytest.fixture
def client():
    with TestClient(create_app(MemoryStore(), ReplayClock()), headers=H) as c:
        yield c


SENT = "@@V@@"
BAD_LITERALS = ["NaN", "Infinity", "-Infinity", '"nan"', '"inf"', '"-inf"']


def bar_body():
    return {"chain": "base", "token": "0xa", "ts": T0, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume_usd": 10.0}


def signal_body():
    return {"token": "0xa", "chain": "base", "wallets": good_wallets(T0 + MIN), "liquidity_usd": 1e7,
            "signal_ts": T0 + MIN, "allocation_pct": 0.05, "target_return_pct": 5.0, "stop_loss_pct": 2.0}


def backtest_body():
    ev = {"wallet": "0xw", "token": "0xa", "chain": "base", "ts": T0, "side": "BUY", "usd_value": 100.0, "price": 1.0}
    pb = {"chain": "base", "token": "0xa", "ts": T0, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume_usd": 10.0}
    return {"events": [ev], "prices": [pb], "horizon_hours": 24, "target_return_pct": 5, "stop_loss_pct": 2,
            "slippage_bps": 30, "fee_bps": 30, "gas_usd": 2, "notional_usd": 1000}


WALLET_FIELDS = ["avg_return", "token_avg_return", "accumulation_usd", "distribution_usd", "pump_distance_pct",
                 "cex_outflow_share", "volume_anomaly"]
CASES = (
    [("/paper/replay/bar", bar_body, [k]) for k in ("open", "high", "low", "close", "volume_usd")]
    + [("/paper/signal", signal_body, [k]) for k in ("liquidity_usd", "allocation_pct", "target_return_pct", "stop_loss_pct")]
    + [("/paper/signal", signal_body, ["wallets", 0, k]) for k in WALLET_FIELDS]
    + [("/score", signal_body, [k]) for k in ("liquidity_usd",)]
    + [("/score", signal_body, ["wallets", 0, k]) for k in WALLET_FIELDS]
    + [("/backtest", backtest_body, [k]) for k in ("horizon_hours", "target_return_pct", "stop_loss_pct", "slippage_bps",
                                                  "fee_bps", "gas_usd", "notional_usd")]
    + [("/backtest", backtest_body, ["events", 0, k]) for k in ("usd_value", "price")]
    + [("/backtest", backtest_body, ["prices", 0, k]) for k in ("open", "high", "low", "close", "volume_usd")]
)


def put(body, path, value):
    body = copy.deepcopy(body)
    cur = body
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value
    return body


def post(client, url, body_str):
    return client.post(url, headers={**H, "Content-Type": "application/json"}, content=body_str)


@pytest.mark.parametrize("literal", BAD_LITERALS)
@pytest.mark.parametrize("url,make,path", CASES, ids=lambda x: x if isinstance(x, str) else None)
def test_non_finite_numbers_are_422_not_500(client, url, make, path, literal):
    raw = json.dumps(put(make(), path, SENT)).replace(f'"{SENT}"', literal)
    r = post(client, url, raw)
    assert r.status_code == 422, (url, path, literal, r.status_code, r.text[:200])
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail and set(detail[0]) == {"loc", "msg", "type"}
    assert any(e["type"] == "finite_number" for e in detail)
    assert literal.strip('"') not in r.text.replace("finite", "")        # the offending input is not echoed back


def test_bad_bar_does_not_touch_state(client):
    raw = json.dumps(put(bar_body(), ["close"], SENT)).replace(f'"{SENT}"', "Infinity")
    assert post(client, "/paper/replay/bar", raw).status_code == 422
    p = client.get("/paper").json()
    assert p["price_book"] == {} and p["portfolio"]["data_clock_ts"] == 0


@pytest.mark.parametrize("url,make,path,value", [
    ("/paper/replay/bar", bar_body, ["ts"], 10 ** 30),
    ("/paper/replay/bar", bar_body, ["close"], 1e13),
    ("/paper/replay/bar", bar_body, ["volume_usd"], 1e16),
    ("/paper/signal", signal_body, ["signal_ts"], 10 ** 30),
    ("/paper/signal", signal_body, ["stop_loss_pct"], 100),
    ("/paper/signal", signal_body, ["stop_loss_pct"], 150),
    ("/paper/signal", signal_body, ["max_hold_sec"], 0),
    ("/paper/signal", signal_body, ["max_hold_sec"], 10 ** 12),
    ("/paper/signal", signal_body, ["wallets", 0, "as_of_ts"], 10 ** 30),
    ("/backtest", backtest_body, ["slippage_bps"], 10_000),
    ("/backtest", backtest_body, ["stop_loss_pct"], 100),
    ("/backtest", backtest_body, ["events", 0, "log_index"], 2 ** 63),
    ("/backtest", backtest_body, ["events", 0, "ts"], 10 ** 30),
])
def test_out_of_range_values_are_422(client, url, make, path, value):
    r = post(client, url, json.dumps(put(make(), path, value)))
    assert r.status_code == 422, (path, value, r.status_code, r.text[:200])
    assert isinstance(r.json()["detail"], list)


def test_valid_bodies_still_pass(client):
    assert post(client, "/paper/replay/bar", json.dumps(bar_body())).status_code == 200
    assert post(client, "/backtest", json.dumps(backtest_body())).status_code == 200


def test_malformed_json_is_422(client):
    r = post(client, "/paper/replay/bar", "{not json")
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)
