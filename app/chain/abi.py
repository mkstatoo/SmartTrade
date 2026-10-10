"""Strict decoders for the log types the wallet-PnL pipeline needs. Raw logs are always stored first; decoding can be
re-run later (DECODER_VERSION) without re-fetching, and a log that does not fit is recorded as an error, never guessed.

Verified: topic hashes against keccak256 (tests), encodings against an independent encoder (tests, labelled fixtures).
NOT done here (needs on-chain context, e.g. eth_call token0/token1/decimals and tx.from): attributing a swap to a wallet
and pricing it in USD. A V2/V3 `Swap` log alone only describes the POOL's balance change."""
from __future__ import annotations

import re

DECODER_VERSION = 1
TOPIC_ERC20_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"   # Transfer(address,address,uint256)
TOPIC_V2_SWAP = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"          # Swap(address,uint256,uint256,uint256,uint256,address)
TOPIC_V3_SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"          # Swap(address,address,int256,int256,uint160,uint128,int24)
WATCHED_TOPICS = (TOPIC_ERC20_TRANSFER, TOPIC_V2_SWAP, TOPIC_V3_SWAP)
HEX32 = re.compile(r"^0x[0-9a-f]{64}$")
HEX20 = re.compile(r"^0x[0-9a-f]{40}$")


class DecodeError(ValueError):
    pass


def _data(log) -> bytes:
    d = log["data"]
    if not re.fullmatch(r"0x([0-9a-f]{2})*", d):
        raise DecodeError("data is not lower-case hex bytes")
    return bytes.fromhex(d[2:])


def _addr_from_topic(t: str) -> str:
    if not HEX32.match(t):
        raise DecodeError("topic is not a 32-byte hex word")
    if t[2:26] != "0" * 24:
        raise DecodeError("indexed address has non-zero padding")
    return "0x" + t[26:]


def _word(b: bytes, i: int) -> bytes:
    return b[32 * i:32 * (i + 1)]


def _uint(b: bytes, i: int, bits: int = 256) -> int:
    v = int.from_bytes(_word(b, i), "big")
    if v >= 1 << bits:
        raise DecodeError(f"value does not fit uint{bits}")
    return v


def _int(b: bytes, i: int, bits: int) -> int:
    raw = int.from_bytes(_word(b, i), "big", signed=True)          # ABI pads signed values by sign extension
    if not -(1 << (bits - 1)) <= raw < (1 << (bits - 1)):
        raise DecodeError(f"value does not fit int{bits}")
    return raw


def decode(log: dict):
    """Returns (kind, fields) for a recognised log, None for logs we do not decode (including ERC-721 Transfers,
    which share the ERC-20 signature but have 4 topics). Raises DecodeError for a recognised signature with a malformed body."""
    topics = log["topics"]
    if not topics:
        return None
    t0, data = topics[0], None
    if t0 == TOPIC_ERC20_TRANSFER:
        if len(topics) == 4:
            return None
        if len(topics) != 3:
            raise DecodeError("Transfer needs 3 topics")
        data = _data(log)
        if len(data) != 32:
            raise DecodeError("Transfer data must be 32 bytes")
        return "erc20_transfer", {"token": log["address"], "from": _addr_from_topic(topics[1]),
                                  "to": _addr_from_topic(topics[2]), "amount": str(_uint(data, 0))}
    if t0 == TOPIC_V2_SWAP:
        if len(topics) != 3:
            raise DecodeError("V2 Swap needs 3 topics")
        data = _data(log)
        if len(data) != 128:
            raise DecodeError("V2 Swap data must be 128 bytes")
        return "uniswap_v2_swap", {"pool": log["address"], "sender": _addr_from_topic(topics[1]),
                                   "to": _addr_from_topic(topics[2]), "amount0_in": str(_uint(data, 0)),
                                   "amount1_in": str(_uint(data, 1)), "amount0_out": str(_uint(data, 2)),
                                   "amount1_out": str(_uint(data, 3))}
    if t0 == TOPIC_V3_SWAP:
        if len(topics) != 3:
            raise DecodeError("V3 Swap needs 3 topics")
        data = _data(log)
        if len(data) != 160:
            raise DecodeError("V3 Swap data must be 160 bytes")
        return "uniswap_v3_swap", {"pool": log["address"], "sender": _addr_from_topic(topics[1]),
                                   "recipient": _addr_from_topic(topics[2]), "amount0": str(_int(data, 0, 256)),
                                   "amount1": str(_int(data, 1, 256)), "sqrt_price_x96": str(_uint(data, 2, 160)),
                                   "liquidity": str(_uint(data, 3, 128)), "tick": _int(data, 4, 24)}
    return None
