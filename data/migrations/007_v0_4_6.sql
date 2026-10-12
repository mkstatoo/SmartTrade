-- v0.4.6: OP-stack chains (Base) charge a separate L1 data fee that is NOT part of gasUsed * effectiveGasPrice
ALTER TABLE chain_txs ADD COLUMN IF NOT EXISTS l1_fee NUMERIC NOT NULL DEFAULT 0 CHECK (l1_fee >= 0);
