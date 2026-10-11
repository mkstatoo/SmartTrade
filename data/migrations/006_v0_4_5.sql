-- v0.4.5 market layer: verified DEX pools, token metadata, transactions (tx.from), token transfers and derived wallet trades.
-- Every derived trade keeps its evidence and method version; rows are tied to a block hash so a reorg orphans them visibly.
CREATE TABLE IF NOT EXISTS chain_tokens (
    chain TEXT NOT NULL CHECK (chain ~ '^[a-z0-9_-]{1,32}$'),
    address TEXT NOT NULL CHECK (address ~ '^0x[0-9a-f]{40}$'),
    symbol TEXT NOT NULL CHECK (length(symbol) BETWEEN 1 AND 32),
    decimals INTEGER NOT NULL CHECK (decimals BETWEEN 0 AND 36),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chain, address)
);
CREATE TABLE IF NOT EXISTS chain_pools (
    chain TEXT NOT NULL CHECK (chain ~ '^[a-z0-9_-]{1,32}$'),
    pool TEXT NOT NULL CHECK (pool ~ '^0x[0-9a-f]{40}$'),
    kind TEXT NOT NULL CHECK (kind IN ('uniswap_v2','uniswap_v3')),
    factory TEXT NOT NULL CHECK (factory ~ '^0x[0-9a-f]{40}$'),
    token0 TEXT NOT NULL CHECK (token0 ~ '^0x[0-9a-f]{40}$'),
    token1 TEXT NOT NULL CHECK (token1 ~ '^0x[0-9a-f]{40}$'),
    fee INTEGER CHECK (fee IS NULL OR fee >= 0),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    discovery JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (chain, pool)
);
CREATE TABLE IF NOT EXISTS chain_txs (
    chain TEXT NOT NULL,
    tx_hash TEXT NOT NULL CHECK (tx_hash ~ '^0x[0-9a-f]{64}$'),
    block_hash TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    from_addr TEXT NOT NULL CHECK (from_addr ~ '^0x[0-9a-f]{40}$'),
    to_addr TEXT CHECK (to_addr IS NULL OR to_addr ~ '^0x[0-9a-f]{40}$'),
    status INTEGER NOT NULL CHECK (status IN (0,1)),
    gas_used NUMERIC NOT NULL CHECK (gas_used >= 0),
    effective_gas_price NUMERIC NOT NULL CHECK (effective_gas_price >= 0),
    source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 200),
    PRIMARY KEY (chain, block_hash, tx_hash),
    FOREIGN KEY (chain, block_hash) REFERENCES chain_blocks (chain, block_hash)
);
CREATE INDEX IF NOT EXISTS idx_chain_txs_from ON chain_txs (chain, from_addr);
CREATE TABLE IF NOT EXISTS chain_transfers (
    chain TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL CHECK (log_index >= 0),
    token TEXT NOT NULL CHECK (token ~ '^0x[0-9a-f]{40}$'),
    from_addr TEXT NOT NULL CHECK (from_addr ~ '^0x[0-9a-f]{40}$'),
    to_addr TEXT NOT NULL CHECK (to_addr ~ '^0x[0-9a-f]{40}$'),
    amount NUMERIC NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (chain, block_hash, tx_hash, log_index),
    FOREIGN KEY (chain, block_hash, tx_hash) REFERENCES chain_txs (chain, block_hash, tx_hash)
);
CREATE INDEX IF NOT EXISTS idx_chain_transfers_token ON chain_transfers (chain, token);
CREATE TABLE IF NOT EXISTS chain_trades (
    id BIGSERIAL PRIMARY KEY,
    chain TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    tx_hash TEXT NOT NULL,
    ts BIGINT NOT NULL CHECK (ts >= 0),
    wallet TEXT NOT NULL CHECK (wallet ~ '^0x[0-9a-f]{40}$'),
    token TEXT NOT NULL CHECK (token ~ '^0x[0-9a-f]{40}$'),
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty NUMERIC NOT NULL CHECK (qty > 0),
    usd NUMERIC NOT NULL CHECK (usd > 0),
    price_usd NUMERIC NOT NULL CHECK (price_usd > 0),
    gas_usd NUMERIC NOT NULL DEFAULT 0 CHECK (gas_usd >= 0),
    confidence TEXT NOT NULL CHECK (confidence IN ('confirmed','mismatch')),
    evidence JSONB NOT NULL,
    method_version INTEGER NOT NULL CHECK (method_version >= 1),
    FOREIGN KEY (chain, block_hash, tx_hash) REFERENCES chain_txs (chain, block_hash, tx_hash),
    CONSTRAINT uq_chain_trades_identity UNIQUE (chain, block_hash, tx_hash, wallet, token, method_version)
);
CREATE INDEX IF NOT EXISTS idx_chain_trades_wallet ON chain_trades (chain, wallet, block_number);
-- transactions whose swaps could not be turned into a wallet trade are recorded with the reason (never silently dropped)
CREATE TABLE IF NOT EXISTS chain_trade_skips (
    chain TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 60),
    method_version INTEGER NOT NULL CHECK (method_version >= 1),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (chain, block_hash, tx_hash, reason, method_version),
    FOREIGN KEY (chain, block_hash, tx_hash) REFERENCES chain_txs (chain, block_hash, tx_hash)
);
CREATE OR REPLACE VIEW chain_trades_canonical AS
    SELECT t.* FROM chain_trades t JOIN chain_blocks b ON b.chain = t.chain AND b.block_hash = t.block_hash WHERE b.canonical;
