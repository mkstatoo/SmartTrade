-- v0.4.3: time-based exit columns + one canonical token identity (EVM contracts lower-case), no silent data loss.
-- One transaction (single multi-statement query); safe to run again.

-- 1. time-exit state of open paper positions (existing open positions keep NULL = no time exit) --------------------
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS max_hold_sec BIGINT;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS expires_ts BIGINT;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_positions_hold_ck') THEN
    ALTER TABLE paper_positions ADD CONSTRAINT paper_positions_hold_ck CHECK (max_hold_sec IS NULL OR max_hold_sec > 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_positions_expires_ck') THEN
    ALTER TABLE paper_positions ADD CONSTRAINT paper_positions_expires_ck CHECK (expires_ts IS NULL OR expires_ts >= entry_ts);
  END IF;
END $$;

-- 2. canonical token identity: merge mixed-case EVM contracts into the lower-case row ---------------------------------
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT chain, contract, lower(contract) AS lo FROM tokens
           WHERE contract <> lower(contract)
             AND (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR contract LIKE '0x%')
  LOOP
    INSERT INTO tokens (chain, contract, symbol, decimals)
      SELECT chain, r.lo, symbol, decimals FROM tokens WHERE chain = r.chain AND contract = r.contract
    ON CONFLICT (chain, contract) DO UPDATE SET symbol = COALESCE(tokens.symbol, EXCLUDED.symbol),
                                               decimals = COALESCE(tokens.decimals, EXCLUDED.decimals);
    UPDATE wallet_events SET token_contract = r.lo WHERE token_chain = r.chain AND token_contract = r.contract;
    UPDATE signals       SET token_contract = r.lo WHERE chain = r.chain AND token_contract = r.contract;
    UPDATE paper_trades  SET token_contract = r.lo WHERE chain = r.chain AND token_contract = r.contract;
    DELETE FROM tokens WHERE chain = r.chain AND contract = r.contract;
  END LOOP;

  -- price_bars has no FK to tokens: normalise independently; a bar that already exists under the lower-case id is quarantined
  INSERT INTO legacy_quarantine (source_table, reason, row)
    SELECT 'price_bars', 'duplicate_after_token_normalization', to_jsonb(b) FROM price_bars b
     WHERE b.token_contract <> lower(b.token_contract)
       AND (b.chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR b.token_contract LIKE '0x%')
       AND EXISTS (SELECT 1 FROM price_bars x WHERE x.chain = b.chain AND x.token_contract = lower(b.token_contract)
                     AND x.timeframe = b.timeframe AND x.ts = b.ts);
  DELETE FROM price_bars b
   WHERE b.token_contract <> lower(b.token_contract)
     AND (b.chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR b.token_contract LIKE '0x%')
     AND EXISTS (SELECT 1 FROM price_bars x WHERE x.chain = b.chain AND x.token_contract = lower(b.token_contract)
                   AND x.timeframe = b.timeframe AND x.ts = b.ts);
  UPDATE price_bars SET token_contract = lower(token_contract)
   WHERE token_contract <> lower(token_contract) AND (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR token_contract LIKE '0x%');
END $$;

ALTER TABLE tokens DROP CONSTRAINT IF EXISTS tokens_evm_lower_ck;
ALTER TABLE tokens ADD CONSTRAINT tokens_evm_lower_ck CHECK (
  NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR contract LIKE '0x%') OR contract = lower(contract));
ALTER TABLE price_bars DROP CONSTRAINT IF EXISTS price_bars_evm_lower_ck;
ALTER TABLE price_bars ADD CONSTRAINT price_bars_evm_lower_ck CHECK (
  NOT (chain IN ('ethereum','base','arbitrum','optimism','polygon','bsc','avalanche') OR token_contract LIKE '0x%') OR token_contract = lower(token_contract));
