"""The live-test scripts (provider_probe.py, live_verify.py) run end-to-end against local mock JSON-RPC servers and a real
PostgreSQL, so that bugs are found here and not during the first real run. Chain data is a scripted fixture."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import TEST_DSN, drop_db, make_db, needs_pg
from fake_chain import FakeChain, addr, transfer_log, v2_swap_log
from test_chain_rpc import Server

ROOT = Path(__file__).resolve().parents[1]
pytestmark = needs_pg


def logs():
    return {n: [transfer_log(addr(9), addr(1), addr(2), n + 1), v2_swap_log(addr(5), addr(1), addr(2), 1, 0, 0, 2)] for n in range(0, 700, 3)}


def run(script, env, tmp):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, **env, "REPORTS_DIR": str(tmp), "LIVE_START_BACK": "300", "LIVE_BLOCKS": "120"})


def test_probe_selects_agreeing_providers_and_live_verify_passes(tmp_path):
    good_a, good_b, forked = FakeChain(700, salt="x", logs_at=logs()), FakeChain(700, salt="x", logs_at=logs()), FakeChain(700, salt="y", logs_at=logs())
    broken = FakeChain(700, salt="x"); broken.chain_id = 5                       # wrong network
    servers = [Server(c) for c in (good_a, good_b, forked, broken)]
    cfg = {"chains": {"ethereum": {"chain_id": 1, "providers": [
        {"name": n, "url": s.url} for n, s in zip(("a", "b", "forked", "wrongchain"), servers)]}}}
    (tmp_path / "p.json").write_text(json.dumps(cfg))
    name, dsn = make_db("live")
    try:
        env = {"PROVIDERS_FILE": str(tmp_path / "p.json"), "DATABASE_URL": dsn}
        r = run("provider_probe.py", env, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        sel = json.loads((tmp_path / "selection.json").read_text())["ethereum"]
        probe = {x["provider"]: x for x in json.loads((tmp_path / "probe.json").read_text())["results"]}
        assert probe["wrongchain"]["ok"] is False and "wrong chain id" in probe["wrongchain"]["errors"][0]
        assert sel["primary"] in ("a", "b") and sel["verifier"] in ("a", "b") and sel["primary"] != sel["verifier"]
        assert "forked" not in sel["ranked"] and "wrongchain" not in sel["ranked"]       # disagreeing / wrong network excluded
        assert probe["a"]["max_log_range_blocks"] == 2000 and probe["a"]["headers_linked"]
        assert "SECRET" not in (tmp_path / "probe.md").read_text()
        r = run("live_verify.py", env, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        rep = json.loads((tmp_path / "live_verify.json").read_text())["reports"][0]
        assert rep["passed"] and all(rep["checks"].values()), rep
        assert rep["log_counts"]["stored"] == rep["log_counts"]["independent"] > 0 and rep["noncanonical_blocks"] == 0
        assert rep["decoded_by_kind"]["erc20_transfer"] > 0 and rep["ingest_run2"]["next_block"] > rep["ingest_run1"]["next_block"] - 1
    finally:
        drop_db(name)
        for s in servers:
            s.close()


def test_live_verify_detects_a_verifier_that_disagrees(tmp_path):
    a, b = FakeChain(700, salt="x", logs_at=logs()), FakeChain(700, salt="x", logs_at=logs())
    sa, sb = Server(a), Server(b)
    cfg = {"chains": {"ethereum": {"chain_id": 1, "providers": [{"name": "a", "url": sa.url}, {"name": "b", "url": sb.url}]}}}
    (tmp_path / "p.json").write_text(json.dumps(cfg))
    (tmp_path / "selection.json").write_text(json.dumps({"ethereum": {"ranked": ["a", "b"], "primary": "a", "verifier": "b"}}))
    # the verifier silently drops one log: the cross-check must fail
    for n in range(400, 700):
        if b.blocks[n]["logs"]:
            b.blocks[n]["logs"] = b.blocks[n]["logs"][:1]
    name, dsn = make_db("live")
    try:
        r = run("live_verify.py", {"PROVIDERS_FILE": str(tmp_path / "p.json"), "DATABASE_URL": dsn}, tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        rep = json.loads((tmp_path / "live_verify.json").read_text())["reports"][0]
        assert rep["checks"]["logs_identical_to_independent_provider"] is False and rep["log_counts"]["only_stored"] > 0
    finally:
        drop_db(name); sa.close(); sb.close()


def test_provider_limited_to_one_block_per_query_still_works_and_agrees(tmp_path):
    narrow, wide = FakeChain(700, salt="x", logs_at=logs()), FakeChain(700, salt="x", logs_at=logs())
    narrow.max_range = 1                                          # like public gateways that allow one block per query
    sn, sw = Server(narrow), Server(wide)
    cfg = {"chains": {"ethereum": {"chain_id": 1, "providers": [{"name": "narrow", "url": sn.url}, {"name": "wide", "url": sw.url}]}}}
    (tmp_path / "p.json").write_text(json.dumps(cfg))
    name, dsn = make_db("live")
    try:
        env = {"PROVIDERS_FILE": str(tmp_path / "p.json"), "DATABASE_URL": dsn}
        assert run("provider_probe.py", env, tmp_path).returncode == 0
        sel = json.loads((tmp_path / "selection.json").read_text())["ethereum"]
        assert sel["primary"] == "wide" and sel["verifier"] == "narrow" and sel["ranges"]["narrow"] == 1
        r = run("live_verify.py", env, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads((tmp_path / "live_verify.json").read_text())["reports"][0]["passed"]
    finally:
        drop_db(name); sn.close(); sw.close()


# ---------------------------------------------------------------------------------------------- market_run.py
def _market_setup(tmp_path, feed_price=3025, with_feed=True, verifier_tamper=False, balances="true"):
    import fake_market as fm
    from app.chain import market
    w = fm.World(100, start=65).build(7)
    a, b = w.chain(), w.chain()
    for ch in (a, b):
        ch.contracts = {fm.ROUTER, fm.RELAYER}
        if balances != "none":
            ch.dyn = w.balance_dyn(ch, frozen=balances == "frozen")
        if with_feed:
            feed = market.CHAINS["ethereum"]["chainlink_eth_usd"]
            ch.evm[(feed, market.SEL["feed_decimals"])] = "0x" + format(8, "064x")
            ch.evm[(feed, market.SEL["latestRoundData"])] = "0x" + "".join(format(x, "064x") for x in (1, feed_price * 10 ** 8, 0, 0, 1))
    if verifier_tamper:
        real = b.receipt
        def receipt(h):
            r = real(h); r["from"] = fm.addr(0xdead); return r
        b.receipt = receipt
    sa, sb = Server(a), Server(b)
    cfg = {"chains": {"ethereum": {"chain_id": 1, "providers": [{"name": "a", "url": sa.url}, {"name": "b", "url": sb.url}]}}}
    (tmp_path / "p.json").write_text(json.dumps(cfg))
    (tmp_path / "selection.json").write_text(json.dumps({"ethereum": {"ranked": ["a", "b"], "primary": "a", "verifier": "b",
                                                                       "ranges": {"a": 2000, "b": 2000}}}))
    return w, (sa, sb)


def _run_market(tmp_path, dsn):
    return run("market_run.py", {"PROVIDERS_FILE": str(tmp_path / "p.json"), "DATABASE_URL": dsn, "MARKET_DISCOVERY_BLOCKS": "40",
                                 "MARKET_WATCH_BLOCKS": "60", "MARKET_TOP_K": "4", "MARKET_VERIFY_SAMPLE": "25"}, tmp_path)


def test_market_run_end_to_end_with_independent_checks(tmp_path):
    w, servers = _market_setup(tmp_path)
    name, dsn = make_db("mkt")
    try:
        r = _run_market(tmp_path, dsn)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        rep = json.loads((tmp_path / "market_run.json").read_text())
        assert rep["chainlink"]["status"] == "pass" and rep["second_provider"]["passed"] is True
        assert rep["state_check"]["status"] == "pass" and rep["state_check"]["checked"] >= 10 and rep["state_check"]["match_rate"] >= 0.9
        vc = rep["volume_coverage"]
        assert vc["priced_swaps_usd_total"] > 0 and abs(sum(c["share"] for c in vc["by_class"].values()) - 1) < 0.01
        assert vc["by_class"]["attributed_to_a_wallet"]["share"] > 0 and any(k.startswith("skipped:") for k in vc["by_class"])
        assert "fresh_tail" in rep["watch_ingest"]
        ub = rep["unattributed_beneficiaries"]
        assert ub["sampled"] > 0 and ub["code_lookup_errors"] == 0 and sum(ub["final_recipient_is"].values()) == ub["sampled"]
        assert rep["tx_targets"]["top_to_for_txs_with_a_trade"] and rep["tx_targets"]["unattributed_txs"] > 0
        assert rep["receipts"]["inconsistent_with_getlogs"] == 0 and rep["trades"]["confirmed"] > 0 and rep["trades"]["mismatch"] > 0
        assert rep["attribution"]["share_with_a_trade"] > 0.3 and rep["wallets"]["wallets_with_confirmed_trade"] > 0
        assert rep["cross_pool_prices"]["buckets_compared"] > 0 and rep["cross_pool_prices"]["max_deviation_pct"] < 1.0
        assert rep["discovery"]["rejected_unverified"] >= 1 and rep["integrity"]["steps_failed"] == []
        text = (tmp_path / "market_run.md").read_text() + (tmp_path / "market_run.json").read_text()
        assert "SECRET" not in text and "127.0.0.1" not in text                  # endpoint URLs / hosts never reach the report
    finally:
        drop_db(name)
        for s in servers:
            s.close()


def test_market_run_flags_chainlink_disagreement_and_tampered_second_provider(tmp_path):
    w, servers = _market_setup(tmp_path, feed_price=3600)
    name, dsn = make_db("mkt")
    try:
        r = _run_market(tmp_path, dsn)
        assert r.returncode == 1
        assert json.loads((tmp_path / "market_run.json").read_text())["chainlink"]["status"] == "fail"
    finally:
        drop_db(name)
        for s in servers:
            s.close()
    w, servers = _market_setup(tmp_path, verifier_tamper=True)
    name, dsn = make_db("mkt")
    try:
        r = _run_market(tmp_path, dsn)
        rep = json.loads((tmp_path / "market_run.json").read_text())
        assert r.returncode == 1 and rep["second_provider"]["passed"] is False and rep["second_provider"]["receipt_mismatches"]
    finally:
        drop_db(name)
        for s in servers:
            s.close()


def test_market_run_reports_unavailable_chainlink_honestly_not_as_pass(tmp_path):
    w, servers = _market_setup(tmp_path, with_feed=False)
    name, dsn = make_db("mkt")
    try:
        r = _run_market(tmp_path, dsn)
        rep = json.loads((tmp_path / "market_run.json").read_text())
        assert rep["chainlink"]["status"].startswith("unavailable") and rep["headline"]["chainlink check"].startswith("unavailable")
    finally:
        drop_db(name)
        for s in servers:
            s.close()


def test_market_run_flags_a_node_whose_state_contradicts_the_logs(tmp_path):
    w, servers = _market_setup(tmp_path, balances="frozen")
    name, dsn = make_db("mkt")
    try:
        r = _run_market(tmp_path, dsn)
        rep = json.loads((tmp_path / "market_run.json").read_text())
        assert r.returncode == 1 and rep["state_check"]["status"] == "fail" and rep["state_check"]["mismatches"]
        assert rep["integrity"]["state_check_failed"] is True
    finally:
        drop_db(name)
        for s in servers:
            s.close()


def test_equal_range_prefers_private_endpoint_and_wider_range_still_wins(tmp_path):
    pub, priv = FakeChain(700, salt="x", logs_at=logs()), FakeChain(700, salt="x", logs_at=logs())
    sp, sq = Server(pub), Server(priv)
    cfg = {"chains": {"ethereum": {"chain_id": 1, "providers": [{"name": "pub", "url": sp.url}]}}}
    (tmp_path / "p.json").write_text(json.dumps(cfg))
    try:
        r = run("provider_probe.py", {"PROVIDERS_FILE": str(tmp_path / "p.json"), "RPC_ETHEREUM_1": sq.url}, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        sel = json.loads((tmp_path / "selection.json").read_text())["ethereum"]
        assert sel["primary"] == "private-1" and sel["verifier"] == "pub", sel          # equal ranges: private first
        priv.max_range = 50                                                              # now the public one is wider
        r = run("provider_probe.py", {"PROVIDERS_FILE": str(tmp_path / "p.json"), "RPC_ETHEREUM_1": sq.url}, tmp_path)
        assert json.loads((tmp_path / "selection.json").read_text())["ethereum"]["primary"] == "pub"
    finally:
        sp.close(); sq.close()
