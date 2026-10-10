CREATE TABLE IF NOT EXISTS wallets (
    chain TEXT NOT NULL,
    address TEXT NOT NULL,
    label TEXT,
    is_team BOOLEAN NOT NULL DEFAULT FALSE,
    is_router BOOLEAN NOT NULL DEFAULT FALSE,
    is_cex BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chain, address)
);

CREATE TABLE IF NOT EXISTS wallet_events (
    id BIGSERIAL PRIMARY KEY,
    tx_hash TEXT NOT NULL,
    log_index BIGINT NOT NULL DEFAULT 0,
    wallet_chain TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    token_chain TEXT NOT NULL,
    token_contract TEXT NOT NULL,
    token_symbol TEXT,
    ts TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL','CEX_IN','CEX_OUT','TRANSFER')),
    usd_value NUMERIC,
    price NUMERIC,
    liquidity_usd NUMERIC,
    source TEXT,
    UNIQUE (tx_hash, log_index),
    FOREIGN KEY (wallet_chain, wallet_address) REFERENCES wallets(chain, address)
);

CREATE INDEX IF NOT EXISTS idx_events_token_ts ON wallet_events(token_chain, token_contract, ts);
CREATE INDEX IF NOT EXISTS idx_events_wallet_ts ON wallet_events(wallet_chain, wallet_address, ts);

CREATE TABLE IF NOT EXISTS price_bars (
    chain TEXT NOT NULL,
    token_contract TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC NOT NULL, high NUMERIC NOT NULL, low NUMERIC NOT NULL, close NUMERIC NOT NULL,
    volume_usd NUMERIC,
    PRIMARY KEY(chain, token_contract, ts),
    CHECK (low <= open AND low <= close AND high >= open AND high >= close)
);

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    chain TEXT NOT NULL,
    token_contract TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    wallet_count INT NOT NULL,
    score NUMERIC NOT NULL,
    confidence NUMERIC NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('WAIT','ENTER','EXIT')),
    reason JSONB
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES signals(id),
    chain TEXT NOT NULL,
    token_contract TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    price NUMERIC NOT NULL,
    qty NUMERIC NOT NULL,
    notional_usd NUMERIC NOT NULL,
    status TEXT NOT NULL
);
