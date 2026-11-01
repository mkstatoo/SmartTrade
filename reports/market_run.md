# Wallet attribution on real Ethereum data

run at 2026-11-01 21:28:33 UTC. Everything below is a measurement of THIS run only.


```json
{
 "at_utc": "2026-11-01 21:28:33",
 "chain": "ethereum",
 "steps": {
  "ingest_discovery": {
   "ok": true,
   "seconds": 133.1
  },
  "discover_pools": {
   "ok": true,
   "seconds": 544.0
  },
  "ingest_watch": {
   "ok": true,
   "seconds": 1512.3
  },
  "ingest_fresh_tail": {
   "ok": true,
   "seconds": 53.2
  },
  "chainlink_check": {
   "ok": true,
   "seconds": 2.8
  },
  "eth_price_by_pool": {
   "ok": true,
   "seconds": 0.1
  },
  "collect_tail_receipts": {
   "ok": true,
   "seconds": 45.9
  },
  "derive_tail": {
   "ok": true,
   "seconds": 0.7
  },
  "state_check": {
   "ok": true,
   "seconds": 21.2
  },
  "collect_receipts": {
   "ok": true,
   "seconds": 1852.0
  },
  "derive_trades": {
   "ok": true,
   "seconds": 8.0
  },
  "second_provider_check": {
   "ok": true,
   "seconds": 39.6
  },
  "cross_pool_prices": {
   "ok": true,
   "seconds": 0.1
  },
  "export_trades": {
   "ok": true,
   "seconds": 0.3
  },
  "volume_coverage": {
   "ok": true,
   "seconds": 0.2
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
 "verifier": "private-1",
 "getlogs_range": 10,
 "failover": {
  "chain": [
   "drpc",
   "private-2",
   "publicnode"
  ],
  "switches": []
 },
 "window": {
  "head": 26322610,
  "discovery": [
   26318696,
   26318995
  ],
  "watch": [
   26318996,
   26322715
  ]
 },
 "partial": true,
 "discovery_ingest": {
  "blocks": 300,
  "logs": 7454,
  "decoded": 7454,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26318996,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "discovery": {
  "swaps_seen": 7454,
  "pools_seen": 1165,
  "candidates": 300,
  "verified": 237,
  "rejected_unverified": 63,
  "dropped_tokens": [],
  "unpriced_swaps": {
   "no_eth_price": 5,
   "no_quote_leg": 158
  },
  "eth_points": 1041,
  "eth_outliers_dropped": 0,
  "constants": {
   "0xc02aaa39": true,
   "0xa0b86991": true,
   "0xdac17f95": true,
   "0x6b175474": true
  },
  "pools": [
   {
    "pool": "0x4585fe77225b41b697c938b018e2ac67ac5a20c0",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WBTC/WETH",
    "swaps": 63,
    "usd_volume": 418244.5782981204
   },
   {
    "pool": "0x56534741cd8b152df6d48adf7ac51f75169a83b2",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WBTC/USDT",
    "swaps": 63,
    "usd_volume": 395432.794263
   },
   {
    "pool": "0xa43fe16908251ee70ef74718545e4fe6c5ccec9f",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "PEPE/WETH",
    "swaps": 52,
    "usd_volume": 240579.92730698898
   },
   {
    "pool": "0x109830a1aaad605bbf02a9dfa7b0b92ec2fb7daa",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "wstETH/WETH",
    "swaps": 29,
    "usd_volume": 191630.37041249915
   },
   {
    "pool": "0x180efc1349a69390ade25667487a826164c9c6e4",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "BEAM/WETH",
    "swaps": 148,
    "usd_volume": 179464.25430701984
   },
   {
    "pool": "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "LINK/WETH",
    "swaps": 25,
    "usd_volume": 132323.7897321667
   },
   {
    "pool": "0x9db9e0e53058c89e5b94e29621a205198648425b",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WBTC/USDT",
    "swaps": 27,
    "usd_volume": 130812.877744
   },
   {
    "pool": "0xe6ff8b9a37b0fab776134636d9981aa778c4e718",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "WBTC/WETH",
    "swaps": 225,
    "usd_volume": 126091.55533679663
   },
   {
    "pool": "0xd0a4c8a1a14530c7c9efdad0ba37e8cf4204d230",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "SHFL/USDC",
    "swaps": 8,
    "usd_volume": 124685.704635
   },
   {
    "pool": "0x66e4c63873c716c16433ede4b22911631923de96",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "SI/WETH",
    "swaps": 143,
    "usd_volume": 124388.08831484194
   },
   {
    "pool": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WBTC/USDC",
    "swaps": 10,
    "usd_volume": 92200.121102
   },
   {
    "pool": "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "AAVE/WETH",
    "swaps": 22,
    "usd_volume": 88178.52131007376
   },
   {
    "pool": "0xc275a7390966e4bcbf331b837cd7316c4a3efa83",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "USDT/USDf",
    "swaps": 5,
    "usd_volume": 73919.370535
   },
   {
    "pool": "0x53bbdf4ea397d17a6f904dc882b3fb78a6875a66",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 10000,
    "pair": "WALLET/WETH",
    "swaps": 35,
    "usd_volume": 66806.07071045463
   },
   {
    "pool": "0x5d4f3c6fa16908609bac31ff148bd002aa6b8c83",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "LINK/WETH",
    "swaps": 155,
    "usd_volume": 61420.49379367036
   },
   {
    "pool": "0x4d68b530920d26c3b01c99fecc19e21011b72bbd",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "ZAMA/USDT",
    "swaps": 145,
    "usd_volume": 54273.71255
   },
   {
    "pool": "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "UNI/WETH",
    "swaps": 18,
    "usd_volume": 48980.15954249465
   },
   {
    "pool": "0x09c5f9b273de8d41e5dce0867ca67e78c92a3a32",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/USDC",
    "swaps": 61,
    "usd_volume": 46292.134552
   },
   {
    "pool": "0x4674abc5796e1334b5075326b39b748bee9eaa34",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "AAVE/WETH",
    "swaps": 98,
    "usd_volume": 46143.91038698997
   },
   {
    "pool": "0x764510ab1d39cf300e7abe8f5b8977d18f290628",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "SKY/WETH",
    "swaps": 20,
    "usd_volume": 42433.86693437293
   },
   {
    "pool": "0xc3db44adc1fcdfd5671f555236eae49f4a8eea18",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "ENA/WETH",
    "swaps": 27,
    "usd_volume": 42187.80341696599
   },
   {
    "pool": "0x3470447f3cecffac709d3e783a307790b0208d60",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "UNI/USDT",
    "swaps": 45,
    "usd_volume": 42030.197435
   },
   {
    "pool": "0x57af956d3e2cca3b86f3d8c6772c03ddca3eaacb",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "PENDLE/WETH",
    "swaps": 22,
    "usd_volume": 38856.2792295925
   },
   {
    "pool": "0xc5c7c21f4e60770ca5991a8832127a40f5236f73",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "XAUt/WETH",
    "swaps": 8,
    "usd_volume": 38832.107276808165
   },
   {
    "pool": "0xe3fe800b0de664bf0bca8ad58ecbc73b259047b0",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "POWR/WETH",
    "swaps": 105,
    "usd_volume": 38341.83674716112
   },
   {
    "pool": "0x41a561b972039a9ccb975a4c17b84c9f95099e15",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "ADI/USDC",
    "swaps": 85,
    "usd_volume": 36661.026583
   },
   {
    "pool": "0xe12959c09e80f3228c52c517cf70ea6eb13d5e10",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/WETH",
    "swaps": 47,
    "usd_volume": 34373.016787625624
   },
   {
    "pool": "0xad24e2908e16fa28c6badff86a3c008b2de964b4",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "WETH/Pikmin",
    "swaps": 38,
    "usd_volume": 26345.195392804413
   },
   {
    "pool": "0x7b1e5d984a43ee732de195628d20d05cfabc3cc7",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WETH/ONDO",
    "swaps": 26,
    "usd_volume": 23004.94827618772
   },
   {
    "pool": "0x25647e01bd0967c1b9599fa3521939871d1d0888",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "WETH/SUPER",
    "swaps": 50,
    "usd_volume": 18675.88627796256
   },
   {
    "pool": "0xe0554a476a092703abdb3ef35c80e0d76d32939f",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "USDC/WETH",
    "swaps": 718,
    "usd_volume": 1762509.439196
   },
   {
    "pool": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "USDC/WETH",
    "swaps": 106,
    "usd_volume": 519749.794956
   },
   {
    "pool": "0x11b815efb8f581194ae79006d24e0d814b7697f6",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WETH/USDT",
    "swaps": 104,
    "usd_volume": 245085.76731
   }
  ]
 },
 "watch_ingest": {
  "blocks": 3600,
  "logs": 25219,
  "decoded": 25219,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26322596,
  "notes": [
   "stopped at max_blocks"
  ],
  "fresh_tail": {
   "blocks": 120,
   "logs": 803,
   "next_block": 26322716
  }
 },
 "eth_series": {
  "points": 7525,
  "outliers_dropped": 1,
  "min": 2211.7083237985935,
  "max": 2312.1632883737957
 },
 "chainlink": {
  "feed": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
  "samples": [
   {
    "block": 26322708,
    "blocks_behind_head": 88,
    "chainlink": 2261.79279512,
    "from_swaps": 2264.27964,
    "deviation_pct": 0.10995016366510531,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 179,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   },
   {
    "block": 26322709,
    "blocks_behind_head": 87,
    "chainlink": 2261.79279512,
    "from_swaps": 2264.428890011241,
    "deviation_pct": 0.11654891186003068,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 180,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   },
   {
    "block": 26322711,
    "blocks_behind_head": 85,
    "chainlink": 2261.79279512,
    "from_swaps": 2264.654679683403,
    "deviation_pct": 0.1265316862613523,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 182,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   },
   {
    "block": 26322713,
    "blocks_behind_head": 83,
    "chainlink": 2261.79279512,
    "from_swaps": 2265.1480068406127,
    "deviation_pct": 0.14834301921253468,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 184,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   },
   {
    "block": 26322714,
    "blocks_behind_head": 82,
    "chainlink": 2261.79279512,
    "from_swaps": 2264.2571824091647,
    "deviation_pct": 0.1089572526043042,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 185,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   },
   {
    "block": 26322715,
    "blocks_behind_head": 81,
    "chainlink": 2261.79279512,
    "from_swaps": 2264.2024185279424,
    "deviation_pct": 0.10653599273732513,
    "feed_updated_at_block": 26322529,
    "feed_age_blocks": 186,
    "from_swaps_at_feed_update": 2262.561937550525,
    "lag_corrected_deviation_pct": 0.034005874993686264
   }
  ],
  "unavailable": 0,
  "raw_median_deviation_pct": 0.11324953776256799,
  "raw_max_deviation_pct": 0.14834301921253468,
  "basis": "lag_corrected (swap price at the moment the feed last updated)",
  "median_deviation_pct": 0.034005874993686264,
  "max_deviation_pct": 0.034005874993686264,
  "distinct_feed_rounds": 1,
  "criterion": "pass if >=3 samples, median <= 0.75% and max <= 1.5% on the stated basis (feed threshold 0.5% + swap noise)",
  "status": "pass"
 },
 "eth_price_by_pool": [
  {
   "pool": "0xe0554a47",
   "fee": 100,
   "swaps": 8690,
   "median_signed_dev_pct": -0.0005,
   "median_abs_dev_pct": 0.0155,
   "p95_abs_dev_pct": 0.0957
  },
  {
   "pool": "0x88e6a0c2",
   "fee": 500,
   "swaps": 1646,
   "median_signed_dev_pct": -0.0003,
   "median_abs_dev_pct": 0.0378,
   "p95_abs_dev_pct": 0.103
  },
  {
   "pool": "0x11b815ef",
   "fee": 500,
   "swaps": 1049,
   "median_signed_dev_pct": 0.0983,
   "median_abs_dev_pct": 0.0989,
   "p95_abs_dev_pct": 0.1837
  }
 ],
 "state_check": {
  "candidates": 32,
  "checked": 32,
  "exact_match": 32,
  "unavailable": 0,
  "mismatches": [],
  "match_rate": 1.0,
  "criterion": "pass if >=10 checked and >=90% equal (other transactions of the same wallet in the same block legitimately differ)",
  "status": "pass"
 },
 "receipts": {
  "stored": 22288,
  "transfers": 123388,
  "errors": 0,
  "inconsistent_with_getlogs": 0,
  "decode_errors": 0,
  "notes": []
 },
 "trades": {
  "txs_examined": 22288,
  "txs_without_receipt": 0,
  "trades": 4476,
  "confirmed": 4241,
  "mismatch": 235,
  "skips_by_reason": {
   "no_eth_price": 6,
   "quote_only": 10598,
   "no_sender_transfer": 9500,
   "zero_net_flow": 95,
   "degenerate_swap": 1
  },
  "eth_points": 7525,
  "eth_outliers_dropped": 1
 },
 "attribution": {
  "swap_txs_excluding_quote_only": 11690,
  "txs_with_a_trade": 4471,
  "share_with_a_trade": 0.3825,
  "confirmed_share_of_trades": 0.9475
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
  "buckets_compared": 369,
  "tokens_compared": 5,
  "median_deviation_pct": 0.07505633182933812,
  "p90_deviation_pct": 0.15095696685895826,
  "max_deviation_pct": 0.9784998597806368
 },
 "trade_export": {
  "trades": 4476,
  "bytes": 734371
 }
}
```
