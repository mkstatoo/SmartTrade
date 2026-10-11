"""Minimal, defensive JSON-RPC client for EVM nodes (eth_blockNumber, eth_getBlockByNumber, eth_getLogs).

Never stores or logs the endpoint URL (it usually contains an API key): only scheme://host is used as the source label.
Every value coming back is format-checked before it can reach the database."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

HEX32 = re.compile(r"^0x[0-9a-fA-F]{64}$")
HEX20 = re.compile(r"^0x[0-9a-fA-F]{40}$")
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
USER_AGENT = "smart-copy-trading-research/0.4.4 (+https://github.com/mkstatoo/SmartTrade)"   # many gateways reject the default Python agent with 403


def _snippet(raw) -> str:
    """First characters of an error body for diagnosis (a gateway message, never the request URL)."""
    try:
        t = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    except Exception:  # noqa: BLE001
        return ""
    return " ".join(t.split())[:100]


class RpcError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def source_label(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("RPC URL must be http(s)://host...")
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


def _hex_int(x, what) -> int:
    if not isinstance(x, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", x):
        raise RpcError(f"malformed quantity for {what}")
    return int(x, 16)


class JsonRpcSource:
    def __init__(self, url: str, timeout: float = 20.0, retries: int = 4, backoff: float = 0.5, sleep=time.sleep):
        self._url, self.timeout, self.retries, self.backoff, self._sleep = url, timeout, retries, backoff, sleep
        self.source = source_label(url)
        self._id = 0

    # ---------------------------------------------------------------- transport
    def _call(self, method: str, params: list):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        last = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self._url, data=body, headers={"content-type": "application/json", "user-agent": USER_AGENT, "accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise RpcError("response too large")
                msg = json.loads(raw)
            except urllib.error.HTTPError as exc:
                try:
                    detail = _snippet(exc.read(300))
                except Exception:  # noqa: BLE001
                    detail = ""
                last = RpcError(f"HTTP {exc.code}" + (f": {detail}" if detail else ""))
                if exc.code not in (429, 500, 502, 503, 504):
                    raise last from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as exc:
                last = RpcError(f"transport error: {type(exc).__name__}")
            else:
                if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or msg.get("id") != self._id:
                    raise RpcError("malformed or mismatched JSON-RPC response: " + _snippet(raw))
                if "error" in msg:
                    e = msg["error"] if isinstance(msg["error"], dict) else {}
                    raise RpcError(str(e.get("message", "rpc error"))[:200], e.get("code"))
                if "result" not in msg:
                    raise RpcError("response without result")
                return msg["result"]
            if attempt < self.retries:
                self._sleep(self.backoff * (2 ** attempt))
        raise last

    # ---------------------------------------------------------------- chain interface used by ingest
    def head(self) -> int:
        return _hex_int(self._call("eth_blockNumber", []), "blockNumber")

    def block(self, number: int) -> dict:
        r = self._call("eth_getBlockByNumber", [hex(number), False])
        if r is None:
            raise RpcError(f"block {number} not available")
        if not (isinstance(r, dict) and HEX32.match(str(r.get("hash"))) and HEX32.match(str(r.get("parentHash")))):
            raise RpcError("malformed block")
        n = _hex_int(r.get("number"), "number")
        if n != number:
            raise RpcError("node returned a different block than requested")
        return {"number": n, "hash": r["hash"].lower(), "parent": r["parentHash"].lower(), "ts": _hex_int(r.get("timestamp"), "timestamp")}

    def logs(self, from_block: int, to_block: int, topics0=None, addresses=None) -> list:
        flt = {"fromBlock": hex(from_block), "toBlock": hex(to_block)}
        if topics0:
            flt["topics"] = [list(topics0)]
        if addresses:
            flt["address"] = list(addresses)
        raw = self._call("eth_getLogs", [flt])
        if not isinstance(raw, list):
            raise RpcError("eth_getLogs did not return a list")
        out = []
        for l in raw:
            try:
                if l.get("removed"):
                    continue                                             # nodes flag logs of orphaned blocks
                topics = [t.lower() for t in l["topics"]]
                if not (HEX32.match(l["blockHash"]) and HEX32.match(l["transactionHash"]) and HEX20.match(l["address"])
                        and all(HEX32.match(t) for t in topics) and re.fullmatch(r"0x([0-9a-fA-F]{2})*", l["data"])):
                    raise ValueError
                out.append({"block_number": _hex_int(l["blockNumber"], "blockNumber"), "block_hash": l["blockHash"].lower(),
                            "tx_hash": l["transactionHash"].lower(), "log_index": _hex_int(l["logIndex"], "logIndex"),
                            "address": l["address"].lower(), "topics": topics, "data": l["data"].lower()})
            except (KeyError, ValueError, AttributeError, TypeError, RpcError):
                raise RpcError("malformed log entry") from None
        return out
