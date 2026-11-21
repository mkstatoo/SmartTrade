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
  "logs": 85501,
  "decoded": 79521,
  "decode_errors": 1,
  "reorgs": 0,
  "next_block": 26462601,
  "head": 26462751,
  "seconds": 70.1,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "range": [
  26462451,
  26462600
 ],
 "failover_switches": [],
 "decoded_by_kind": {
  "erc20_transfer": 74598,
  "uniswap_v3_swap": 3376,
  "uniswap_v2_swap": 1547
 },
 "decode_error_examples": [
  "Transfer needs 3 topics"
 ],
 "log_counts": {
  "stored": 85501,
  "independent": 85501,
  "only_stored": 0,
  "only_independent": 0
 },
 "ingest_run2": {
  "blocks": 20,
  "logs": 9550,
  "reorgs": 0,
  "next_block": 26462621
 },
 "noncanonical_blocks": 0,
 "passed": true
}
```
