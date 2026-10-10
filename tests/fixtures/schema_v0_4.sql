CREATE TABLE IF NOT EXISTS tokens (
    chain TEXT NOT NULL, contract TEXT NOT NULL, symbol TEXT, decimals INT CHECK (decimals BETWEEN 0 AND 255),
    PRIMARY KEY(chain, contract)
);
CREATE TABLE IF NOT EXISTS wallets (
    chain TEXT NOT NULL, address TEXT NOT NULL, label TEXT, is_team BOOLEAN NOT NULL DEFAULT FALSE,
    is_router BOOLEAN NOT NULL DEFAULT FALSE, is_cex BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(chain,address)
);
CREATE TABLE IF NOT EXISTS wallet_events (
    id BIGSERIAL PRIMARY KEY, tx_hash TEXT NOT NULL, log_index BIGINT, wallet_chain TEXT NOT NULL, wallet_address TEXT NOT NULL,
    token_chain TEXT NOT NULL, token_contract TEXT NOT NULL, token_symbol TEXT, ts TIMESTAMPTZ NOT NULL,
    block_number BIGINT, block_hash TEXT, ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL','CEX_IN','CEX_OUT','TRANSFER')),
    usd_value NUMERIC CHECK(usd_value IS NULL OR usd_value >= 0), price NUMERIC CHECK(price IS NULL OR price > 0), liquidity_usd NUMERIC CHECK(liquidity_usd IS NULL OR liquidity_usd >= 0), source TEXT,
    FOREIGN KEY(wallet_chain,wallet_address) REFERENCES wallets(chain,address),
    FOREIGN KEY(token_chain,token_contract) REFERENCES tokens(chain,contract),
    UNIQUE(wallet_chain,tx_hash,log_index,wallet_address,side)
);
CREATE INDEX IF NOT EXISTS idx_events_token_ts ON wallet_events(token_chain,token_contract,ts);
CREATE INDEX IF NOT EXISTS idx_events_wallet_ts ON wallet_events(wallet_chain,wallet_address,ts);
CREATE TABLE IF NOT EXISTS price_bars (
    chain TEXT NOT NULL, token_contract TEXT NOT NULL, ts TIMESTAMPTZ NOT NULL, timeframe TEXT NOT NULL,
    open NUMERIC NOT NULL CHECK(open>0), high NUMERIC NOT NULL CHECK(high>0), low NUMERIC NOT NULL CHECK(low>0), close NUMERIC NOT NULL CHECK(close>0), volume_usd NUMERIC NOT NULL CHECK(volume_usd>=0),
    PRIMARY KEY(chain,token_contract,timeframe,ts), CHECK(low<=open AND low<=close AND high>=open AND high>=close)
);
CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY, chain TEXT NOT NULL, token_contract TEXT NOT NULL, ts TIMESTAMPTZ NOT NULL, stats_as_of_ts TIMESTAMPTZ NOT NULL,
    wallet_count INT NOT NULL CHECK(wallet_count>=0), score NUMERIC NOT NULL CHECK(score BETWEEN 0 AND 100), confidence NUMERIC NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    action TEXT NOT NULL CHECK(action IN ('WAIT','ENTER','EXIT')), reason JSONB
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id BIGSERIAL PRIMARY KEY, signal_id BIGINT REFERENCES signals(id), chain TEXT NOT NULL, token_contract TEXT NOT NULL, side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    ts TIMESTAMPTZ NOT NULL, price NUMERIC NOT NULL CHECK(price>0), qty NUMERIC NOT NULL CHECK(qty>0), notional_usd NUMERIC NOT NULL CHECK(notional_usd>0), status TEXT NOT NULL
);
