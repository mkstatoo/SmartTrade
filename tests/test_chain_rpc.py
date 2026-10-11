import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.chain.rpc import JsonRpcSource, RpcError, source_label
from tests.fake_chain import FakeChain, transfer_log, addr


class Server:
    """Local HTTP JSON-RPC server in front of a FakeChain; `script` lets a test inject faults per request number."""
    def __init__(self, chain, script=None):
        self.chain, self.script, self.n = chain, script or {}, 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                outer.n += 1
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                fault = outer.script.get(outer.n)
                if isinstance(fault, int):
                    self.send_response(fault); self.end_headers(); return
                if callable(fault):
                    raw = fault(body)
                else:
                    try:
                        res = {"jsonrpc": "2.0", "id": body["id"], "result": outer.chain.rpc(body["method"], body["params"])}
                    except RpcError as e:
                        res = {"jsonrpc": "2.0", "id": body["id"], "error": {"code": e.code, "message": str(e)}}
                    raw = json.dumps(res).encode()
                self.send_response(200); self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v2/SECRET-API-KEY"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


@pytest.fixture
def srv():
    made = []

    def mk(chain, script=None):
        s = Server(chain, script); made.append(s); return s
    yield mk
    for s in made:
        s.close()


def src(url, **kw):
    kw.setdefault("sleep", lambda s: None)
    return JsonRpcSource(url, **kw)


def test_label_hides_credentials():
    assert source_label("https://eth.example.com:8545/v2/SECRET") == "https://eth.example.com:8545"
    with pytest.raises(ValueError):
        source_label("file:///etc/passwd")
    s = src("https://user:pw@eth.example.com/v2/SECRET")
    assert "SECRET" not in s.source and "pw" not in s.source


def test_head_block_logs_roundtrip(srv):
    ch = FakeChain(10, logs_at={4: [transfer_log(addr(9), addr(1), addr(2), 5)]})
    s = srv(ch)
    r = src(s.url)
    assert r.head() == 9
    assert r.block(4) == {"number": 4, "hash": ch.blocks[4]["hash"], "parent": ch.blocks[3]["hash"], "ts": ch.blocks[4]["ts"]}
    got = r.logs(0, 9)
    assert len(got) == 1 and got[0]["block_number"] == 4 and got[0]["block_hash"] == ch.blocks[4]["hash"]


def test_retries_transient_http_errors_then_succeeds(srv):
    s = srv(FakeChain(5), {1: 429, 2: 503})
    assert src(s.url).head() == 4 and s.n == 3


def test_gives_up_after_retries(srv):
    s = srv(FakeChain(5), {i: 500 for i in range(1, 20)})
    with pytest.raises(RpcError):
        src(s.url, retries=2).head()
    assert s.n == 3


def test_non_retryable_http_status_fails_fast(srv):
    s = srv(FakeChain(5), {1: 401})
    with pytest.raises(RpcError):
        src(s.url).head()
    assert s.n == 1


def test_rpc_error_surfaces_with_code(srv):
    ch = FakeChain(5); ch.max_range = 1
    s = srv(ch)
    with pytest.raises(RpcError) as e:
        src(s.url).logs(0, 3)
    assert e.value.code == -32005


@pytest.mark.parametrize("bad", [
    lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"] + 1, "result": "0x1"}).encode(),      # id mismatch
    lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"]}).encode(),                          # no result
    lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"], "result": "10"}).encode(),          # not hex
    lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"], "result": "0xzz"}).encode(),
    lambda b: json.dumps([1, 2]).encode(),
])
def test_malformed_head_responses_rejected(srv, bad):
    s = srv(FakeChain(5), {1: bad})
    with pytest.raises(RpcError):
        src(s.url, retries=0).head()


def test_garbage_body_is_transport_error_and_retried(srv):
    s = srv(FakeChain(5), {1: lambda b: b"not json"})
    assert src(s.url).head() == 4


def test_block_number_mismatch_rejected(srv):
    ch = FakeChain(10)
    s = srv(ch, {1: lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"], "result": ch.rpc("eth_getBlockByNumber", ["0x5", False])}).encode()})
    with pytest.raises(RpcError, match="different block"):
        src(s.url).block(3)


def test_missing_block_and_malformed_log_rejected(srv):
    ch = FakeChain(5)
    s = srv(ch)
    with pytest.raises(RpcError):
        src(s.url).block(99)
    ok = ch.rpc("eth_getLogs", [{"fromBlock": "0x0", "toBlock": "0x4"}])
    assert ok == []
    bad_log = {"blockNumber": "0x1", "blockHash": "0x12", "transactionHash": "0x" + "ab" * 32, "logIndex": "0x0",
               "address": addr(1), "topics": ["0x" + "cd" * 32], "data": "0x"}
    s2 = srv(ch, {1: lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"], "result": [bad_log]}).encode()})
    with pytest.raises(RpcError, match="malformed log"):
        src(s2.url, retries=0).logs(0, 4)


def test_removed_logs_are_skipped(srv):
    good = {"blockNumber": "0x1", "blockHash": "0x" + "11" * 32, "transactionHash": "0x" + "ab" * 32, "logIndex": "0x0",
            "address": addr(1), "topics": ["0x" + "cd" * 32], "data": "0x", "removed": True}
    s = srv(FakeChain(5), {1: lambda b: json.dumps({"jsonrpc": "2.0", "id": b["id"], "result": [good]}).encode()})
    assert src(s.url).logs(0, 4) == []


def test_oversized_response_rejected(srv, monkeypatch):
    import app.chain.rpc as rpc
    monkeypatch.setattr(rpc, "MAX_RESPONSE_BYTES", 50)
    s = srv(FakeChain(5))
    with pytest.raises(RpcError):
        src(s.url, retries=0).block(1)


def test_unreachable_endpoint_error_message_has_no_url():
    r = src("http://127.0.0.1:1/KEY123", retries=1)
    with pytest.raises(RpcError) as e:
        r.head()
    assert "KEY123" not in str(e.value)


def test_sends_an_identifying_user_agent_and_error_body_snippet(srv):
    seen = {}
    ch = FakeChain(5)
    s = srv(ch)
    orig = s.httpd.RequestHandlerClass.do_POST

    def spy(self):
        seen["ua"] = self.headers.get("user-agent")
        return orig(self)
    s.httpd.RequestHandlerClass.do_POST = spy
    src(s.url).head()
    assert seen["ua"].startswith("smart-copy-trading-research/")            # default Python agent is rejected (403) by many gateways
    s2 = srv(ch, {1: 403})
    with pytest.raises(RpcError, match="HTTP 403"):
        src(s2.url, retries=0).head()
