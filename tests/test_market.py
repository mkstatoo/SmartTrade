"""Tests for app/chain/market.py. The fake EVM here is an ENGINE-TEST FIXTURE (a dict of eth_call answers), not market data.
Selectors are verified against keccak256 computed independently of the module."""
from decimal import Decimal

import pytest

from app.chain import market as m
from app.chain.rpc import RpcError
from tests.fake_chain import addr


def keccak4(sig: str) -> str:
    from Crypto.Hash import keccak
    return "0x" + keccak.new(digest_bits=256, data=sig.encode()).hexdigest()[:8]


def test_selectors_match_keccak_of_signatures():
    sigs = {"factory": "factory()", "token0": "token0()", "token1": "token1()", "fee": "fee()",
            "getPool": "getPool(address,address,uint24)", "getPair": "getPair(address,address)",
            "decimals": "decimals()", "symbol": "symbol()", "latestRoundData": "latestRoundData()",
            "balanceOf": "balanceOf(address)"}
    for k, s in sigs.items():
        assert m.SEL[k] == keccak4(s), k


def test_codecs():
    assert m.calldata(m.SEL["getPair"], addr(1), addr(2)) == m.SEL["getPair"] + "0" * 24 + addr(1)[2:] + "0" * 24 + addr(2)[2:]
    assert m.calldata("0x12345678", 3000) == "0x12345678" + format(3000, "064x")
    assert m.dec_address("0x" + "0" * 24 + "ab" * 20) == "0x" + "ab" * 20
    with pytest.raises(m.MarketError):
        m.dec_address("0x" + "1" * 64)
    assert m.dec_uint("0x" + format(7, "064x")) == 7
    assert m.dec_int("0x" + format((1 << 256) - 5, "064x")) == -5
    with pytest.raises(m.MarketError):
        m.dec_uint("0x00")


