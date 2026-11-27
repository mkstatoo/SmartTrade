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
 "verifier": "publicnode",
 "ranges": {
  "primary": 10,
  "verifier": 1
 },
 "ingest_run1": {
  "blocks": 150,
  "logs": 85112,
  "decoded": 77439,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26509507,
  "head": 26509657,
  "seconds": 44.0,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "range": [
  26509357,
  26509506
 ],
 "failover_switches": [],
 "decoded_by_kind": {
  "erc20_transfer": 72268,
  "uniswap_v2_swap": 1551,
  "uniswap_v3_swap": 3620
 },
 "decode_error_examples": [],
 "log_counts": {
  "stored": 85112,
  "independent": 85112,
  "only_stored": 0,
  "only_independent": 0
 },
 "ingest_run2": {
  "blocks": 20,
  "logs": 11650,
  "reorgs": 0,
  "next_block": 26509527
 },
 "noncanonical_blocks": 0,
 "passed": true
}
```
