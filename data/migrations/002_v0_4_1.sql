-- v0.4.1 additive/idempotent migration; inspect and normalize legacy addresses before applying.
CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='wallets_evm_lower_ck') THEN ALTER TABLE wallets ADD CONSTRAINT wallets_evm_lower_ck CHECK (chain='solana' OR address=lower(address)) NOT VALID; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='signals_asof_ck') THEN ALTER TABLE signals ADD CONSTRAINT signals_asof_ck CHECK (stats_as_of_ts <= ts) NOT VALID; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='signals_token_fk') THEN ALTER TABLE signals ADD CONSTRAINT signals_token_fk FOREIGN KEY(chain,token_contract) REFERENCES tokens(chain,contract) NOT VALID; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='paper_trades_token_fk') THEN ALTER TABLE paper_trades ADD CONSTRAINT paper_trades_token_fk FOREIGN KEY(chain,token_contract) REFERENCES tokens(chain,contract) NOT VALID; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='paper_trades_status_ck') THEN ALTER TABLE paper_trades ADD CONSTRAINT paper_trades_status_ck CHECK(status IN ('OPEN','CLOSED','REJECTED')) NOT VALID; END IF;
END $$;
ALTER TABLE wallet_events ALTER COLUMN log_index DROP NOT NULL;
ALTER TABLE wallet_events DROP CONSTRAINT IF EXISTS wallet_events_wallet_chain_tx_hash_log_index_wallet_address_key;
ALTER TABLE wallet_events DROP CONSTRAINT IF EXISTS wallet_events_wallet_chain_tx_hash_log_index_wallet_address_side_key;
ALTER TABLE wallet_events DROP CONSTRAINT IF EXISTS wallet_events_event_key;
ALTER TABLE wallet_events ADD CONSTRAINT wallet_events_event_key UNIQUE NULLS NOT DISTINCT(wallet_chain,tx_hash,log_index,wallet_address,side);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS fee_usd NUMERIC NOT NULL DEFAULT 0 CHECK(fee_usd>=0);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS slippage_usd NUMERIC NOT NULL DEFAULT 0 CHECK(slippage_usd>=0);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS gas_usd NUMERIC NOT NULL DEFAULT 0 CHECK(gas_usd>=0);
INSERT INTO schema_migrations(version) VALUES ('002_v0_4_1') ON CONFLICT DO NOTHING;
