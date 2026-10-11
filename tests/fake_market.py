"""ENGINE-TEST FIXTURE: a synthetic Uniswap world with HIDDEN TRUE prices and a ground-truth list of what every wallet really did.
It is not market data. The pipeline under test never sees `truth`; tests compare its output to it.

Trade shapes covered: direct swap, router with small fee, router with a fee beyond tolerance, relayer (tx.from is not the
beneficiary), two-hop route (two trades in one tx), zero-net arbitrage, quote-for-quote swap, pool without a quote leg, an
impostor pool that outnumbers every real pool in swaps, one manipulated ETH price print."""
import random
from decimal import Decimal

from app.chain import market as m
from tests.fake_chain import FakeChain, _h, addr, transfer_log, v2_swap_log, v3_swap_log

CFG = m.CHAINS["ethereum"]
WETH = CFG["weth"]
USDC, USDT, DAI = ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7",
                   "0x6b175474e89094c44da98b954eedeac495271d0f")
TOKA, TOKB = addr(0x7001), addr(0x7002)
DEC = {WETH: 18, USDC: 6, USDT: 6, DAI: 18, TOKA: 18, TOKB: 8}
SYM = {WETH: "WETH", USDC: "USDC", USDT: "USDT", DAI: "DAI", TOKA: "TKA", TOKB: "TKB"}
ROUTER, RELAYER, BOT = addr(0x5001), addr(0x5002), addr(0x9000)
WALLETS = [addr(0x2000 + i) for i in range(6)]
P_REF, P_REF2, P_AW, P_BU, P_AU, P_AB, P_IMP = (addr(0x1001), addr(0x1002), addr(0x1003), addr(0x1004), addr(0x1005), addr(0x1006), addr(0x1666))
BAD_BLOCK_OFFSET = 20          # the manipulated ETH print happens this many blocks after `start`


def eth_price(n: int, shock=None) -> Decimal:
    """shock=(block, factor): every price AFTER `block` is multiplied by factor (used to prove that the future cannot change the past)."""
    px = Decimal(3000) + Decimal(n % 40) * Decimal("1.5")
    return px * Decimal(str(shock[1])) if shock and n > shock[0] else px


def tok_price(t: str, n: int) -> Decimal:
    return Decimal("2.5") * (1 + Decimal(n % 7) / 1000) if t == TOKA else Decimal("0.4") * (1 + Decimal(n % 5) / 500)


def _word(a): return "0x" + "0" * 24 + a[2:]


def _sorted(a, b): return (a, b) if int(a, 16) < int(b, 16) else (b, a)


IMPOSTOR = ("uniswap_v3", TOKA, USDC, 500)
POOLS = {P_REF: ("uniswap_v3", USDC, WETH, 500), P_REF2: ("uniswap_v2", DAI, WETH, None), P_AW: ("uniswap_v3", TOKA, WETH, 3000),
         P_BU: ("uniswap_v2", TOKB, USDC, None), P_AU: ("uniswap_v3", TOKA, USDC, 500), P_AB: ("uniswap_v2", TOKA, TOKB, None)}


def install_evm(chain: FakeChain):
    ev = chain.evm
    for t, d in DEC.items():
        ev[(t, m.SEL["decimals"])] = "0x" + format(d, "064x")
        s = SYM[t].encode()
        ev[(t, m.SEL["symbol"])] = "0x" + format(32, "064x") + format(len(s), "064x") + s.hex().ljust(64, "0")
    for p, (kind, a, b, fee) in POOLS.items():
        t0, t1 = _sorted(a, b)
        fac = CFG["v3_factory"] if kind == "uniswap_v3" else CFG["v2_factory"]
        ev[(p, m.SEL["factory"])] = _word(fac)
        ev[(p, m.SEL["token0"])], ev[(p, m.SEL["token1"])] = _word(t0), _word(t1)
        if kind == "uniswap_v3":
            ev[(p, m.SEL["fee"])] = "0x" + format(fee, "064x")
            ev[(fac, m.calldata(m.SEL["getPool"], t0, t1, fee))] = _word(p)
        else:
            ev[(fac, m.calldata(m.SEL["getPair"], t0, t1))] = _word(p)
    t0, t1 = _sorted(TOKA, USDC)                                   # impostor: says "V3 factory, TOKA/USDC 500" but the factory knows P_AU
    ev[(P_IMP, m.SEL["factory"])] = _word(CFG["v3_factory"])
    ev[(P_IMP, m.SEL["token0"])], ev[(P_IMP, m.SEL["token1"])] = _word(t0), _word(t1)
    ev[(P_IMP, m.SEL["fee"])] = "0x" + format(500, "064x")


