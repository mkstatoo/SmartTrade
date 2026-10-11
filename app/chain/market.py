"""On-chain market knowledge for wallet attribution: verified DEX pools, token metadata, swap normalisation and USD valuation.

Nothing here trusts a hard-coded address blindly: pools are accepted only if the DEX FACTORY itself says "this is the pool
for (token0, token1, fee)", and the well-known token / oracle addresses are re-checked on-chain (symbol, decimals) at run time.
USD valuation uses execution prices from the swaps themselves (stable coins = 1 USD, WETH priced from WETH/stable pool swaps);
an external oracle (Chainlink) is used only as an independent cross-check, never as input."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, getcontext

from app.chain.rpc import RpcError

getcontext().prec = 50

SEL = {"factory": "0xc45a0155", "token0": "0x0dfe1681", "token1": "0xd21220a7", "fee": "0xddca3f43",
       "getPool": "0x1698ee82", "getPair": "0xe6a43905", "decimals": "0x313ce567", "symbol": "0x95d89b41",
       "latestRoundData": "0xfeaf968c", "feed_decimals": "0x313ce567", "balanceOf": "0x70a08231"}

CHAINS = {
    "ethereum": {
        "chain_id": 1,
        "v3_factory": "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        "v2_factory": "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
        "weth": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "stables": {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC", "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
                    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI"},
        "expected": {"0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("WETH", 18), "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
                     "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6), "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18)},
        "chainlink_eth_usd": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
    },
}
HEX20 = re.compile(r"^0x[0-9a-f]{40}$")


class MarketError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ eth_call codecs
def _word(x) -> str:
    return format(x, "064x") if isinstance(x, int) else x[2:].rjust(64, "0")


def calldata(sel: str, *args) -> str:
    return sel + "".join(_word(a) for a in args)


def dec_address(res: str) -> str:
    h = res[2:]
    if len(h) != 64 or h[:24] != "0" * 24:
        raise MarketError("not an address word")
    return "0x" + h[24:]


def dec_uint(res: str, index: int = 0) -> int:
    h = res[2:]
    if len(h) < 64 * (index + 1):
        raise MarketError("result too short")
    return int(h[64 * index:64 * (index + 1)], 16)


def dec_int(res: str, index: int = 0, bits: int = 256) -> int:
    v = dec_uint(res, index)
    return v - (1 << 256) if v >= 1 << 255 else v


def dec_string(res: str) -> str:
    """ERC-20 symbol(): ABI string, or the legacy bytes32 form (MKR, SAI). Output is sanitised: printable ASCII only, <= 32 chars."""
    h = res[2:]
    try:
        if len(h) == 64:
            raw = bytes.fromhex(h).rstrip(b"\x00")
        else:
            off = int(h[:64], 16) * 2
            n = int(h[off:off + 64], 16)
            if n > 256:
                raise MarketError("symbol too long")
            raw = bytes.fromhex(h[off + 64:off + 64 + 2 * n])
        s = raw.decode("ascii", "replace")
    except (ValueError, MarketError) as exc:
        raise MarketError("undecodable string") from exc
    return re.sub(r"[^A-Za-z0-9._+\-$ ]", "?", s)[:32]


def _try(rpc, to, data, block=None):
    try:
        return rpc.call(to, data, block)
    except RpcError as exc:
        if exc.code is not None or "revert" in str(exc).lower():                 # JSON-RPC level error = call failed
            return None
        raise


@dataclass(frozen=True)
class Pool:
    pool: str
    kind: str                      # 'uniswap_v2' | 'uniswap_v3'
    factory: str
    token0: str
    token1: str
    fee: int | None


def token_meta(rpc, token: str, block=None) -> dict:
    sym, dec = _try(rpc, token, SEL["symbol"], block), _try(rpc, token, SEL["decimals"], block)
    if sym is None or dec is None:
        raise MarketError(f"{token} does not look like an ERC-20")
    d = dec_uint(dec)
    if not 0 <= d <= 36:
        raise MarketError("implausible decimals")
    return {"address": token, "symbol": dec_string(sym), "decimals": d}


def verify_pool(rpc, cfg: dict, pool: str, block=None) -> Pool | None:
    """A pool is genuine only if its factory (one of the two Uniswap factories) returns this very address for its tokens."""
    f = _try(rpc, pool, SEL["factory"], block)
    if f is None:
        v2 = _try(rpc, pool, SEL["token0"], block)
        if v2 is None:
            return None
    fac = None
    if f is not None:
        try:
            fac = dec_address(f)
        except MarketError:
            return None
    t0, t1 = _try(rpc, pool, SEL["token0"], block), _try(rpc, pool, SEL["token1"], block)
    if t0 is None or t1 is None:
        return None
    try:
        a0, a1 = dec_address(t0), dec_address(t1)
    except MarketError:
        return None
    if fac == cfg["v3_factory"]:
        fee = _try(rpc, pool, SEL["fee"], block)
        if fee is None:
            return None
        fee_i = dec_uint(fee)
        gp = _try(rpc, fac, calldata(SEL["getPool"], a0, a1, fee_i), block)
        if gp is not None and dec_address(gp) == pool:
            return Pool(pool, "uniswap_v3", fac, a0, a1, fee_i)
        return None
    # V2 pairs expose factory() too; check getPair on the V2 factory
    if fac == cfg["v2_factory"]:
        gp = _try(rpc, fac, calldata(SEL["getPair"], a0, a1), block)
        if gp is not None and dec_address(gp) == pool:
            return Pool(pool, "uniswap_v2", fac, a0, a1, None)
    return None


def check_constants(rpc, cfg: dict) -> dict:
    """Re-verify the hard-coded reference tokens on-chain; returns {address: {ok, symbol, decimals}} (failures are reported)."""
    out = {}
    for addr, (sym, dec) in cfg["expected"].items():
        try:
            m = token_meta(rpc, addr)
            out[addr] = {"ok": m["symbol"] == sym and m["decimals"] == dec, "symbol": m["symbol"], "decimals": m["decimals"]}
        except (MarketError, RpcError) as exc:
            out[addr] = {"ok": False, "error": str(exc)[:100]}
    return out


# ------------------------------------------------------------------------------------------------ swaps
def normalise_swap(kind: str, fields: dict) -> tuple[int, int]:
    """(d0, d1): change of the POOL's balance of token0/token1. Positive = the trader paid that token into the pool."""
    if kind == "uniswap_v3_swap":
        return int(fields["amount0"]), int(fields["amount1"])
    if kind == "uniswap_v2_swap":
        return int(fields["amount0_in"]) - int(fields["amount0_out"]), int(fields["amount1_in"]) - int(fields["amount1_out"])
    raise MarketError("not a swap")


