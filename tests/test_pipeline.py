"""End-to-end test of discovery -> receipts -> wallet trades -> PnL on a synthetic world with hidden truth (see fake_market)."""
from collections import Counter
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import dict_row

from app.chain import abi, market, pipeline
from app.chain.ingest import ingest
from app.chain.rpc import RpcError
from app.migrate import migrate
from tests import fake_market as fm
from tests.conftest import needs_pg

pytestmark = needs_pg
START = 50
CFG = fm.CFG


@pytest.fixture
def db(pgdb):
    migrate(pgdb)
    return pgdb


def q(dsn, sql, *a):
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        return c.execute(sql, a).fetchall()


def run_all(db, *, seed=7, blocks=100, top_k=4):
    w = fm.World(blocks, start=START).build(seed)
    ch = w.chain()
    ingest(ch, db, "eth-disc", start_block=0, confirmations=12, max_blocks=START, topics0=pipeline.SWAP_TOPICS)
    disc = pipeline.discover_pools(db, ch, "eth", CFG, discovery_chain="eth-disc", top_k=top_k)
    pools = sorted(pipeline.watch_list(db, "eth"))
    ingest(ch, db, "eth", start_block=START, confirmations=12, topics0=pipeline.SWAP_TOPICS, addresses=pools)
    col = pipeline.collect_txs(db, lambda: ch, "eth", workers=3)
    der = pipeline.derive_trades(db, "eth", CFG)
    return w, ch, disc, col, der


def block_of(w):
    return {lg["tx"]: n for n, logs in w.logs.items() for lg in logs if lg.get("tx")}


def test_watch_list_is_verified_and_excludes_impostor_and_quoteless_pools(db):
    w, ch, disc, col, der = run_all(db)
    assert set(pipeline.watch_list(db, "eth")) == {fm.P_AW, fm.P_BU, fm.P_AU, fm.P_REF, fm.P_REF2}
    assert fm.P_IMP in disc["rejected_unverified"]                       # the most active "pool" is not a Uniswap pool
    roles = {p["pool"]: p["role"] for p in disc["pools"]}
    assert roles[fm.P_REF] == roles[fm.P_REF2] == "reference" and roles[fm.P_AW] == "watch"
    assert all(v["ok"] for v in disc["constants"].values())
    toks = {r["address"]: (r["symbol"], r["decimals"]) for r in q(db, "SELECT * FROM chain_tokens WHERE chain='eth'")}
    assert toks[fm.TOKB] == ("TKB", 8) and toks[fm.TOKA] == ("TKA", 18)
    pairs = {p["pool"]: p["pair"] for p in disc["pools"]}
    assert pairs[fm.P_AW] == "TKA/WETH"


def test_derived_trades_equal_hidden_truth(db):
    w, ch, disc, col, der = run_all(db)
    blk = block_of(w)
    truth = [t for t in w.truth["trades"] if blk[t["tx"]] >= START]
    assert len(truth) > 30                                                # the world is not trivially small
    got = {(r["tx_hash"], r["token"]): r for r in q(db, "SELECT * FROM chain_trades_canonical WHERE chain='eth'")}
    assert len(got) == len(truth) == der.trades
    for t in truth:
        r = got[(t["tx"], t["token"])]
        assert (r["wallet"], r["side"], r["confidence"]) == (t["wallet"], t["side"], t["conf"]), t
        assert r["qty"] == t["qty"], t                                    # exact: quantities come from the swap's raw integers
        assert abs(r["usd"] - t["usd"]) <= t["usd"] * Decimal("1e-6"), (t, r["usd"])
        assert r["price_usd"] == r["usd"] / r["qty"] or abs(r["price_usd"] * r["qty"] - r["usd"]) < Decimal("1e-9")
    kinds = Counter(t["conf"] for t in truth)
    assert kinds["confirmed"] and kinds["mismatch"] and der.confirmed == kinds["confirmed"] and der.mismatch == kinds["mismatch"]


