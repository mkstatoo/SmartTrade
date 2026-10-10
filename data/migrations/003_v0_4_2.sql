-- v0.4.2: converge every legacy database to the schema in data/schema.sql, with NO silent data loss.
-- Rows that violate a constraint the new schema enforces are copied to legacy_quarantine and then removed.
-- Runs as one transaction (single multi-statement query) and is safe to run again.

CREATE TABLE IF NOT EXISTS legacy_quarantine (
    id BIGSERIAL PRIMARY KEY, source_table TEXT NOT NULL, reason TEXT NOT NULL, row JSONB NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 1. EVM wallet addresses: merge mixed-case rows into the lower-case row -------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT chain, address, lower(address) AS lo FROM wallets
           WHERE address <> lower(address)
             AND (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR address LIKE '0x%')
  LOOP
    INSERT INTO wallets (chain, address, label, is_team, is_router, is_cex, created_at)
      SELECT chain, r.lo, label, is_team, is_router, is_cex, created_at FROM wallets WHERE chain = r.chain AND address = r.address
    ON CONFLICT (chain, address) DO UPDATE SET
      label = COALESCE(wallets.label, EXCLUDED.label), is_team = wallets.is_team OR EXCLUDED.is_team,
      is_router = wallets.is_router OR EXCLUDED.is_router, is_cex = wallets.is_cex OR EXCLUDED.is_cex;
    UPDATE wallet_events e SET wallet_address = r.lo
     WHERE e.wallet_chain = r.chain AND e.wallet_address = r.address
       AND NOT EXISTS (SELECT 1 FROM wallet_events x WHERE x.wallet_chain = e.wallet_chain AND x.tx_hash = e.tx_hash
                         AND x.log_index IS NOT DISTINCT FROM e.log_index AND x.wallet_address = r.lo AND x.side = e.side);
    INSERT INTO legacy_quarantine (source_table, reason, row)
      SELECT 'wallet_events', 'duplicate_after_address_normalization', to_jsonb(e) FROM wallet_events e
       WHERE e.wallet_chain = r.chain AND e.wallet_address = r.address;
    DELETE FROM wallet_events WHERE wallet_chain = r.chain AND wallet_address = r.address;
    DELETE FROM wallets WHERE chain = r.chain AND address = r.address;
  END LOOP;
END $$;

-- 2. referenced tokens must exist (registering a contract loses nothing) ---------------------------------------
INSERT INTO tokens (chain, contract) SELECT DISTINCT chain, token_contract FROM signals ON CONFLICT DO NOTHING;
INSERT INTO tokens (chain, contract) SELECT DISTINCT chain, token_contract FROM paper_trades ON CONFLICT DO NOTHING;

-- 3. quarantine rows the stricter schema cannot hold ------------------------------------------------------------
DO $$
BEGIN
  CREATE TEMP TABLE _bad_sig ON COMMIT DROP AS
    SELECT id, CASE WHEN stats_as_of_ts > ts THEN 'stats_as_of_after_signal_ts' ELSE 'negative_wallet_count' END AS why
      FROM signals WHERE stats_as_of_ts > ts OR wallet_count < 0;
  UPDATE paper_trades SET signal_id = NULL WHERE signal_id IN (SELECT id FROM _bad_sig);
  INSERT INTO legacy_quarantine (source_table, reason, row)
    SELECT 'signals', b.why, to_jsonb(s) FROM signals s JOIN _bad_sig b ON b.id = s.id;
  DELETE FROM signals WHERE id IN (SELECT id FROM _bad_sig);

  INSERT INTO legacy_quarantine (source_table, reason, row)
    SELECT 'paper_trades', 'invalid_status', to_jsonb(t) FROM paper_trades t WHERE status NOT IN ('OPEN','CLOSED','REJECTED');
  DELETE FROM paper_trades WHERE status NOT IN ('OPEN','CLOSED','REJECTED');

  INSERT INTO legacy_quarantine (source_table, reason, row)
    SELECT 'price_bars', 'null_volume_or_nonpositive_price', to_jsonb(b) FROM price_bars b
     WHERE volume_usd IS NULL OR volume_usd < 0 OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0;
  DELETE FROM price_bars WHERE volume_usd IS NULL OR volume_usd < 0 OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0;
END $$;

-- 4. converge structure with schema.sql ---------------------------------------------------------------------------
ALTER TABLE wallets DROP CONSTRAINT IF EXISTS wallets_evm_lower_ck;
ALTER TABLE wallets ADD CONSTRAINT wallets_evm_lower_ck CHECK (
  NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR address LIKE '0x%')
  OR address = lower(address));

ALTER TABLE price_bars ALTER COLUMN volume_usd SET NOT NULL;
ALTER TABLE price_bars ALTER COLUMN timeframe DROP DEFAULT;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'price_bars_open_ck') THEN
    ALTER TABLE price_bars ADD CONSTRAINT price_bars_open_ck CHECK (open > 0),
      ADD CONSTRAINT price_bars_high_ck CHECK (high > 0), ADD CONSTRAINT price_bars_low_ck CHECK (low > 0),
      ADD CONSTRAINT price_bars_close_ck CHECK (close > 0), ADD CONSTRAINT price_bars_volume_ck CHECK (volume_usd >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'signals_wallet_count_ck') THEN
    ALTER TABLE signals ADD CONSTRAINT signals_wallet_count_ck CHECK (wallet_count >= 0);
  END IF;
END $$;
ALTER TABLE signals ALTER COLUMN ts DROP DEFAULT;
ALTER TABLE paper_trades ALTER COLUMN ts DROP DEFAULT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS portfolio_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_paper_trades_portfolio ON paper_trades (portfolio_id, id);

-- 5. durable paper portfolio tables (identical to schema.sql) -------------------------------------------------------
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
    PRIMARY KEY (portfolio_id, token_key)
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
    CHECK (exit_ts >= entry_ts)
);
CREATE INDEX IF NOT EXISTS idx_paper_closed_portfolio ON paper_closed_trades (portfolio_id, id);

-- 6. every constraint that 002 left NOT VALID is validated now that the data is clean ------------------------------
DO $$
DECLARE c RECORD;
BEGIN
  FOR c IN SELECT conrelid::regclass AS tbl, conname FROM pg_constraint
            WHERE NOT convalidated AND connamespace = 'public'::regnamespace
  LOOP
    EXECUTE format('ALTER TABLE %s VALIDATE CONSTRAINT %I', c.tbl, c.conname);
  END LOOP;
END $$;
