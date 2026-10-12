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
  "logs": 102014,
  "decoded": 97948,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26178617,
  "head": 26178767,
  "seconds": 116.4,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "range": [
  26178467,
  26178616
 ],
 "failover_switches": [],
 "decoded_by_kind": {
  "erc20_transfer": 94133,
  "uniswap_v3_swap": 2795,
  "uniswap_v2_swap": 1020
 },
 "decode_error_examples": [],
 "log_counts": {
  "stored": 102014,
  "independent": 102014,
  "only_stored": 0,
  "only_independent": 0
 },
 "ingest_run2": {
  "blocks": 20,
  "logs": 18248,
  "reorgs": 0,
  "next_block": 26178637
 },
 "noncanonical_blocks": 0,
 "passed": true
}
```
## base: SKIPPED
```
{
 "chain": "base",
 "checks": {},
 "primary": "publicnode",
 "verifier": null,
 "skipped": "need two agreeing usable providers (primary + independent verifier)"
}
```