def _abi_string(s: bytes) -> str:
    return "0x" + format(32, "064x") + format(len(s), "064x") + s.hex().ljust(64 * ((len(s) + 31) // 32), "0")


def test_dec_string_abi_bytes32_and_sanitising():
    assert m.dec_string(_abi_string(b"USDC")) == "USDC"
    assert m.dec_string("0x" + b"MKR".hex().ljust(64, "0")) == "MKR"                       # legacy bytes32
    assert m.dec_string(_abi_string(b"A<script>B")) == "A?script?B"
    assert len(m.dec_string(_abi_string(b"x" * 100))) == 32
    with pytest.raises(m.MarketError):
        m.dec_string(_abi_string(b"x" * 300))


class FakeEvm:
    def __init__(self):
        self.store = {}

    def put(self, to, data, result):
        self.store[(to, data)] = result

    def call(self, to, data, block=None):
        if (to, data) not in self.store:
            raise RpcError("execution reverted", 3)
        return self.store[(to, data)]


def word_addr(a):
    return "0x" + "0" * 24 + a[2:]


CFG = m.CHAINS["ethereum"]
WETH, USDC, USDT, DAI = CFG["weth"], "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7", "0x6b175474e89094c44da98b954eedeac495271d0f"
TOK = addr(0x7001)


def v3_pool(evm, pool, t0, t1, fee, registered=True, factory=None):
    f = factory or CFG["v3_factory"]
    evm.put(pool, m.SEL["factory"], word_addr(f))
    evm.put(pool, m.SEL["token0"], word_addr(t0))
    evm.put(pool, m.SEL["token1"], word_addr(t1))
    evm.put(pool, m.SEL["fee"], "0x" + format(fee, "064x"))
    if registered:
        evm.put(CFG["v3_factory"], m.calldata(m.SEL["getPool"], t0, t1, fee), word_addr(pool))


def v2_pair(evm, pool, t0, t1, registered=True):
    evm.put(pool, m.SEL["factory"], word_addr(CFG["v2_factory"]))
    evm.put(pool, m.SEL["token0"], word_addr(t0))
    evm.put(pool, m.SEL["token1"], word_addr(t1))
    if registered:
        evm.put(CFG["v2_factory"], m.calldata(m.SEL["getPair"], t0, t1), word_addr(pool))


def test_verify_pool_accepts_registered_v3_and_v2():
    evm = FakeEvm()
    v3_pool(evm, addr(0x100), WETH, USDC, 500)
    v2_pair(evm, addr(0x200), TOK, WETH)
    p3, p2 = m.verify_pool(evm, CFG, addr(0x100)), m.verify_pool(evm, CFG, addr(0x200))
    assert (p3.kind, p3.fee, p3.token0, p3.token1) == ("uniswap_v3", 500, WETH, USDC)
    assert (p2.kind, p2.fee) == ("uniswap_v2", None)


def test_verify_pool_rejects_impostors():
    evm = FakeEvm()
    v3_pool(evm, addr(0x101), WETH, USDC, 500, registered=False)                           # claims the factory, factory disagrees
    v3_pool(evm, addr(0x102), WETH, USDC, 500, factory=addr(0xbad))                        # foreign factory
    v2_pair(evm, addr(0x201), TOK, WETH, registered=False)
    evm.put(addr(0x300), m.SEL["token0"], word_addr(TOK))                                  # token-like, no factory
    evm.put(addr(0x300), m.SEL["token1"], word_addr(WETH))
    # a fake pool whose factory() returns the real factory but the factory maps the tokens to a DIFFERENT pool
    v3_pool(evm, addr(0x103), WETH, USDT, 3000, registered=False)
    evm.put(CFG["v3_factory"], m.calldata(m.SEL["getPool"], WETH, USDT, 3000), word_addr(addr(0x104)))
    for a in (0x101, 0x102, 0x201, 0x300, 0x103, 0x999):
        assert m.verify_pool(evm, CFG, addr(a)) is None, hex(a)


def test_token_meta_and_check_constants():
    evm = FakeEvm()
    for t, (s, d) in CFG["expected"].items():
        evm.put(t, m.SEL["symbol"], _abi_string(s.encode()))
        evm.put(t, m.SEL["decimals"], "0x" + format(d, "064x"))
    assert all(v["ok"] for v in m.check_constants(evm, CFG).values())
    evm.put(USDC, m.SEL["decimals"], "0x" + format(18, "064x"))                            # wrong decimals must be flagged
    res = m.check_constants(evm, CFG)
    assert res[USDC]["ok"] is False and res[WETH]["ok"] is True
    with pytest.raises(m.MarketError):
        m.token_meta(evm, addr(0x555))


def test_normalise_swap_signs():
    assert m.normalise_swap("uniswap_v3_swap", {"amount0": -5, "amount1": 7}) == (-5, 7)
    assert m.normalise_swap("uniswap_v2_swap", {"amount0_in": 0, "amount1_in": 9, "amount0_out": 4, "amount1_out": 0}) == (-4, 9)
    with pytest.raises(m.MarketError):
        m.normalise_swap("erc20_transfer", {})


def _val(eth=None):
    s = m.EthSeries()
    if eth is not None:
        s.add(100, 0, Decimal(eth))
    return m.Valuation(CFG, {WETH: 18, USDC: 6, USDT: 6, DAI: 18, TOK: 18}, s.finalize())


def test_priced_swap_buy_and_sell_against_stable():
    v = _val()
    pool = m.Pool(addr(1), "uniswap_v3", CFG["v3_factory"], USDC, TOK, 3000)             # token0 = quote (USDC), token1 = base
    buy = v.priced_swap(pool, 2_000_000_000, -10 * 10 ** 18, 100, 1)                      # pool receives 2000 USDC, pays 10 TOK
    assert buy["trader_buys"] is True and buy["usd"] == Decimal(2000) and buy["qty"] == Decimal(10) and buy["price_usd"] == Decimal(200)
    sell = v.priced_swap(pool, -500_000_000, 5 * 10 ** 18, 100, 1)
    assert sell["trader_buys"] is False and sell["price_usd"] == Decimal(100)


def test_priced_swap_weth_quote_uses_eth_series_and_reasons():
    pool = m.Pool(addr(2), "uniswap_v2", CFG["v2_factory"], TOK, WETH, None)              # base first, quote second
    r = _val("3000").priced_swap(pool, -10 * 10 ** 18, 2 * 10 ** 18, 100, 1)              # 2 WETH for 10 TOK -> 6000 USD
    assert r["usd"] == Decimal(6000) and r["price_usd"] == Decimal(600) and r["trader_buys"] is True
    assert _val().priced_swap(pool, -10 * 10 ** 18, 2 * 10 ** 18, 100, 1) == "no_eth_price"
    both = m.Pool(addr(3), "uniswap_v3", CFG["v3_factory"], WETH, USDC, 500)
    assert _val("3000").priced_swap(both, 1, -1, 100, 1) == "both_quote"
    none = m.Pool(addr(4), "uniswap_v3", CFG["v3_factory"], TOK, addr(0x7002), 500)
    assert _val("3000").priced_swap(none, 1, -1, 100, 1) == "no_quote_leg"
    assert _val("3000").priced_swap(pool, 5, 5, 100, 1) == "degenerate_swap"
    assert _val("3000").priced_swap(pool, 0, 5, 100, 1) == "degenerate_swap"


def test_eth_series_lookup_ordering():
    s = m.EthSeries()
    s.add(20, 0, Decimal(2)); s.add(10, 5, Decimal(1)); s.add(10, 9, Decimal("1.5"))
    s.finalize()
    assert s.at(10, 4) is None                       # before the first point there is NO price (never a later one)
    assert s.at(10, 5) == Decimal(1) and s.at(10, 8) == Decimal(1)
    assert s.at(10, 9) == Decimal("1.5") and s.at(19, 99) == Decimal("1.5")
    assert s.at(20, 0) == Decimal(2) and s.at(999, 0) == Decimal(2)
    assert m.EthSeries().at(1, 1) is None


def test_eth_price_from_swap():
    p = m.Pool(addr(5), "uniswap_v3", CFG["v3_factory"], USDC, WETH, 500)
    dec = {WETH: 18, USDC: 6}
    # pool receives 3000 USDC and pays 1 WETH -> 3000
    assert m.eth_price_from_swap(CFG, dec, p, 3_000_000_000, -10 ** 18) == Decimal(3000)
    assert m.eth_price_from_swap(CFG, dec, p, 3_000_000_000, 10 ** 18) is None       # same direction: not a swap
    other = m.Pool(addr(6), "uniswap_v3", CFG["v3_factory"], TOK, WETH, 500)
    assert m.eth_price_from_swap(CFG, {**dec, TOK: 18}, other, 1, -1) is None        # WETH/non-stable is not a price source


def _pts(prices, start=100):
    return [(start + i, 0, Decimal(str(p))) for i, p in enumerate(prices)]


def test_robust_series_is_causal_and_warmup_points_are_not_usable():
    from app.chain import pipeline
    ser, dropped = pipeline.robust_eth_series(_pts([3000, 3001, 3002, 3001, 3000, 3002, 3003, 3300, 3004, 3005]))
    assert dropped == 1                                              # the 3300 print is an outlier against what came BEFORE it
    assert ser.at(104, 0) is None                                    # inside warm-up: no price yet
    assert ser.at(105, 0) == Decimal(3002) and ser.at(107, 0) == Decimal(3003) and ser.at(109, 0) == Decimal(3005)
    # changing anything AFTER a moment cannot change the price at that moment
    a, _ = pipeline.robust_eth_series(_pts([3000, 3001, 3002, 3001, 3000, 3002, 3003, 3004]))
    b, _ = pipeline.robust_eth_series(_pts([3000, 3001, 3002, 3001, 3000, 3002, 3003, 3004, 9999, 1, 5000]))
    for blk in range(100, 108):
        assert a.at(blk, 0) == b.at(blk, 0)


def test_robust_series_recovers_from_a_real_regime_change_without_looking_ahead():
    from app.chain import pipeline
    ser, dropped = pipeline.robust_eth_series(_pts([3000] * 6 + [3300, 3301, 3302, 3300, 3301, 3302, 3303]))
    assert dropped == 5                                              # five consistent rejects trigger re-seeding
    assert ser.at(105, 0) == Decimal(3000)
    assert ser.at(111, 0) == Decimal(3302) and ser.at(112, 0) == Decimal(3303)
    assert ser.at(110, 0) == Decimal(3000)                           # the new regime is NOT applied retroactively


def test_chain_configs_are_well_formed_and_base_is_not_ethereum():
    from app.chain import market
    import re
    for name, cfg in market.CHAINS.items():
        for k in ("v3_factory", "v2_factory", "weth", "chainlink_eth_usd"):
            assert re.fullmatch(r"0x[0-9a-f]{40}", cfg[k]), (name, k)
        assert set(cfg["stables"]) <= set(cfg["expected"]) and cfg["weth"] in cfg["expected"]
        assert all(re.fullmatch(r"0x[0-9a-f]{40}", a) for a in cfg["expected"])
        assert cfg["expected"][cfg["weth"]] == ("WETH", 18)
    eth, base = market.CHAINS["ethereum"], market.CHAINS["base"]
    assert base["chain_id"] == 8453 and eth["chain_id"] == 1
    for k in ("v3_factory", "v2_factory", "weth", "chainlink_eth_usd"):
        assert eth[k] != base[k]
    assert not set(eth["expected"]) & set(base["expected"]) - {base["weth"]}
