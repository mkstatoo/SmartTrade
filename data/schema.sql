-- Smart Copy Trading — FULL CURRENT SCHEMA (v0.4.4).
-- Applies to a FRESH database only (all statements are idempotent). Existing databases are upgraded with
-- `python -m app.migrate`, which applies data/migrations/* in order. tests/test_postgres.py proves that a fresh
-- install and a migrated legacy database end up with the same catalog (columns, constraints, indexes).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tokens (
    chain TEXT NOT NULL, contract TEXT NOT NULL, symbol TEXT,
    decimals INT CHECK (decimals BETWEEN 0 AND 255),
    PRIMARY KEY (chain, contract),
    -- mirrors app.ids.canonical_address: EVM contracts are stored lower-case, other chains keep their case
    CHECK (NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR contract LIKE '0x%')
           OR contract = lower(contract))
);

CREATE TABLE IF NOT EXISTS wallets (
    chain TEXT NOT NULL, address TEXT NOT NULL, label TEXT,
    is_team BOOLEAN NOT NULL DEFAULT FALSE, is_router BOOLEAN NOT NULL DEFAULT FALSE, is_cex BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chain, address),
    -- mirrors app.models.normalize_address: EVM addresses are stored lower-case, other chains keep their case
    CHECK (NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR address LIKE '0x%')
           OR address = lower(address))
);

CREATE TABLE IF NOT EXISTS wallet_events (
    id BIGSERIAL PRIMARY KEY, tx_hash TEXT NOT NULL, log_index BIGINT,
    wallet_chain TEXT NOT NULL, wallet_address TEXT NOT NULL,
    token_chain TEXT NOT NULL, token_contract TEXT NOT NULL, token_symbol TEXT,
    ts TIMESTAMPTZ NOT NULL, block_number BIGINT, block_hash TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL','CEX_IN','CEX_OUT','TRANSFER')),
    usd_value NUMERIC CHECK (usd_value IS NULL OR usd_value >= 0),
    price NUMERIC CHECK (price IS NULL OR price > 0),
    liquidity_usd NUMERIC CHECK (liquidity_usd IS NULL OR liquidity_usd >= 0),
    source TEXT,
    FOREIGN KEY (wallet_chain, wallet_address) REFERENCES wallets (chain, address),
    FOREIGN KEY (token_chain, token_contract) REFERENCES tokens (chain, contract),
    UNIQUE NULLS NOT DISTINCT (wallet_chain, tx_hash, log_index, wallet_address, side)
);
CREATE INDEX IF NOT EXISTS idx_events_token_ts ON wallet_events (token_chain, token_contract, ts);
CREATE INDEX IF NOT EXISTS idx_events_wallet_ts ON wallet_events (wallet_chain, wallet_address, ts);

CREATE TABLE IF NOT EXISTS price_bars (
    chain TEXT NOT NULL, token_contract TEXT NOT NULL, ts TIMESTAMPTZ NOT NULL, timeframe TEXT NOT NULL,
    open NUMERIC NOT NULL CHECK (open > 0), high NUMERIC NOT NULL CHECK (high > 0),
    low NUMERIC NOT NULL CHECK (low > 0), close NUMERIC NOT NULL CHECK (close > 0),
    volume_usd NUMERIC NOT NULL CHECK (volume_usd >= 0),
    PRIMARY KEY (chain, token_contract, timeframe, ts),
    CHECK (low <= open AND low <= close AND high >= open AND high >= close),
    CHECK (NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR token_contract LIKE '0x%')
           OR token_contract = lower(token_contract))
);

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY, chain TEXT NOT NULL, token_contract TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL, stats_as_of_ts TIMESTAMPTZ NOT NULL,
    wallet_count INT NOT NULL CHECK (wallet_count >= 0),
    score NUMERIC NOT NULL CHECK (score BETWEEN 0 AND 100),
    confidence NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    action TEXT NOT NULL CHECK (action IN ('WAIT','ENTER','EXIT')),
    reason JSONB,
    FOREIGN KEY (chain, token_contract) REFERENCES tokens (chain, contract),
    CHECK (stats_as_of_ts <= ts)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id BIGSERIAL PRIMARY KEY, signal_id BIGINT REFERENCES signals (id),
    chain TEXT NOT NULL, token_contract TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')), ts TIMESTAMPTZ NOT NULL,
    price NUMERIC NOT NULL CHECK (price > 0), qty NUMERIC NOT NULL CHECK (qty > 0),
    notional_usd NUMERIC NOT NULL CHECK (notional_usd > 0),
    status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED','REJECTED')),
    fee_usd NUMERIC NOT NULL DEFAULT 0 CHECK (fee_usd >= 0),
    slippage_usd NUMERIC NOT NULL DEFAULT 0 CHECK (slippage_usd >= 0),
    gas_usd NUMERIC NOT NULL DEFAULT 0 CHECK (gas_usd >= 0),
    portfolio_id TEXT NOT NULL DEFAULT 'default',
    FOREIGN KEY (chain, token_contract) REFERENCES tokens (chain, contract)
);
CREATE INDEX IF NOT EXISTS idx_paper_trades_portfolio ON paper_trades (portfolio_id, id);

-- ---------------------------------------------------------------- durable paper portfolio (v0.4.2)
CREATE TABLE IF NOT EXISTS paper_portfolios (
    portfolio_id TEXT PRIMARY KEY,
    initial_cash_usd NUMERIC NOT NULL CHECK (initial_cash_usd > 0),
    cash_usd NUMERIC NOT NULL,
    realized_pnl_usd NUMERIC NOT NULL DEFAULT 0,
    peak_equity_usd NUMERIC NOT NULL CHECK (peak_equity_usd > 0),
    max_drawdown_pct NUMERIC NOT NULL DEFAULT 0 CHECK (max_drawdown_pct BETWEEN 0 AND 100),
    now_ts BIGINT NOT NULL DEFAULT 0 CHECK (now_ts >= 0),
    slippage_bps NUMERIC NOT NULL CHECK (slippage_bps >= 0 AND slippage_bps < 10000),
    fee_bps NUMERIC NOT NULL CHECK (fee_bps >= 0),
    gas_usd NUMERIC NOT NULL CHECK (gas_usd >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_positions (
    portfolio_id TEXT NOT NULL REFERENCES paper_portfolios (portfolio_id) ON DELETE CASCADE,
    token_key TEXT NOT NULL,
    qty NUMERIC NOT NULL CHECK (qty > 0), entry NUMERIC NOT NULL CHECK (entry > 0),
    cost NUMERIC NOT NULL CHECK (cost > 0), notional NUMERIC NOT NULL CHECK (notional > 0),
    entry_fee_usd NUMERIC NOT NULL CHECK (entry_fee_usd >= 0), entry_gas_usd NUMERIC NOT NULL CHECK (entry_gas_usd >= 0),
    reference_price NUMERIC NOT NULL CHECK (reference_price > 0),
    fee_bps NUMERIC NOT NULL CHECK (fee_bps >= 0), slippage_bps NUMERIC NOT NULL CHECK (slippage_bps >= 0),
    gas_usd NUMERIC NOT NULL CHECK (gas_usd >= 0),
    target_return_pct NUMERIC CHECK (target_return_pct IS NULL OR target_return_pct > 0),
    stop_loss_pct NUMERIC CHECK (stop_loss_pct IS NULL OR stop_loss_pct > 0),
    entry_ts BIGINT NOT NULL CHECK (entry_ts >= 0), signal_id BIGINT REFERENCES signals (id),
    max_hold_sec BIGINT CHECK (max_hold_sec IS NULL OR max_hold_sec > 0),
    expires_ts BIGINT,
    PRIMARY KEY (portfolio_id, token_key),
    CHECK (expires_ts IS NULL OR expires_ts >= entry_ts)
);

CREATE TABLE IF NOT EXISTS paper_price_book (
    portfolio_id TEXT NOT NULL REFERENCES paper_portfolios (portfolio_id) ON DELETE CASCADE,
    token_key TEXT NOT NULL, price NUMERIC NOT NULL CHECK (price > 0),
    price_ts BIGINT NOT NULL CHECK (price_ts >= 0), last_bar_ts BIGINT NOT NULL CHECK (last_bar_ts >= 0),
    PRIMARY KEY (portfolio_id, token_key)
);

CREATE TABLE IF NOT EXISTS paper_cooldowns (
    portfolio_id TEXT NOT NULL REFERENCES paper_portfolios (portfolio_id) ON DELETE CASCADE,
    token_key TEXT NOT NULL, until_ts BIGINT NOT NULL CHECK (until_ts >= 0),
    PRIMARY KEY (portfolio_id, token_key)
);

CREATE TABLE IF NOT EXISTS paper_closed_trades (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES paper_portfolios (portfolio_id) ON DELETE CASCADE,
    token_key TEXT NOT NULL, entry NUMERIC NOT NULL CHECK (entry > 0), exit_price NUMERIC NOT NULL CHECK (exit_price > 0),
    market_level NUMERIC NOT NULL CHECK (market_level > 0), qty NUMERIC NOT NULL CHECK (qty > 0),
    cost NUMERIC NOT NULL CHECK (cost > 0), pnl_usd NUMERIC NOT NULL,
    exit_fee_usd NUMERIC NOT NULL CHECK (exit_fee_usd >= 0), exit_gas_usd NUMERIC NOT NULL CHECK (exit_gas_usd >= 0),
    reason TEXT NOT NULL CHECK (reason IN ('stop','target','time','manual','risk')),
    entry_ts BIGINT NOT NULL, exit_ts BIGINT NOT NULL, signal_id BIGINT REFERENCES signals (id),
    price_basis TEXT NOT NULL DEFAULT 'bar' CHECK (price_basis IN ('bar','stale_last_close')),
    price_age_sec BIGINT CHECK (price_age_sec IS NULL OR price_age_sec >= 0),
    CHECK (exit_ts >= entry_ts)
);
CREATE INDEX IF NOT EXISTS idx_paper_closed_portfolio ON paper_closed_trades (portfolio_id, id);

-- rows that a migration could not keep (they violated a constraint the new schema enforces); nothing is silently dropped
CREATE TABLE IF NOT EXISTS legacy_quarantine (
    id BIGSERIAL PRIMARY KEY, source_table TEXT NOT NULL, reason TEXT NOT NULL, row JSONB NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

INSERT INTO schema_migrations (version) VALUES ('001_v03_to_v04'), ('002_v0_4_1'), ('003_v0_4_2'), ('004_v0_4_3'), ('005_v0_4_4'), ('006_v0_4_5')
ON CONFLICT DO NOTHING;