def D(x) -> Decimal:
    return Decimal(int(x))


@dataclass
class Valuation:
    """Turns raw token amounts into USD using only on-chain execution prices."""
    cfg: dict
    decimals: dict                 # token -> int
    eth_usd: "EthSeries"

    def is_stable(self, t): return t in self.cfg["stables"]

    def is_quote(self, t): return t == self.cfg["weth"] or t in self.cfg["stables"]

    def quote_usd(self, token: str, amount: int, block: int, log_index: int):
        """USD value of `amount` (raw, >=0) of a quote token at (block, log_index) or None if no ETH price is known."""
        if token in self.cfg["stables"]:
            return D(amount) / Decimal(10) ** self.decimals[token]
        px = self.eth_usd.at(block, log_index)
        if px is None:
            return None
        return D(amount) / Decimal(10) ** self.decimals[token] * px

    def priced_swap(self, pool: Pool, d0: int, d1: int, block: int, log_index: int):
        """For a pool with exactly one quote leg: dict(token, qty, usd, trader_buys, price_usd) else a reason string."""
        q0, q1 = self.is_quote(pool.token0), self.is_quote(pool.token1)
        if q0 == q1:
            return "both_quote" if q0 else "no_quote_leg"
        base, bd, quote, qd = (pool.token1, d1, pool.token0, d0) if q0 else (pool.token0, d0, pool.token1, d1)
        if bd == 0 or qd == 0 or (bd > 0) == (qd > 0):
            return "degenerate_swap"
        usd = self.quote_usd(quote, abs(qd), block, log_index)
        if usd is None:
            return "no_eth_price"
        qty = D(abs(bd)) / Decimal(10) ** self.decimals[base]
        return {"token": base, "qty": qty, "raw": abs(bd), "usd": usd, "trader_buys": bd < 0, "price_usd": usd / qty}


class EthSeries:
    """ETH/USD from execution prices of WETH/stable pool swaps: sorted list of ((block, log_index), price)."""

    def __init__(self):
        self.pts: list[tuple[tuple[int, int], Decimal]] = []

    def add(self, block: int, log_index: int, price: Decimal):
        self.pts.append(((block, log_index), price))

    def finalize(self):
        self.pts.sort(key=lambda p: p[0])
        return self

    def at(self, block: int, log_index: int):
        """Latest price at or before (block, log_index). Before the first point there is NO price (None): a later price is never
        attached to an earlier moment (the caller records the reason `no_eth_price`)."""
        if not self.pts:
            return None
        lo, hi, key = 0, len(self.pts), (block, log_index)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.pts[mid][0] <= key:
                lo = mid + 1
            else:
                hi = mid
        return self.pts[lo - 1][1] if lo else None


def eth_price_from_swap(cfg: dict, decimals: dict, pool: Pool, d0: int, d1: int):
    """Execution price (USD per ETH) of a WETH/stable swap, else None."""
    pair = {pool.token0: d0, pool.token1: d1}
    if cfg["weth"] not in pair:
        return None
    other = [t for t in pair if t != cfg["weth"]]
    if len(other) != 1 or other[0] not in cfg["stables"]:
        return None
    dw, ds = pair[cfg["weth"]], pair[other[0]]
    if dw == 0 or ds == 0 or (dw > 0) == (ds > 0):
        return None
    return (D(abs(ds)) / Decimal(10) ** decimals[other[0]]) / (D(abs(dw)) / Decimal(10) ** decimals[cfg["weth"]])
