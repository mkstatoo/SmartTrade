"""ENGINE-TEST FIXTURE: a scripted in-memory EVM chain (blocks, logs, reorgs). It is not market or chain data; it exists to
exercise ingestion rules deterministically. Encoders here are written independently of app/chain/abi.py (they build
logs from integers, the decoder parses them back)."""
import hashlib

from app.chain.rpc import RpcError

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
V2 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
V3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


def addr(n: int) -> str:
    return "0x" + format(n, "040x")


def topic_addr(a: str) -> str:
    return "0x" + "0" * 24 + a[2:]


def word(v: int) -> str:
    return format(v % (1 << 256), "064x")          # two's complement for negatives = sign extension


def transfer_log(token, frm, to, amount):
    return {"address": token, "topics": [TRANSFER, topic_addr(frm), topic_addr(to)], "data": "0x" + word(amount)}


def v2_swap_log(pool, sender, to, a0in, a1in, a0out, a1out):
    return {"address": pool, "topics": [V2, topic_addr(sender), topic_addr(to)],
            "data": "0x" + "".join(word(x) for x in (a0in, a1in, a0out, a1out))}


def v3_swap_log(pool, sender, recipient, a0, a1, sqrt, liq, tick):
    return {"address": pool, "topics": [V3, topic_addr(sender), topic_addr(recipient)],
            "data": "0x" + "".join(word(x) for x in (a0, a1, sqrt, liq, tick))}


def _h(*parts) -> str:
    return "0x" + hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


class FakeChain:
    source = "fake://node"

    def __init__(self, length=30, salt="a", logs_at=None, t0=1_700_000_000):
        self.blocks = {}                 # number -> dict(hash,parent,ts,logs)
        self.t0, self.calls, self.hook = t0, [], None
        self.max_range = None
        self.evm = {}                    # (to, data) -> eth_call result; absent = revert
        self.tx_meta = {}                # tx_hash -> {from, status, gas_used, egp}
        parent = "0x" + "00" * 32
        for n in range(length):
            parent = self._mk(n, parent, salt, (logs_at or {}).get(n, []))
        self.tip = length - 1

    def _mk(self, n, parent, salt, logs):
        h = _h(salt, n, parent)
        self.blocks[n] = {"hash": h, "parent": parent, "ts": self.t0 + 12 * n, "logs": list(logs)}
        return h

    def extend(self, count, salt="a", logs_at=None):
        for _ in range(count):
            n = self.tip + 1
            self._mk(n, self.blocks[self.tip]["hash"], salt, (logs_at or {}).get(n, []))
            self.tip = n

    def reorg(self, fork_block, new_len, salt="b", logs_at=None):
        """Replace everything above fork_block by new_len fresh blocks."""
        for n in [k for k in self.blocks if k > fork_block]:
            del self.blocks[n]
        parent = self.blocks[fork_block]["hash"]
        for i in range(new_len):
            n = fork_block + 1 + i
            parent = self._mk(n, parent, salt, (logs_at or {}).get(n, []))
        self.tip = fork_block + new_len

    # ---- source interface
    def _tick(self, name, *args):
        self.calls.append((name, args))
        if self.hook:
            self.hook(self, name, args)

    def head(self):
        self._tick("head")
        return self.tip

    def block(self, n):
        self._tick("block", n)
        if n not in self.blocks:
            raise RpcError(f"block {n} not available")
        b = self.blocks[n]
        return {"number": n, "hash": b["hash"], "parent": b["parent"], "ts": b["ts"]}

    def logs(self, lo, hi, topics0=None, addresses=None):
        self._tick("logs", lo, hi)
        if self.max_range is not None and hi - lo + 1 > self.max_range:
            raise RpcError("query returned more than 10000 results / range too large", -32005)
        out = []
        for n in range(lo, hi + 1):
            b = self.blocks.get(n)
            if not b:
                continue
            for i, l in enumerate(b["logs"]):
                if topics0 and l["topics"][0] not in topics0:
                    continue
                if addresses and l["address"] not in addresses:
                    continue
                out.append({"block_number": n, "block_hash": b["hash"], "tx_hash": l.get("tx") or _h("tx", n, i // 2),
                            "log_index": i, "address": l["address"], "topics": list(l["topics"]), "data": l["data"]})
        return out

    def call(self, to, data, block=None):
        self._tick("call", to, data)
        if (to, data) not in self.evm:
            raise RpcError("execution reverted", 3)
        return self.evm[(to, data)]

    def receipt(self, tx_hash):
        self._tick("receipt", tx_hash)
        meta = self.tx_meta.get(tx_hash)
        if meta is None:
            raise RpcError("receipt not available")
        for n, b in self.blocks.items():
            logs = [{"block_number": n, "block_hash": b["hash"], "tx_hash": tx_hash, "log_index": i, "address": l["address"],
                     "topics": list(l["topics"]), "data": l["data"]} for i, l in enumerate(b["logs"]) if l.get("tx") == tx_hash]
            if logs:
                return {"tx_hash": tx_hash, "block_number": n, "block_hash": b["hash"], "from": meta["from"], "status": meta["status"],
                        "gas_used": meta["gas_used"], "effective_gas_price": meta["egp"], "logs": logs}
        raise RpcError("receipt not available")

    # ---- raw JSON-RPC view (for the HTTP mock)
    chain_id = 1

    def rpc(self, method, params):
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_blockNumber":
            return hex(self.tip)
        if method == "eth_getBlockByNumber":
            n = int(params[0], 16)
            b = self.blocks.get(n)
            return None if b is None else {"number": hex(n), "hash": b["hash"], "parentHash": b["parent"], "timestamp": hex(b["ts"])}
        if method == "eth_getLogs":
            f = params[0]
            lo, hi = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            t0 = f.get("topics", [None])[0]
            res = self.logs(lo, hi, t0, f.get("address"))
            return [{"blockNumber": hex(l["block_number"]), "blockHash": l["block_hash"], "transactionHash": l["tx_hash"],
                     "logIndex": hex(l["log_index"]), "address": l["address"], "topics": l["topics"], "data": l["data"],
                     "removed": False} for l in res]
        if method == "eth_call":
            return self.call(params[0]["to"], params[0]["data"])
        if method == "eth_getTransactionReceipt":
            try:
                r = self.receipt(params[0])
            except RpcError:
                return None
            return {"transactionHash": r["tx_hash"], "blockNumber": hex(r["block_number"]), "blockHash": r["block_hash"], "from": r["from"],
                    "status": hex(r["status"]), "gasUsed": hex(r["gas_used"]), "effectiveGasPrice": hex(r["effective_gas_price"]),
                    "logs": [{"blockNumber": hex(l["block_number"]), "blockHash": l["block_hash"], "transactionHash": l["tx_hash"],
                              "logIndex": hex(l["log_index"]), "address": l["address"], "topics": l["topics"], "data": l["data"],
                              "removed": False} for l in r["logs"]]}
        raise RpcError("method not found", -32601)
