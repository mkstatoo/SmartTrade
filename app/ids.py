"""Single canonical identity for chains, addresses and tokens (used by models, API, store, backtest).

EVM addresses are case-insensitive hex -> stored lower-case. Everything else (e.g. Solana base58) is case-sensitive
and is never altered. A value is treated as EVM when the chain is a known EVM chain OR the value starts with 0x
(the same predicate the PostgreSQL CHECK constraints use).
"""
EVM_CHAINS = frozenset({"ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche"})


def is_evm(chain: str, value: str) -> bool:
    return chain.lower() in EVM_CHAINS or value.startswith("0x")


def canonical_address(chain: str, value: str) -> str:
    return value.lower() if is_evm(chain, value) else value


def token_key(chain: str, token: str) -> str:
    return f"{chain.lower()}:{canonical_address(chain, token)}"
