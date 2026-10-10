-- v0.4.4: provenance of the exit price on closed paper trades (stale-price time exits are labelled, never disguised).
ALTER TABLE paper_closed_trades ADD COLUMN IF NOT EXISTS price_basis TEXT NOT NULL DEFAULT 'bar';
ALTER TABLE paper_closed_trades ADD COLUMN IF NOT EXISTS price_age_sec BIGINT;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_closed_price_basis_ck') THEN
    ALTER TABLE paper_closed_trades ADD CONSTRAINT paper_closed_price_basis_ck CHECK (price_basis IN ('bar','stale_last_close'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_closed_price_age_ck') THEN
    ALTER TABLE paper_closed_trades ADD CONSTRAINT paper_closed_price_age_ck CHECK (price_age_sec IS NULL OR price_age_sec >= 0);
  END IF;
END $$;

-- v0.4.4 on-chain raw layer: every row keeps its provenance (chain, block hash/number, tx hash, log index, RPC source).
-- Orphaned blocks are kept with canonical=false (never deleted) so a reorg is auditable.
CREATE TABLE IF NOT EXISTS chain_blocks (
    chain TEXT NOT NULL CHECK (chain ~ '^[a-z0-9_-]{1,32}$'),
    block_hash TEXT NOT NULL CHECK (block_hash ~ '^0x[0-9a-f]{64}$'),
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    parent_hash TEXT NOT NULL CHECK (parent_hash ~ '^0x[0-9a-f]{64}$'),
    block_ts BIGINT NOT NULL CHECK (block_ts >= 0),
    canonical BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 200),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chain, block_hash)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chain_blocks_canonical ON chain_blocks (chain, block_number) WHERE canonical;

CREATE TABLE IF NOT EXISTS chain_logs (
    id BIGSERIAL PRIMARY KEY,
    chain TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    tx_hash TEXT NOT NULL CHECK (tx_hash ~ '^0x[0-9a-f]{64}$'),
    log_index INTEGER NOT NULL CHECK (log_index >= 0),
    address TEXT NOT NULL CHECK (address ~ '^0x[0-9a-f]{40}$'),
    topic0 TEXT NOT NULL CHECK (topic0 ~ '^0x[0-9a-f]{64}$'),
    topics TEXT[] NOT NULL CHECK (cardinality(topics) BETWEEN 1 AND 4),
    data TEXT NOT NULL CHECK (data ~ '^0x([0-9a-f]{2})*$'),
    FOREIGN KEY (chain, block_hash) REFERENCES chain_blocks (chain, block_hash),
    CONSTRAINT uq_chain_logs_identity UNIQUE (chain, block_hash, tx_hash, log_index)
);
CREATE INDEX IF NOT EXISTS idx_chain_logs_block ON chain_logs (chain, block_number);
CREATE INDEX IF NOT EXISTS idx_chain_logs_tx ON chain_logs (chain, tx_hash);

CREATE TABLE IF NOT EXISTS chain_decoded (
    log_id BIGINT NOT NULL REFERENCES chain_logs (id) ON DELETE CASCADE,
    decoder_version INTEGER NOT NULL CHECK (decoder_version >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('erc20_transfer','uniswap_v2_swap','uniswap_v3_swap')),
    fields JSONB NOT NULL,
    PRIMARY KEY (log_id, decoder_version)
);
CREATE TABLE IF NOT EXISTS chain_decode_errors (
    log_id BIGINT NOT NULL REFERENCES chain_logs (id) ON DELETE CASCADE,
    decoder_version INTEGER NOT NULL CHECK (decoder_version >= 1),
    error TEXT NOT NULL,
    PRIMARY KEY (log_id, decoder_version)
);
CREATE TABLE IF NOT EXISTS chain_cursor (
    chain TEXT PRIMARY KEY CHECK (chain ~ '^[a-z0-9_-]{1,32}$'),
    next_block BIGINT NOT NULL CHECK (next_block >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chain_reorgs (
    id BIGSERIAL PRIMARY KEY,
    chain TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fork_block BIGINT NOT NULL CHECK (fork_block >= 0),
    depth INTEGER NOT NULL CHECK (depth >= 1),
    orphaned_blocks INTEGER NOT NULL CHECK (orphaned_blocks >= 0)
);
CREATE OR REPLACE VIEW chain_logs_canonical AS
    SELECT l.*, b.block_ts, b.source
    FROM chain_logs l JOIN chain_blocks b ON b.chain = l.chain AND b.block_hash = l.block_hash
    WHERE b.canonical;
