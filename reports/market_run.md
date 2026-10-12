# Wallet attribution on real Ethereum data

run at 2026-10-12 20:27:52 UTC. Everything below is a measurement of THIS run only.

- **window blocks (discovery + watch)**: 300 + 3600
- **pools watched**: 33
- **receipts stored / errors / inconsistent**: 31722 / 0 / 0
- **trades (confirmed / mismatch)**: 9042 (8728 / 314)
- **share of swap txs that became a trade**: 0.6077
- **chainlink check**: pass
- **second provider check**: True
- **balance-state check**: pass
- **cross-pool price deviation (median / max %)**: 0.072403918775052 / 0.8103917596535979
- **wallets with a confirmed trade**: 2914
- **integrity**: no integrity problem found by the checks above

```json
{
 "at_utc": "2026-10-12 20:27:52",
 "chain": "ethereum",
 "steps": {
  "ingest_discovery": {
   "ok": true,
   "seconds": 90.6
  },
  "discover_pools": {
   "ok": true,
   "seconds": 364.4
  },
  "ingest_watch": {
   "ok": true,
   "seconds": 1022.3
  },
  "ingest_fresh_tail": {
   "ok": true,
   "seconds": 33.6
  },
  "chainlink_check": {
   "ok": true,
   "seconds": 1.6
  },
  "collect_tail_receipts": {
   "ok": true,
   "seconds": 35.7
  },
  "derive_tail": {
   "ok": true,
   "seconds": 1.0
  },
  "state_check": {
   "ok": true,
   "seconds": 25.4
  },
  "collect_receipts": {
   "ok": true,
   "seconds": 1857.8
  },
  "derive_trades": {
   "ok": true,
   "seconds": 12.2
  },
  "second_provider_check": {
   "ok": true,
   "seconds": 9.1
  },
  "cross_pool_prices": {
   "ok": true,
   "seconds": 0.1
  },
  "volume_coverage": {
   "ok": true,
   "seconds": 0.2
  },
  "unattributed_beneficiaries": {
   "ok": true,
   "seconds": 21.5
  },
  "tx_targets": {
   "ok": true,
   "seconds": 0.2
  },
  "wallet_summary": {
   "ok": true,
   "seconds": 0.5
  }
 },
 "params": {
  "discovery_blocks": 300,
  "watch_blocks": 3600,
  "top_k": 30,
  "receipt_limit": 150000,
  "confirmations": 12
 },
 "primary": "drpc",
 "verifier": "private-2",
 "getlogs_range": 10,
 "failover": {
  "chain": [
   "drpc",
   "publicnode"
  ],
  "switches": []
 },
 "window": {
  "head": 26178783,
  "discovery": [
   26174869,
   26175168
  ],
  "watch": [
   26175169,
   26178888
  ]
 },
 "discovery_ingest": {
  "blocks": 300,
  "logs": 8474,
  "decoded": 8474,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26175169,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "discovery": {
  "swaps_seen": 8474,
  "pools_seen": 1120,
  "candidates": 300,
  "verified": 245,
  "rejected_unverified": 55,
  "dropped_tokens": [],
  "unpriced_swaps": {
   "no_eth_price": 7,
   "no_quote_leg": 136
  },
  "eth_points": 1167,
  "eth_outliers_dropped": 3,
  "constants": {
   "0xc02aaa39": true,
   "0xa0b86991": true,
   "0xdac17f95": true,
   "0x6b175474": true
  },
  "pools": [
   {
    "pool": "0x56534741cd8b152df6d48adf7ac51f75169a83b2",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WBTC/USDT",
    "swaps": 46,
    "usd_volume": 1105466.963136
   },
   {
    "pool": "0x1ac97b51ca74fd1f395c343b305d58e4c2b01aca",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "NEX/WETH",
    "swaps": 233,
    "usd_volume": 330057.9932924959
   },
   {
    "pool": "0x1e5d177e223380b651f450ba3c4319c6f0f3ab21",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "DOPE/WETH",
    "swaps": 289,
    "usd_volume": 273364.37392023887
   },
   {
    "pool": "0xe6f4ee50c0429a6f85761bbe8f797a299eb23f89",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "BUNKER/WETH",
    "swaps": 165,
    "usd_volume": 237899.09477736725
   },
   {
    "pool": "0xf774c0cf63a7bb1a403fc7256242283c150e9b95",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "DOPE/WETH",
    "swaps": 230,
    "usd_volume": 235239.9110596528
   },
   {
    "pool": "0x4585fe77225b41b697c938b018e2ac67ac5a20c0",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WBTC/WETH",
    "swaps": 30,
    "usd_volume": 225363.12435364607
   },
   {
    "pool": "0x398c09f3482c2c4f591204dea79aab9ad1d403c7",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "WETH/INCOGNITO",
    "swaps": 129,
    "usd_volume": 140791.38250333178
   },
   {
    "pool": "0x9db9e0e53058c89e5b94e29621a205198648425b",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WBTC/USDT",
    "swaps": 15,
    "usd_volume": 139494.778171
   },
   {
    "pool": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WBTC/USDC",
    "swaps": 13,
    "usd_volume": 118923.646183
   },
   {
    "pool": "0xe6d7ebb9f1a9519dc06d557e03c522d53520e76a",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "USDe/USDC",
    "swaps": 6,
    "usd_volume": 95435.395538
   },
   {
    "pool": "0x109830a1aaad605bbf02a9dfa7b0b92ec2fb7daa",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "wstETH/WETH",
    "swaps": 6,
    "usd_volume": 80282.67750984953
   },
   {
    "pool": "0x09c5f9b273de8d41e5dce0867ca67e78c92a3a32",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/USDC",
    "swaps": 44,
    "usd_volume": 39324.160482
   },
   {
    "pool": "0xa43fe16908251ee70ef74718545e4fe6c5ccec9f",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "PEPE/WETH",
    "swaps": 33,
    "usd_volume": 37605.657732083004
   },
   {
    "pool": "0x7b1e5d984a43ee732de195628d20d05cfabc3cc7",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WETH/ONDO",
    "swaps": 22,
    "usd_volume": 31286.865124417156
   },
   {
    "pool": "0x3470447f3cecffac709d3e783a307790b0208d60",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "UNI/USDT",
    "swaps": 15,
    "usd_volume": 29722.162879
   },
   {
    "pool": "0x95dbb3c7546f22bce375900abfdd64a4e5bd73d6",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "EURC/USDC",
    "swaps": 7,
    "usd_volume": 26917.804871
   },
   {
    "pool": "0xe6ff8b9a37b0fab776134636d9981aa778c4e718",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "WBTC/WETH",
    "swaps": 72,
    "usd_volume": 25619.641274499987
   },
   {
    "pool": "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "LINK/WETH",
    "swaps": 9,
    "usd_volume": 22533.313758809298
   },
   {
    "pool": "0xee8aaa362a75fbf8e0a38a50ddc27f38551e16ea",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "NEAR/USDC",
    "swaps": 39,
    "usd_volume": 22487.547593
   },
   {
    "pool": "0xe12959c09e80f3228c52c517cf70ea6eb13d5e10",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/WETH",
    "swaps": 30,
    "usd_volume": 21895.44342663355
   },
   {
    "pool": "0x24ee2c6b9597f035088cda8575e9d5e15a84b9df",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "QNT/WETH",
    "swaps": 41,
    "usd_volume": 21750.38642670341
   },
   {
    "pool": "0x41a561b972039a9ccb975a4c17b84c9f95099e15",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "ADI/USDC",
    "swaps": 79,
    "usd_volume": 20926.857082
   },
   {
    "pool": "0x894d4e6d3d2abc64fc0de0e4e2ea63a93bc9c520",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "USDC/IMD",
    "swaps": 66,
    "usd_volume": 20352.204824
   },
   {
    "pool": "0x000ba527862e5b82cff0f7c66b646af023274aa1",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "SAFE/WETH",
    "swaps": 58,
    "usd_volume": 20072.283313746884
   },
   {
    "pool": "0x5d4f3c6fa16908609bac31ff148bd002aa6b8c83",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "LINK/WETH",
    "swaps": 43,
    "usd_volume": 19374.593694800064
   },
   {
    "pool": "0x86bc870520acf4e9c255270d7f51c814ad184960",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "W/WETH",
    "swaps": 125,
    "usd_volume": 18820.987167888925
   },
   {
    "pool": "0x33676385160f9d8f03a0db2821029882f7c79e93",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "RLB/USDT",
    "swaps": 5,
    "usd_volume": 16914.229023
   },
   {
    "pool": "0x3539f9c1ce0b6e77dd6d8b7d7a8b0daef6b41712",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "BYBOOP/WETH",
    "swaps": 172,
    "usd_volume": 16759.097496507162
   },
   {
    "pool": "0x5ae13baaef0620fdae1d355495dc51a17adb4082",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "PAXG/USDC",
    "swaps": 17,
    "usd_volume": 16030.950049
   },
   {
    "pool": "0x2322e5517a3cbc75a3f02d74c96f82dda120d841",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "RLB/USDC",
    "swaps": 6,
    "usd_volume": 15759.25093
   },
   {
    "pool": "0xe0554a476a092703abdb3ef35c80e0d76d32939f",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "USDC/WETH",
    "swaps": 814,
    "usd_volume": 1961612.892707
   },
   {
    "pool": "0x4e68ccd3e89f51c3074ca5072bbac773960dfa36",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WETH/USDT",
    "swaps": 60,
    "usd_volume": 1580467.459799
   },
   {
    "pool": "0xc7bbec68d12a0d1830360f8ec58fa599ba1b0e9b",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "WETH/USDT",
    "swaps": 508,
    "usd_volume": 875717.735873
   }
  ]
 },
 "watch_ingest": {
  "blocks": 3600,
  "logs": 34520,
  "decoded": 34520,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26178769,
  "notes": [
   "stopped at max_blocks"
  ],
  "fresh_tail": {
   "blocks": 120,
   "logs": 965,
   "next_block": 26178889
  }
 },
 "eth_series": {
  "points": 11932,
  "outliers_dropped": 7,
  "min": 2436.490277658258,
  "max": 2574.6081055919635
 },
 "chainlink": {
  "feed": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
  "samples": [
   {
    "block": 26178883,
    "blocks_behind_head": 25,
    "chainlink": 2520.62,
    "from_swaps": 2521.0525454545455,
    "deviation_pct": 0.017160280190804428
   },
   {
    "block": 26178884,
    "blocks_behind_head": 24,
    "chainlink": 2520.62,
    "from_swaps": 2521.0118888663737,
    "deviation_pct": 0.015547320356649125
   },
   {
    "block": 26178885,
    "blocks_behind_head": 23,
    "chainlink": 2520.62,
    "from_swaps": 2521.468635260809,
    "deviation_pct": 0.03366771908535242
   },
   {
    "block": 26178886,
    "blocks_behind_head": 22,
    "chainlink": 2520.62,
    "from_swaps": 2524.133449879166,
    "deviation_pct": 0.13938832030080645
   },
   {
    "block": 26178887,
    "blocks_behind_head": 21,
    "chainlink": 2520.62,
    "from_swaps": 2521.911390852639,
    "deviation_pct": 0.051233063795387175
   },
   {
    "block": 26178888,
    "blocks_behind_head": 20,
    "chainlink": 2520.62,
    "from_swaps": 2522.4201671267565,
    "deviation_pct": 0.0714176324379034
   }
  ],
  "unavailable": 0,
  "median_deviation_pct": 0.0424503914403698,
  "max_deviation_pct": 0.13938832030080645,
  "criterion": "pass if >=3 samples, median <= 0.5% and max <= 1.5% (Chainlink only updates on 0.5% moves or its heartbeat)",
  "status": "pass"
 },
 "state_check": {
  "candidates": 60,
  "checked": 60,
  "exact_match": 60,
  "unavailable": 0,
  "mismatches": [],
  "match_rate": 1.0,
  "criterion": "pass if >=10 checked and >=90% equal (other transactions of the same wallet in the same block legitimately differ)",
  "status": "pass"
 },
 "receipts": {
  "stored": 31722,
  "transfers": 150377,
  "errors": 0,
  "inconsistent_with_getlogs": 0,
  "decode_errors": 0,
  "notes": []
 },
 "trades": {
  "txs_examined": 31722,
  "txs_without_receipt": 0,
  "trades": 9042,
  "confirmed": 8728,
  "mismatch": 314,
  "skips_by_reason": {
   "quote_only": 16854,
   "no_eth_price": 12,
   "no_sender_transfer": 7437,
   "zero_net_flow": 218
  },
  "eth_points": 11932,
  "eth_outliers_dropped": 7
 },
 "attribution": {
  "swap_txs_excluding_quote_only": 14868,
  "txs_with_a_trade": 9035,
  "share_with_a_trade": 0.6077,
  "confirmed_share_of_trades": 0.9653
 },
 "second_provider": {
  "receipts_checked": 50,
  "receipt_mismatches": [],
  "receipt_fetch_errors": 0,
  "trade_wallets_checked": 50,
  "wallet_mismatches": [],
  "tx_fetch_errors": 0,
  "passed": true
 },
 "cross_pool_prices": {
  "buckets_compared": 242,
  "tokens_compared": 4,
  "median_deviation_pct": 0.072403918775052,
  "p90_deviation_pct": 0.15327002332963657,
  "max_deviation_pct": 0.8103917596535979
 },
 "volume_coverage": {
  "priced_swaps_usd_total": 42626523.899307884,
  "by_class": {
   "skipped:no_sender_transfer": {
    "usd": 22663417.064050693,
    "share": 0.5317,
    "swaps": 6297
   },
   "attributed_to_a_wallet": {
    "usd": 12540550.782819832,
    "share": 0.2942,
    "swaps": 9152
   },
   "skipped:quote_only": {
    "usd": 6659711.024869422,
    "share": 0.1562,
    "swaps": 1539
   },
   "skipped:zero_net_flow": {
    "usd": 762845.0275679375,
    "share": 0.0179,
    "swaps": 283
   }
  },
  "note": "volume-weighted: the share of traded USD whose wallet we know; txs counted without weights would overstate it"
 },
 "unattributed_beneficiaries": {
  "sampled": 300,
  "final_recipient_is": {
   "contract": 204,
   "eoa": 18,
   "no_final_recipient": 78
  },
  "code_lookup_errors": 0,
  "most_repeated_recipients": [
   {
    "to": "0x000000000004444c5dc75cb358380d2e3de08a90",
    "txs": 56
   },
   {
    "to": "0x278d858f05b94576c1e6f73285886876ff6ef8d2",
    "txs": 20
   },
   {
    "to": "0x51c72848c68a965f66fa7a88855f9f7784502a7f",
    "txs": 19
   },
   {
    "to": "0xbdb3ba9ffe392549e1f8658dd2630c141fdf47b6",
    "txs": 15
   },
   {
    "to": "0x8f10b468b06c6fd214b65f87778827f7d113f996",
    "txs": 7
   }
  ],
  "note": "diagnostic only: an EOA recipient suggests a real user behind a relayer (a possible later attribution rule); a contract suggests a bot or aggregator"
 },
 "tx_targets": {
  "top_to_for_txs_with_a_trade": [
   {
    "to": "0xdfa8ead9129d2053f307e9370570a33118619ea0",
    "txs": 4917
   },
   {
    "to": "0xe592427a0aece92de3edee1f18e0157c05861564",
    "txs": 2618
   },
   {
    "to": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    "txs": 211
   },
   {
    "to": "0x66a9893cc07d91d95644aedd05d03f95e1dba8af",
    "txs": 202
   },
   {
    "to": "0x23617e59a5925b2a4bf75d73ff6711cd0b29de85",
    "txs": 182
   },
   {
    "to": "0x0000000000001ff3684f28c67538d4d072c22734",
    "txs": 87
   },
   {
    "to": "0x111111125421ca6dc452d289314280a0f8842a65",
    "txs": 84
   },
   {
    "to": "0x8feab81d36e7576107d5de0758c1b839be31b4f6",
    "txs": 65
   }
  ],
  "top_to_for_unattributed_txs": [
   {
    "to": "0x51c72848c68a965f66fa7a88855f9f7784502a7f",
    "txs": 1311
   },
   {
    "to": "0x278d858f05b94576c1e6f73285886876ff6ef8d2",
    "txs": 674
   },
   {
    "to": "0xbdb3ba9ffe392549e1f8658dd2630c141fdf47b6",
    "txs": 671
   },
   {
    "to": "0xcbc6ec2db48b469b6bd93816701bc5089da78bf2",
    "txs": 366
   },
   {
    "to": "0xccc88a9d1b4ed6b0eaba998850414b24f1c315be",
    "txs": 322
   },
   {
    "to": "0x227be0f88ecb7899a0e6e0347888b909d622c8e1",
    "txs": 302
   },
   {
    "to": "0x4313c378cc91ea583c91387b9216e2c03096b27f",
    "txs": 287
   },
   {
    "to": "0x4337084d9e255ff0702461cf8895ce9e3b5ff108",
    "txs": 217
   }
  ],
  "unattributed_txs": 7071,
  "note": "addresses are not labelled here; a 'to' that is frequent among attributed trades is a public router, one that appears only among unattributed txs is typically a private bot contract"
 },
 "wallets": {
  "pnl_overview": {
   "wallets_with_a_known_cost_closed_trade": 49,
   "closed_trades_with_known_cost": 341,
   "win_rate_on_those": 0.1173,
   "total_realized_known_cost_usd": 201.24,
   "total_unrealized_usd_all_wallets": -1525930.5,
   "top_by_realized_known_cost": [
    {
     "wallet": "0x8bb88a3eafd6ba0b6cce254c0c447c4cf5860afe",
     "closed_trades": 60,
     "closed_with_known_cost": 42,
     "wins": 32,
     "realized_pnl_known_cost_usd": 344.0225892882378,
     "unrealized_pnl_usd": 17.039397923097376,
     "fees_in_trades_usd": 50.167939260452336,
     "sells_with_unknown_basis_usd": 5375.852366893506,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xebc60eaf88564c8f81afe99dece22b2ef637c440",
     "closed_trades": 2,
     "closed_with_known_cost": 2,
     "wins": 1,
     "realized_pnl_known_cost_usd": 47.54128030926479,
     "unrealized_pnl_usd": -133.97657479330547,
     "fees_in_trades_usd": 5.116369224890143,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xab5213d62b6b851f4e4e3f827e273e545895d061",
     "closed_trades": 2,
     "closed_with_known_cost": 1,
     "wins": 1,
     "realized_pnl_known_cost_usd": 37.90236399618946,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.08071760812913348,
     "sells_with_unknown_basis_usd": 311.4770915380086,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0xb023be96b79f6f3f38b8c725ebbf679ecdf5ce4a",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 1,
     "realized_pnl_known_cost_usd": 18.445049866167672,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.25643456137991144,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0x82d8adcf6140eb163cf533b38a448612d65eb5dc",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 1,
     "realized_pnl_known_cost_usd": 18.076645189553176,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 2.0989158085421775,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0x76216333a291b13c7655b6237d9bff9a0bafcea6",
     "closed_trades": 3,
     "closed_with_known_cost": 3,
     "wins": 3,
     "realized_pnl_known_cost_usd": 13.937203353052727,
     "unrealized_pnl_usd": 27.175590212409055,
     "fees_in_trades_usd": 20.780658334060035,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xb072d4eb81d70f11bb1ae55a82ca98ae44f061f4",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 1,
     "realized_pnl_known_cost_usd": 0.9679156519666076,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 1.4183909082309962,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0xdf5b74a3a5951d6e234a694f41246104bbffc8fd",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.006795424750651683,
     "unrealized_pnl_usd": 14.329369557225096,
     "fees_in_trades_usd": 0.47123040891024853,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0x188d9d2ba7071e94cda9021eeff492ec5f9601de",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.025847256309719336,
     "unrealized_pnl_usd": -0.03299608803804482,
     "fees_in_trades_usd": 0.045283330500202286,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0x73708a726c26e1b7d9ed781463d93e991de22355",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.04191739079899508,
     "unrealized_pnl_usd": -0.029528301528341395,
     "fees_in_trades_usd": 0.0762053918622709,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 1
    }
   ],
   "bottom_by_realized_known_cost": [
    {
     "wallet": "0xe9ac1c8a3f55bdeaa8ecdefd1323d014e7672fff",
     "closed_trades": 2,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -41.95739318833498,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.07418420502257983,
     "sells_with_unknown_basis_usd": 380.10607110959165,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0xc5bc98458f0bfb8a278b5b9711c48fa86dc988ea",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -32.9773868795267,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 1.3786554278801268,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0xb27e90464a75cfe015b83f633a04a88cce57f700",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -13.50164193734974,
     "unrealized_pnl_usd": -28.839443012931167,
     "fees_in_trades_usd": 3.3029804990366403,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 2
    },
    {
     "wallet": "0x783212944ad54e98036bd5fbe873bf3bd294324f",
     "closed_trades": 25,
     "closed_with_known_cost": 21,
     "wins": 0,
     "realized_pnl_known_cost_usd": -12.820249911907329,
     "unrealized_pnl_usd": -0.4378613469214015,
     "fees_in_trades_usd": 5.4456653148986565,
     "sells_with_unknown_basis_usd": 871.5979533355842,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xa64de29b9ad210165cfb9bf3a8d8134aa3611467",
     "closed_trades": 24,
     "closed_with_known_cost": 19,
     "wins": 0,
     "realized_pnl_known_cost_usd": -11.825286654837416,
     "unrealized_pnl_usd": -0.6163157670033934,
     "fees_in_trades_usd": 4.9725992069191305,
     "sells_with_unknown_basis_usd": 930.5282063620336,
     "open_positions_marked_at_last_price": 1
    }
   ],
   "unrealized_caveat": "marked at the LAST execution price seen in this window; in thin pools that price is not what a position could be sold for, so treat it as indicative only",
   "caveat": "observed only inside this window: no history before it, so cost basis of earlier holdings is unknown (excluded, never invented); wallets are tx.from only; execution price only (no off-chain costs); a ranking from one window is NOT evidence of skill"
  },
  "wallets": 3081,
  "wallets_with_confirmed_trade": 2914,
  "wallets_with_2plus_trades": 1570,
  "top_by_usd": [
   {
    "wallet": "0x8b137283471e9a8147c4c123fe51205864ac616d",
    "trades": 1,
    "usd": 378178.4301847371
   },
   {
    "wallet": "0x03327768efd938c094b9f6d086d9ecd08afa1ae7",
    "trades": 4,
    "usd": 176258.803927
   },
   {
    "wallet": "0x774bb9306df1cd921eb842b1388c78f75e6ef79f",
    "trades": 3,
    "usd": 139114.5624215961
   },
   {
    "wallet": "0xaea4bcad666659e7937ce8740ff54afa38af5122",
    "trades": 2,
    "usd": 113822.327404
   },
   {
    "wallet": "0xa130772609c7fa01b59bfd75ab56660c1a6ae14a",
    "trades": 16,
    "usd": 105277.081331
   },
   {
    "wallet": "0x7a88c70499c3ca741f83f0ea70c4cb7acc4f176d",
    "trades": 5,
    "usd": 97356.62812508362
   },
   {
    "wallet": "0x3243d4b454f38ac2be5518957dbe29911f386f9f",
    "trades": 8,
    "usd": 57536.92493368659
   },
   {
    "wallet": "0x4c83baf502ad36e152a5c10f0e644f1bb0be3a45",
    "trades": 22,
    "usd": 51047.064523595844
   },
   {
    "wallet": "0xc709f44710739c838efe0400455a016e6da665a0",
    "trades": 26,
    "usd": 50559.759625788734
   },
   {
    "wallet": "0xa32d1b04de9b5acba44a039f7fea7aca4931bb94",
    "trades": 6,
    "usd": 48987.07449
   }
  ],
  "pnl": {
   "wallets_with_pnl": 2914,
   "closed_trades": 3125,
   "closed_trades_with_known_cost": 341,
   "sells_with_unknown_basis_usd": 5338756.181022134,
   "trades_with_unpriced_gas": 0,
   "note": "window is short: most sells have no earlier buy in the data, so their cost is UNKNOWN and is not turned into a profit or loss"
  }
 },
 "integrity": {
  "steps_failed": [],
  "receipts_inconsistent": 0,
  "chainlink_failed": false,
  "second_provider_failed": false,
  "state_check_failed": false
 }
}
```