def test_skips_match_truth_and_unwatched_pools_leave_no_trace(db):
    w, ch, disc, col, der = run_all(db)
    blk = block_of(w)
    watched = {fm.P_AW, fm.P_BU, fm.P_AU, fm.P_REF, fm.P_REF2}
    expect = {(tx, r) for tx, r in w.truth["skips"] if blk[tx] >= START and r != "no_quote_leg"}
    got = {(r["tx_hash"], r["reason"]) for r in q(db, "SELECT tx_hash, reason FROM chain_trade_skips WHERE chain='eth'")}
    assert got == expect
    assert {r for _, r in expect} >= {"quote_only", "no_sender_transfer", "zero_net_flow"}
    quoteless = {tx for tx, r in w.truth["skips"] if r == "no_quote_leg"}
    assert quoteless and not (quoteless & {r["tx_hash"] for r in q(db, "SELECT tx_hash FROM chain_txs WHERE chain='eth'")})
    assert watched                                                         # (pool P_AB was never watched, so its txs were never fetched)


def test_gas_is_priced_once_per_transaction_at_the_true_eth_price(db):
    w, ch, disc, col, der = run_all(db)
    blk = block_of(w)
    rows = q(db, "SELECT tx_hash, sum(gas_usd) g, count(*) n FROM chain_trades_canonical WHERE chain='eth' GROUP BY tx_hash")
    assert rows
    for r in rows:
        n = blk[r["tx_hash"]]
        meta = w.meta[r["tx_hash"]]
        exp = Decimal(meta["gas_used"]) * Decimal(meta["egp"]) / 10 ** 18 * fm.eth_price(n)
        assert abs(r["g"] - exp) <= exp * Decimal("1e-6"), (r["tx_hash"], r["g"], exp)
    assert any(r["n"] == 2 for r in rows)                                  # the two-hop tx carries its gas exactly once


def test_manipulated_eth_print_is_dropped_and_does_not_move_prices(db):
    w, ch, disc, col, der = run_all(db)
    assert der.eth_outliers_dropped >= 1
    bad_block = START + fm.BAD_BLOCK_OFFSET
    rows = q(db, "SELECT * FROM chain_trades_canonical WHERE chain='eth' AND block_number=%s", bad_block)
    assert rows
    for r in rows:
        if r["confidence"] == "confirmed":
            t = next(t for t in w.truth["trades"] if t["tx"] == r["tx_hash"] and t["token"] == r["token"])
            assert abs(r["usd"] - t["usd"]) <= t["usd"] * Decimal("1e-6")


def test_rederiving_and_recollecting_is_idempotent(db):
    w, ch, disc, col, der = run_all(db)
    before = q(db, "SELECT tx_hash, wallet, token, side, qty, usd, gas_usd, confidence FROM chain_trades ORDER BY tx_hash, token")
    col2 = pipeline.collect_txs(db, lambda: ch, "eth")
    assert col2.txs == 0 and col2.already == col.txs
    der2 = pipeline.derive_trades(db, "eth", CFG)
    assert der2.trades == der.trades and dict(der2.skips) == dict(der.skips)
    assert q(db, "SELECT tx_hash, wallet, token, side, qty, usd, gas_usd, confidence FROM chain_trades ORDER BY tx_hash, token") == before


def test_orphaned_blocks_drop_out_of_derivation(db):
    w, ch, disc, col, der = run_all(db)
    total = len(q(db, "SELECT 1 FROM chain_trades_canonical WHERE chain='eth'"))
    inside = len(q(db, "SELECT 1 FROM chain_trades_canonical WHERE chain='eth' AND block_number BETWEEN 60 AND 70"))
    assert inside > 0
    with psycopg.connect(db, autocommit=True) as c:                        # what a reorg does to those blocks (ingest tests cover the real path)
        c.execute("UPDATE chain_blocks SET canonical=false WHERE chain='eth' AND block_number BETWEEN 60 AND 70")
    pipeline.derive_trades(db, "eth", CFG)
    assert len(q(db, "SELECT 1 FROM chain_trades_canonical WHERE chain='eth'")) == total - inside
    assert len(q(db, "SELECT 1 FROM chain_trades WHERE chain='eth' AND block_number BETWEEN 60 AND 70")) == inside   # kept for audit


