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
 "verifier": "private-1",
 "ranges": {
  "primary": 10,
  "verifier": 1
 },
 "ingest_run1": {
  "blocks": 150,
  "logs": 63497,
  "decoded": 62911,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26322434,
  "head": 26322584,
  "seconds": 104.0,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "range": [
  26322284,
  26322433
 ],
 "failover_switches": [],
 "decoded_by_kind": {
  "erc20_transfer": 59889,
  "uniswap_v3_swap": 2024,
  "uniswap_v2_swap": 998
 },
 "decode_error_examples": [],
 "log_counts": {
  "stored": 63497,
  "independent": 63497,
  "only_stored": 0,
  "only_independent": 0
 },
 "ingest_run2": {
  "blocks": 20,
  "logs": 7883,
  "reorgs": 0,
  "next_block": 26322454
 },
 "noncanonical_blocks": 0,
 "passed": true
}
```