class World:
    def __init__(self, blocks: int, start: int = 0, shock=None):
        self.blocks, self.start, self.shock = blocks, start, shock
        self.logs = {n: [] for n in range(blocks)}
        self.meta = {}
        self.truth = {"trades": [], "skips": []}
        self.k = 0

    def eth(self, n):
        return eth_price(n, self.shock)

    def _tx(self, n, frm, status=1, gas=150_000, egp=20 * 10 ** 9, to=None):
        self.k += 1
        h = _h("wtx", n, self.k)
        self.meta[h] = {"from": frm, "to": to, "status": status, "gas_used": gas, "egp": egp}
        return h

    def _swap(self, n, tx, pool, base_or_none, trader_pays: dict, trader_gets: dict, sender, recipient):
        """trader_pays/gets: {token: raw}. Emits the pool's Swap log (pool perspective) for the pool's two tokens."""
        kind, a, b, fee = POOLS.get(pool) or IMPOSTOR
        t0, t1 = _sorted(a, b)
        d0 = trader_pays.get(t0, 0) - trader_gets.get(t0, 0)
        d1 = trader_pays.get(t1, 0) - trader_gets.get(t1, 0)
        if kind == "uniswap_v3":
            lg = v3_swap_log(pool, sender, recipient, d0, d1, 10 ** 20, 10 ** 15, 100)
        else:
            lg = v2_swap_log(pool, sender, recipient, max(d0, 0), max(d1, 0), max(-d0, 0), max(-d1, 0))
        lg["tx"] = tx
        self.logs[n].append(lg)

    def _tr(self, n, tx, token, frm, to, amt):
        lg = transfer_log(token, frm, to, amt)
        lg["tx"] = tx
        self.logs[n].append(lg)

    def _amounts(self, n, base, quote, qty: Decimal):
        braw = int(qty * Decimal(10) ** DEC[base])
        usd = Decimal(braw) / Decimal(10) ** DEC[base] * tok_price(base, n)
        qraw = int(usd / (self.eth(n) if quote == WETH else 1) * Decimal(10) ** DEC[quote])
        tq = Decimal(qraw) / Decimal(10) ** DEC[quote] * (self.eth(n) if quote == WETH else 1)
        return braw, qraw, Decimal(braw) / Decimal(10) ** DEC[base], tq      # raw base, raw quote, true qty, true usd

    def trade(self, n, pool, base, quote, buys, wallet, rng, style="direct", frm=None, fee_bps=0, beneficiary=None):
        qty = Decimal(rng.randint(10, 500)) / Decimal(10) if base == TOKA else Decimal(rng.randint(100, 5000)) / Decimal(10)
        braw, qraw, tq, tusd = self._amounts(n, base, quote, qty)
        tx = self._tx(n, frm or wallet, to=ROUTER if style != "direct" else None)
        who = beneficiary or wallet
        pays, gets = ({quote: qraw}, {base: braw}) if buys else ({base: braw}, {quote: qraw})
        self._swap(n, tx, pool, base, pays, gets, ROUTER if style != "direct" else wallet, ROUTER if style != "direct" else who)
        if style == "direct":
            if buys:
                self._tr(n, tx, quote, who, pool, qraw); self._tr(n, tx, base, pool, who, braw)
            else:
                self._tr(n, tx, base, who, pool, braw); self._tr(n, tx, quote, pool, who, qraw)
        else:                                                       # via router (aggregator takes fee_bps from what is delivered)
            if buys:
                got = braw * (10000 - fee_bps) // 10000
                self._tr(n, tx, quote, who, pool, qraw); self._tr(n, tx, base, pool, ROUTER, braw); self._tr(n, tx, base, ROUTER, who, got)
            else:
                got = qraw * (10000 - fee_bps) // 10000
                self._tr(n, tx, base, who, pool, braw); self._tr(n, tx, quote, pool, ROUTER, qraw); self._tr(n, tx, quote, ROUTER, who, got)
        return tx, tq, tusd, who

    def build(self, seed=7):
        rng = random.Random(seed)
        for n in range(self.blocks):
            # reference ETH prints first in the block: they set the price for later log indexes of the same block
            for pool in (P_REF, P_REF2):
                w = Decimal(rng.randint(2, 50)) / 10
                wraw = int(w * 10 ** 18)
                stable = USDC if pool == P_REF else DAI
                sraw = int(Decimal(wraw) / Decimal(10) ** 18 * self.eth(n) * Decimal(10) ** DEC[stable])
                tx = self._tx(n, BOT)
                buys_eth = rng.random() < 0.5
                pays, gets = ({stable: sraw}, {WETH: wraw}) if buys_eth else ({WETH: wraw}, {stable: sraw})
                self._swap(n, tx, pool, None, pays, gets, BOT, BOT)
                for tok, amt, frm, to in ((stable, sraw, BOT, pool) if buys_eth else (stable, sraw, pool, BOT)), \
                                         ((WETH, wraw, pool, BOT) if buys_eth else (WETH, wraw, BOT, pool)):
                    self._tr(n, tx, tok, frm, to, amt)
                self.truth["skips"].append((tx, "quote_only"))
            if n == self.start + BAD_BLOCK_OFFSET:                  # manipulated print: +25% in the DAI pool
                wraw, tx = 10 ** 18, self._tx(n, BOT)
                sraw = int(self.eth(n) * Decimal("1.25") * 10 ** 18)
                self._swap(n, tx, P_REF2, None, {DAI: sraw}, {WETH: wraw}, BOT, BOT)
                self._tr(n, tx, DAI, BOT, P_REF2, sraw); self._tr(n, tx, WETH, P_REF2, BOT, wraw)
                self.truth["skips"].append((tx, "quote_only"))
            for _ in range(3):                                      # impostor pool noise (never a real pool)
                tx = self._tx(n, BOT)
                self._swap(n, tx, P_IMP, None, {USDC: 10 ** 9}, {TOKA: 10 ** 18}, BOT, BOT)
            for _ in range(2):
                self._scenario(n, rng)
        return self

    def _scenario(self, n, rng):
        w = rng.choice(WALLETS)
        sc = rng.choice(["direct_buy", "direct_sell", "direct_buy_b", "router_buy", "router_fee5", "relayer", "multihop", "arb",
                         "quote_swap", "no_quote", "multihop_mixed"])
        T = self.truth
        if sc in ("direct_buy", "direct_sell"):
            pool, quote = rng.choice([(P_AW, WETH), (P_AU, USDC)])
            tx, q, u, who = self.trade(n, pool, TOKA, quote, sc == "direct_buy", w, rng)
            T["trades"].append({"tx": tx, "wallet": w, "token": TOKA, "side": "buy" if sc == "direct_buy" else "sell", "qty": q, "usd": u, "conf": "confirmed", "quote": quote})
        elif sc == "direct_buy_b":
            tx, q, u, who = self.trade(n, P_BU, TOKB, USDC, rng.random() < 0.5, w, rng)
            T["trades"].append({"tx": tx, "wallet": w, "token": TOKB, "side": self._side_of(n, tx, TOKB, w), "qty": q, "usd": u, "conf": "confirmed", "quote": USDC})
        elif sc == "router_buy":
            tx, q, u, who = self.trade(n, P_AW, TOKA, WETH, True, w, rng, style="router", fee_bps=50)
            T["trades"].append({"tx": tx, "wallet": w, "token": TOKA, "side": "buy", "qty": q, "usd": u, "conf": "confirmed", "quote": WETH})
        elif sc == "router_fee5":
            tx, q, u, who = self.trade(n, P_AU, TOKA, USDC, True, w, rng, style="router", fee_bps=500)
            T["trades"].append({"tx": tx, "wallet": w, "token": TOKA, "side": "buy", "qty": q, "usd": u, "conf": "mismatch", "quote": USDC})
        elif sc == "relayer":
            tx, q, u, who = self.trade(n, P_AU, TOKA, USDC, True, w, rng, style="router", frm=RELAYER)
            T["skips"].append((tx, "no_sender_transfer"))
        elif sc == "multihop":
            qa = Decimal(rng.randint(10, 300)) / 10
            ba, ra, qty_a, usd_a = self._amounts(n, TOKA, USDC, qa)                 # sell TOKA for USDC
            bb_qty = (usd_a / tok_price(TOKB, n)).quantize(Decimal("0.01"))
            bb, rb, qty_b, usd_b = self._amounts(n, TOKB, USDC, bb_qty)             # buy TOKB with the USDC
            tx = self._tx(n, w)
            self._swap(n, tx, P_AU, None, {TOKA: ba}, {USDC: ra}, ROUTER, P_BU)
            self._swap(n, tx, P_BU, None, {USDC: rb}, {TOKB: bb}, ROUTER, w)
            self._tr(n, tx, TOKA, w, P_AU, ba); self._tr(n, tx, USDC, P_AU, P_BU, ra)
            self._tr(n, tx, TOKB, P_BU, w, bb)
            T["trades"] += [{"tx": tx, "wallet": w, "token": TOKA, "side": "sell", "qty": qty_a, "usd": Decimal(ra) / 10 ** 6, "conf": "confirmed", "quote": USDC},
                            {"tx": tx, "wallet": w, "token": TOKB, "side": "buy", "qty": qty_b, "usd": Decimal(rb) / 10 ** 6, "conf": "confirmed", "quote": USDC}]
        elif sc == "multihop_mixed":
            # sell TOKB (confirmed), buy TOKA through a router that keeps 5% (mismatch). TOKA sorts first, so the FIRST trade of the tx
            # is the mismatch one: the gas of the transaction must still end up on the confirmed trade.
            bb, rb, qty_b, _ = self._amounts(n, TOKB, USDC, Decimal(rng.randint(100, 3000)) / 10)
            ba, ra, qty_a, _ = self._amounts(n, TOKA, USDC, (Decimal(rb) / 10 ** 6 / tok_price(TOKA, n)).quantize(Decimal("0.01")))
            tx = self._tx(n, w, to=ROUTER)
            self._swap(n, tx, P_BU, None, {TOKB: bb}, {USDC: rb}, ROUTER, P_AU)
            self._swap(n, tx, P_AU, None, {USDC: ra}, {TOKA: ba}, ROUTER, ROUTER)
            self._tr(n, tx, TOKB, w, P_BU, bb); self._tr(n, tx, USDC, P_BU, P_AU, rb)
            self._tr(n, tx, TOKA, P_AU, ROUTER, ba); self._tr(n, tx, TOKA, ROUTER, w, ba * 95 // 100)
            T["trades"] += [{"tx": tx, "wallet": w, "token": TOKA, "side": "buy", "qty": qty_a, "usd": Decimal(ra) / 10 ** 6, "conf": "mismatch", "quote": USDC},
                            {"tx": tx, "wallet": w, "token": TOKB, "side": "sell", "qty": qty_b, "usd": Decimal(rb) / 10 ** 6, "conf": "confirmed", "quote": USDC}]
        elif sc == "arb":
            braw, qraw, _, _ = self._amounts(n, TOKA, WETH, Decimal(25))
            _, qraw2, _, _ = self._amounts(n, TOKA, USDC, Decimal(25))
            tx = self._tx(n, w)
            self._swap(n, tx, P_AW, None, {WETH: qraw}, {TOKA: braw}, w, w)
            self._swap(n, tx, P_AU, None, {TOKA: braw}, {USDC: qraw2}, w, w)
            self._tr(n, tx, WETH, w, P_AW, qraw); self._tr(n, tx, TOKA, P_AW, P_AU, braw); self._tr(n, tx, USDC, P_AU, w, qraw2)
            T["skips"].append((tx, "zero_net_flow"))
        elif sc == "quote_swap":
            tx = self._tx(n, w)
            self._swap(n, tx, P_REF, None, {WETH: 10 ** 18}, {USDC: int(self.eth(n) * 10 ** 6)}, w, w)
            self._tr(n, tx, WETH, w, P_REF, 10 ** 18); self._tr(n, tx, USDC, P_REF, w, int(self.eth(n) * 10 ** 6))
            T["skips"].append((tx, "quote_only"))
        else:                                                       # no quote leg: TOKA -> TOKB
            tx = self._tx(n, w)
            self._swap(n, tx, P_AB, None, {TOKA: 10 ** 18}, {TOKB: 10 ** 8}, w, w)
            self._tr(n, tx, TOKA, w, P_AB, 10 ** 18); self._tr(n, tx, TOKB, P_AB, w, 10 ** 8)
            T["skips"].append((tx, "no_quote_leg"))

    def _side_of(self, n, tx, base, wallet):
        for lg in self.logs[n]:
            if lg.get("tx") == tx and lg["address"] == base:
                return "buy" if lg["topics"][2] == "0x" + "0" * 24 + wallet[2:] else "sell"
        raise AssertionError

    def balance_dyn(self, ch, frozen=False):
        """balanceOf(address) from the world's own Transfer logs (state at the END of block b). `frozen` returns a constant: a node that lies."""
        base = 10 ** 30

        def dyn(to, data, block):
            if not data.startswith(m.SEL["balanceOf"]):
                return None
            who = "0x" + data[-40:]
            if frozen:
                return "0x" + format(base, "064x")
            top = ch.tip if block is None else block
            bal = base
            for n in range(0, min(top, self.blocks - 1) + 1):
                for lg in self.logs[n]:
                    if lg["address"] != to or lg["topics"][0] != "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
                        continue
                    amt = int(lg["data"], 16)
                    bal += amt if lg["topics"][2][-40:] == who[2:] else 0
                    bal -= amt if lg["topics"][1][-40:] == who[2:] else 0
            return "0x" + format(bal, "064x")
        return dyn

    def chain(self, salt="a", tail=40) -> FakeChain:
        """FakeChain with `tail` empty blocks after the world (confirmations)."""
        ch = FakeChain(self.blocks + tail, salt=salt, logs_at=self.logs)
        ch.tx_meta = dict(self.meta)
        install_evm(ch)
        return ch