def test_receipt_that_disagrees_with_getlogs_is_rejected_and_errors_are_counted(db):
    w = fm.World(100, start=START).build(7)
    ch = w.chain()
    ingest(ch, db, "eth-disc", start_block=0, confirmations=12, max_blocks=START, topics0=pipeline.SWAP_TOPICS)
    pipeline.discover_pools(db, ch, "eth", CFG, discovery_chain="eth-disc", top_k=4)
    ingest(ch, db, "eth", start_block=START, confirmations=12, topics0=pipeline.SWAP_TOPICS, addresses=sorted(pipeline.watch_list(db, "eth")))
    txs = sorted({l["tx_hash"] for l in q(db, "SELECT tx_hash FROM chain_logs_canonical WHERE chain='eth'")}) if False else \
        sorted({r["tx_hash"] for r in q(db, "SELECT tx_hash FROM chain_logs_canonical WHERE chain='eth'")})
    tampered, missing = txs[0], txs[1]
    real = ch.receipt

    def receipt(h):
        if h == missing:
            raise RpcError("receipt not available")
        r = real(h)
        if h == tampered:
            r["logs"] = [l for l in r["logs"] if l["topics"][0] not in pipeline.SWAP_TOPICS]      # swap log vanished
        return r
    ch.receipt = receipt
    col = pipeline.collect_txs(db, lambda: ch, "eth")
    assert col.inconsistent == 1 and col.receipt_errors == 1 and col.txs == len(txs) - 2
    stored = {r["tx_hash"] for r in q(db, "SELECT tx_hash FROM chain_txs")}
    assert tampered not in stored and missing not in stored


def test_wrong_reference_constants_stop_discovery(db):
    w = fm.World(60, start=START).build(7)
    ch = w.chain()
    ch.evm[(fm.USDC, market.SEL["decimals"])] = "0x" + format(18, "064x")
    ingest(ch, db, "eth-disc", start_block=0, confirmations=12, max_blocks=40, topics0=pipeline.SWAP_TOPICS)
    with pytest.raises(market.MarketError):
        pipeline.discover_pools(db, ch, "eth", CFG, discovery_chain="eth-disc")
    assert q(db, "SELECT 1 FROM chain_pools") == []


def test_collect_without_watchlist_is_an_error(db):
    with pytest.raises(market.MarketError):
        pipeline.collect_txs(db, lambda: None, "eth")


def test_wallet_pnl_uses_only_confirmed_trades_and_matches_truth(db):
    from app.ids import token_key
    w, ch, disc, col, der = run_all(db)
    blk = block_of(w)
    pnl = pipeline.wallet_pnl(db, "eth")
    truth = [t for t in w.truth["trades"] if blk[t["tx"]] >= START and t["conf"] == "confirmed"]
    assert set(pnl) == {t["wallet"] for t in truth}
    for wallet, res in pnl.items():
        for token in (fm.TOKA, fm.TOKB):
            mine = [t for t in truth if t["wallet"] == wallet and t["token"] == token]
            st = res["tokens"].get(token_key("eth", token))
            if not mine:
                assert st is None
                continue
            assert Decimal(str(st["bought_qty"])) == sum((t["qty"] for t in mine if t["side"] == "buy"), Decimal(0))
            assert Decimal(str(st["sold_qty"])) == sum((t["qty"] for t in mine if t["side"] == "sell"), Decimal(0))
        assert res["missing_marks"] == []
