# Live verification (real chain data)

## ethereum: PASS
```
{
 "chain": "ethereum",
 "checks": {
  "blocks_contiguous": true,
  "stored_parent_chain_linked": true,
  "block_hashes_match_independent_provider": true,
  "logs_identical_to_independent_provider": true,
  "resume_continues_without_duplicates": true
 },
 "primary": "drpc",
 "verifier": "private-2",
 "ranges": {
  "primary": 10,
  "verifier": 1
 },
 "ingest_run1": {
  "blocks": 150,
  "logs": 78551,
  "decoded": 77671,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26362423,
  "head": 26362573,
  "seconds": 37.1,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "range": [
  26362273,
  26362422
 ],
 "failover_switches": [],
 "decoded_by_kind": {
  "erc20_transfer": 75383,
  "uniswap_v3_swap": 1573,
  "uniswap_v2_swap": 715
 },
 "decode_error_examples": [],
 "log_counts": {
  "stored": 78551,
  "independent": 78551,
  "only_stored": 0,
  "only_independent": 0
 },
 "ingest_run2": {
  "blocks": 20,
  "logs": 13019,
  "reorgs": 0,
  "next_block": 26362443
 },
 "noncanonical_blocks": 0,
 "passed": true
}
```
