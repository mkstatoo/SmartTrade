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
