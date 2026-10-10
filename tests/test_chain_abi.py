import pytest
from Crypto.Hash import keccak

from app.chain import abi
from tests.fake_chain import addr, transfer_log, v2_swap_log, v3_swap_log, TRANSFER, topic_addr


def k(sig):
    return "0x" + keccak.new(digest_bits=256, data=sig.encode()).hexdigest()


def test_topic_hashes_are_keccak_of_signatures():
    assert abi.TOPIC_ERC20_TRANSFER == k("Transfer(address,address,uint256)")
    assert abi.TOPIC_V2_SWAP == k("Swap(address,uint256,uint256,uint256,uint256,address)")
    assert abi.TOPIC_V3_SWAP == k("Swap(address,address,int256,int256,uint160,uint128,int24)")


def test_transfer_roundtrip_and_max_value():
    big = (1 << 256) - 1
    kind, f = abi.decode(transfer_log(addr(9), addr(1), addr(2), big))
    assert kind == "erc20_transfer" and f == {"token": addr(9), "from": addr(1), "to": addr(2), "amount": str(big)}


def test_v2_swap_roundtrip():
    kind, f = abi.decode(v2_swap_log(addr(5), addr(1), addr(2), 10, 0, 0, 77))
    assert kind == "uniswap_v2_swap"
    assert (f["amount0_in"], f["amount1_in"], f["amount0_out"], f["amount1_out"]) == ("10", "0", "0", "77")


@pytest.mark.parametrize("a0,a1,tick", [(-5, 7, -887272), (123456789, -987654321, 887272), (0, -1, 0), (-(1 << 255), (1 << 255) - 1, -1)])
def test_v3_swap_signed_values(a0, a1, tick):
    kind, f = abi.decode(v3_swap_log(addr(5), addr(1), addr(2), a0, a1, (1 << 160) - 1, (1 << 128) - 1, tick))
    assert kind == "uniswap_v3_swap"
    assert (int(f["amount0"]), int(f["amount1"]), f["tick"]) == (a0, a1, tick)
    assert f["sqrt_price_x96"] == str((1 << 160) - 1) and f["liquidity"] == str((1 << 128) - 1)


def test_erc721_transfer_is_ignored_not_misdecoded():
    log = {"address": addr(3), "topics": [TRANSFER, topic_addr(addr(1)), topic_addr(addr(2)), "0x" + "00" * 31 + "07"], "data": "0x"}
    assert abi.decode(log) is None


def test_unknown_and_empty_topics_ignored():
    assert abi.decode({"address": addr(1), "topics": ["0x" + "11" * 32], "data": "0x"}) is None
    assert abi.decode({"address": addr(1), "topics": [], "data": "0x"}) is None


@pytest.mark.parametrize("mutate", [
    lambda l: l.update(data=l["data"][:-2]),                                   # truncated
    lambda l: l.update(data=l["data"] + "00"),                                 # trailing byte
    lambda l: l.update(topics=l["topics"][:2]),                                # missing topic
    lambda l: l.update(topics=[l["topics"][0], "0x" + "ff" * 32, l["topics"][2]]),   # dirty address padding
    lambda l: l.update(data="0xZZ"),
])
def test_malformed_transfer_raises(mutate):
    log = transfer_log(addr(9), addr(1), addr(2), 5)
    mutate(log)
    with pytest.raises(abi.DecodeError):
        abi.decode(log)


def test_v3_out_of_range_fields_rejected():
    log = v3_swap_log(addr(5), addr(1), addr(2), 1, 1, 1, 1, 0)
    log["data"] = log["data"][:2 + 64 * 4] + "00" * 29 + "7fffff"   # tick word: 0x00..7fffff = 8388607 > int24 max? (=2^23-1 ok)
    assert abi.decode(log)[1]["tick"] == 8388607
    log["data"] = log["data"][:2 + 64 * 4] + "00" * 29 + "800000"      # 2^23 does not fit int24
    with pytest.raises(abi.DecodeError):
        abi.decode(log)
