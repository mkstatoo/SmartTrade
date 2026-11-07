# Wallet attribution on real Ethereum data

run at 2026-11-07 11:10:15 UTC. Everything below is a measurement of THIS run only.

- **window blocks (discovery + watch)**: 300 + 3600
- **pools watched**: 33
- **receipts stored / errors / inconsistent**: 12101 / 0 / 0
- **trades (confirmed / mismatch)**: 2121 (1958 / 163)
- **share of swap txs that became a trade**: 0.3582
- **chainlink check**: pass
- **second provider check**: True
- **balance-state check**: pass
- **cross-pool price deviation (median / max %)**: 0.04787484277821922 / 0.39036643234454205
- **wallets with a confirmed trade**: 622
- **integrity**: no integrity problem found by the checks above

```json
{
 "at_utc": "2026-11-07 11:10:15",
 "chain": "ethereum",
 "steps": {
  "ingest_discovery": {
   "ok": true,
   "seconds": 30.0
  },
  "discover_pools": {
   "ok": true,
   "seconds": 108.8
  },
  "ingest_watch": {
   "ok": true,
   "seconds": 324.3
  },
  "ingest_fresh_tail": {
   "ok": true,
   "seconds": 3.8
  },
  "chainlink_check": {
   "ok": true,
   "seconds": 0.7
  },
  "eth_price_by_pool": {
   "ok": true,
   "seconds": 0.0
  },
  "collect_tail_receipts": {
   "ok": true,
   "seconds": 4.8
  },
  "derive_tail": {
   "ok": true,
   "seconds": 0.2
  },
  "state_check": {
   "ok": true,
   "seconds": 7.1
  },
  "collect_receipts": {
   "ok": true,
   "seconds": 244.5
  },
  "derive_trades": {
   "ok": true,
   "seconds": 2.0
  },
  "second_provider_check": {
   "ok": true,
   "seconds": 18.3
  },
  "cross_pool_prices": {
   "ok": true,
   "seconds": 0.0
  },
  "export_trades": {
   "ok": true,
   "seconds": 0.1
  },
  "volume_coverage": {
   "ok": true,
   "seconds": 0.1
  },
  "unattributed_beneficiaries": {
   "ok": true,
   "seconds": 7.0
  },
  "tx_targets": {
   "ok": true,
   "seconds": 0.0
  },
  "wallet_summary": {
   "ok": true,
   "seconds": 0.1
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
   "private-1",
   "publicnode"
  ],
  "switches": []
 },
 "window": {
  "head": 26362585,
  "discovery": [
   26358671,
   26358970
  ],
  "watch": [
   26358971,
   26362611
  ]
 },
 "discovery_ingest": {
  "blocks": 300,
  "logs": 6469,
  "decoded": 6469,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26358971,
  "notes": [
   "stopped at max_blocks"
  ]
 },
 "discovery": {
  "swaps_seen": 6469,
  "pools_seen": 1117,
  "candidates": 300,
  "verified": 238,
  "rejected_unverified": 62,
  "dropped_tokens": [],
  "unpriced_swaps": {
   "no_eth_price": 3,
   "no_quote_leg": 103
  },
  "eth_points": 810,
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
    "swaps": 43,
    "usd_volume": 409413.36193413584
   },
   {
    "pool": "0x56534741cd8b152df6d48adf7ac51f75169a83b2",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "WBTC/USDT",
    "swaps": 47,
    "usd_volume": 319723.69271
   },
   {
    "pool": "0x109830a1aaad605bbf02a9dfa7b0b92ec2fb7daa",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "wstETH/WETH",
    "swaps": 18,
    "usd_volume": 87549.91270802193
   },
   {
    "pool": "0xa43fe16908251ee70ef74718545e4fe6c5ccec9f",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "PEPE/WETH",
    "swaps": 200,
    "usd_volume": 65929.34638271172
   },
   {
    "pool": "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "AAVE/WETH",
    "swaps": 33,
    "usd_volume": 65525.58543742632
   },
   {
    "pool": "0xe6ff8b9a37b0fab776134636d9981aa778c4e718",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "WBTC/WETH",
    "swaps": 70,
    "usd_volume": 58750.359094726766
   },
   {
    "pool": "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "LINK/WETH",
    "swaps": 10,
    "usd_volume": 56076.461617079825
   },
   {
    "pool": "0x09c5f9b273de8d41e5dce0867ca67e78c92a3a32",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/USDC",
    "swaps": 49,
    "usd_volume": 36546.08061
   },
   {
    "pool": "0x41a561b972039a9ccb975a4c17b84c9f95099e15",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "ADI/USDC",
    "swaps": 89,
    "usd_volume": 35891.780562
   },
   {
    "pool": "0x3470447f3cecffac709d3e783a307790b0208d60",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "UNI/USDT",
    "swaps": 23,
    "usd_volume": 34807.158771
   },
   {
    "pool": "0x8a7e585048bda875e64024118c506b14f78166dd",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "PAXG/WETH",
    "swaps": 12,
    "usd_volume": 33933.47326625184
   },
   {
    "pool": "0xc5c7c21f4e60770ca5991a8832127a40f5236f73",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "XAUt/WETH",
    "swaps": 7,
    "usd_volume": 28769.32271224066
   },
   {
    "pool": "0xe12959c09e80f3228c52c517cf70ea6eb13d5e10",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "cirBTC/WETH",
    "swaps": 33,
    "usd_volume": 24043.418421060265
   },
   {
    "pool": "0x2c2226a6381e68a86c1a8dcb8d9fdab050959dd5",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "HLX/USDC",
    "swaps": 88,
    "usd_volume": 20604.719473
   },
   {
    "pool": "0x7b1e5d984a43ee732de195628d20d05cfabc3cc7",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WETH/ONDO",
    "swaps": 27,
    "usd_volume": 20324.29170095461
   },
   {
    "pool": "0x4d68b530920d26c3b01c99fecc19e21011b72bbd",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "ZAMA/USDT",
    "swaps": 66,
    "usd_volume": 19199.626165
   },
   {
    "pool": "0xc9101faaac077d2f7a30c60d3d89955e1a89fa8b",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "USDC/SPCXon",
    "swaps": 118,
    "usd_volume": 17257.23591
   },
   {
    "pool": "0xc3db44adc1fcdfd5671f555236eae49f4a8eea18",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "ENA/WETH",
    "swaps": 14,
    "usd_volume": 13962.738130467353
   },
   {
    "pool": "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "UNI/WETH",
    "swaps": 16,
    "usd_volume": 13635.572629446058
   },
   {
    "pool": "0xc6b9c3fa037303d10d50d71ae3cedb0eea7a1c78",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "GHX/WETH",
    "swaps": 27,
    "usd_volume": 12288.285899176783
   },
   {
    "pool": "0x89a67c6dee35db9815da2fb9191f0998a8b37c39",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 10000,
    "pair": "WPRL/USDT",
    "swaps": 15,
    "usd_volume": 10739.052567
   },
   {
    "pool": "0x4628a0a564debfc8798eb55db5c91f2200486c24",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "RNDR/WETH",
    "swaps": 17,
    "usd_volume": 10674.860022516617
   },
   {
    "pool": "0x9c4fe5ffd9a9fc5678cfbd93aa2d4fd684b67c4c",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "PAXG/WETH",
    "swaps": 7,
    "usd_volume": 9709.459454767351
   },
   {
    "pool": "0x2bea179872982dfc293da8325ea49a03d613ee76",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "Bubbles/WETH",
    "swaps": 14,
    "usd_volume": 9141.166387302601
   },
   {
    "pool": "0x180efc1349a69390ade25667487a826164c9c6e4",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "BEAM/WETH",
    "swaps": 23,
    "usd_volume": 9011.115165033518
   },
   {
    "pool": "0x5d4f3c6fa16908609bac31ff148bd002aa6b8c83",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "LINK/WETH",
    "swaps": 35,
    "usd_volume": 8902.74111501512
   },
   {
    "pool": "0x24ee2c6b9597f035088cda8575e9d5e15a84b9df",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "QNT/WETH",
    "swaps": 27,
    "usd_volume": 8745.529453550578
   },
   {
    "pool": "0xf7fd0860922bd3352e2dbaf725a182b74bf7a2e1",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "PROMPT/USDC",
    "swaps": 33,
    "usd_volume": 8688.149755
   },
   {
    "pool": "0xc02d0fa00c0bec48186026c71da2e54ebf680139",
    "role": "watch",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "wNXM/WETH",
    "swaps": 8,
    "usd_volume": 7782.670832068269
   },
   {
    "pool": "0x52c77b0cb827afbad022e6d6caf2c44452edbc39",
    "role": "watch",
    "kind": "uniswap_v2",
    "fee": null,
    "pair": "WETH/SPX",
    "swaps": 7,
    "usd_volume": 7776.087606237378
   },
   {
    "pool": "0xe0554a476a092703abdb3ef35c80e0d76d32939f",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 100,
    "pair": "USDC/WETH",
    "swaps": 683,
    "usd_volume": 2013180.919252
   },
   {
    "pool": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 500,
    "pair": "USDC/WETH",
    "swaps": 231,
    "usd_volume": 1253012.225133
   },
   {
    "pool": "0x4e68ccd3e89f51c3074ca5072bbac773960dfa36",
    "role": "reference",
    "kind": "uniswap_v3",
    "fee": 3000,
    "pair": "WETH/USDT",
    "swaps": 16,
    "usd_volume": 374882.165994
   }
  ]
 },
 "watch_ingest": {
  "blocks": 3600,
  "logs": 14652,
  "decoded": 14652,
  "decode_errors": 0,
  "reorgs": 0,
  "next_block": 26362571,
  "notes": [
   "stopped at max_blocks"
  ],
  "fresh_tail": {
   "blocks": 41,
   "logs": 116,
   "next_block": 26362612
  }
 },
 "eth_series": {
  "points": 4000,
  "outliers_dropped": 0,
  "min": 2195.4161397287376,
  "max": 2291.7869717043504
 },
 "chainlink": {
  "feed": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
  "samples": [
   {
    "block": 26362599,
    "blocks_behind_head": 25,
    "chainlink": 2245.42983687,
    "from_swaps": 2244.268215907709,
    "deviation_pct": 0.051732676889622416,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 281,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   },
   {
    "block": 26362600,
    "blocks_behind_head": 24,
    "chainlink": 2245.42983687,
    "from_swaps": 2244.432741470005,
    "deviation_pct": 0.04440554693015506,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 282,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   },
   {
    "block": 26362606,
    "blocks_behind_head": 18,
    "chainlink": 2245.42983687,
    "from_swaps": 2244.4750887210134,
    "deviation_pct": 0.04251961621376925,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 288,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   },
   {
    "block": 26362607,
    "blocks_behind_head": 17,
    "chainlink": 2245.42983687,
    "from_swaps": 2243.905143336209,
    "deviation_pct": 0.06790207864681969,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 289,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   },
   {
    "block": 26362608,
    "blocks_behind_head": 16,
    "chainlink": 2245.42983687,
    "from_swaps": 2243.6140442655937,
    "deviation_pct": 0.08086614752289696,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 290,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   },
   {
    "block": 26362609,
    "blocks_behind_head": 15,
    "chainlink": 2245.42983687,
    "from_swaps": 2243.7163513251785,
    "deviation_pct": 0.07630991254708022,
    "feed_updated_at_block": 26362318,
    "feed_age_blocks": 291,
    "from_swaps_at_feed_update": 2245.700358509567,
    "lag_corrected_deviation_pct": 0.0120476549801289
   }
  ],
  "unavailable": 0,
  "raw_median_deviation_pct": 0.05981737776822105,
  "raw_max_deviation_pct": 0.08086614752289696,
  "basis": "lag_corrected (swap price at the moment the feed last updated)",
  "median_deviation_pct": 0.0120476549801289,
  "max_deviation_pct": 0.0120476549801289,
  "distinct_feed_rounds": 1,
  "criterion": "pass if >=3 samples, median <= 0.75% and max <= 1.5% on the stated basis (feed threshold 0.5% + swap noise)",
  "status": "pass"
 },
 "eth_price_by_pool": [
  {
   "pool": "0xe0554a47",
   "fee": 100,
   "swaps": 5368,
   "median_signed_dev_pct": -0.0004,
   "median_abs_dev_pct": 0.0131,
   "p95_abs_dev_pct": 0.0555
  },
  {
   "pool": "0x88e6a0c2",
   "fee": 500,
   "swaps": 1131,
   "median_signed_dev_pct": 0.0006,
   "median_abs_dev_pct": 0.0257,
   "p95_abs_dev_pct": 0.0998
  },
  {
   "pool": "0x4e68ccd3",
   "fee": 3000,
   "swaps": 129,
   "median_signed_dev_pct": 0.1092,
   "median_abs_dev_pct": 0.1985,
   "p95_abs_dev_pct": 0.5845
  }
 ],
 "state_check": {
  "candidates": 51,
  "checked": 51,
  "exact_match": 50,
  "unavailable": 0,
  "mismatches": [
   {
    "tx": "0x9c11bc66830f",
    "state_delta": "44906474017838210000000",
    "log_delta": "-6364525982161790000000"
   }
  ],
  "match_rate": 0.9804,
  "criterion": "pass if >=10 checked and >=90% equal (other transactions of the same wallet in the same block legitimately differ)",
  "status": "pass"
 },
 "receipts": {
  "stored": 12101,
  "transfers": 71899,
  "errors": 0,
  "inconsistent_with_getlogs": 0,
  "decode_errors": 0,
  "notes": []
 },
 "trades": {
  "txs_examined": 12101,
  "txs_without_receipt": 0,
  "trades": 2121,
  "confirmed": 1958,
  "mismatch": 163,
  "skips_by_reason": {
   "no_eth_price": 6,
   "no_sender_transfer": 5434,
   "quote_only": 6179,
   "zero_net_flow": 57
  },
  "eth_points": 4000,
  "eth_outliers_dropped": 0
 },
 "attribution": {
  "swap_txs_excluding_quote_only": 5922,
  "txs_with_a_trade": 2121,
  "share_with_a_trade": 0.3582,
  "confirmed_share_of_trades": 0.9231
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
  "buckets_compared": 193,
  "tokens_compared": 5,
  "median_deviation_pct": 0.04787484277821922,
  "p90_deviation_pct": 0.13593804755318642,
  "max_deviation_pct": 0.39036643234454205
 },
 "trade_export": {
  "trades": 2121,
  "bytes": 316843
 },
 "volume_coverage": {
  "priced_swaps_usd_total": 9049761.698641922,
  "by_class": {
   "skipped:no_sender_transfer": {
    "usd": 5900118.162735942,
    "share": 0.652,
    "swaps": 4477
   },
   "skipped:quote_only": {
    "usd": 1788721.1077852647,
    "share": 0.1977,
    "swaps": 1126
   },
   "attributed_to_a_wallet": {
    "usd": 1181764.9939678798,
    "share": 0.1306,
    "swaps": 2449
   },
   "skipped:zero_net_flow": {
    "usd": 178492.13180683635,
    "share": 0.0197,
    "swaps": 68
   },
   "skipped:no_eth_price": {
    "usd": 665.302346,
    "share": 0.0001,
    "swaps": 1
   }
  },
  "note": "volume-weighted: the share of traded USD whose wallet we know; txs counted without weights would overstate it"
 },
 "unattributed_beneficiaries": {
  "sampled": 300,
  "final_recipient_is": {
   "no_final_recipient": 106,
   "contract": 183,
   "eoa": 11
  },
  "code_lookup_errors": 0,
  "most_repeated_recipients": [
   {
    "to": "0xbdb3ba9ffe392549e1f8658dd2630c141fdf47b6",
    "txs": 30
   },
   {
    "to": "0x000000000004444c5dc75cb358380d2e3de08a90",
    "txs": 27
   },
   {
    "to": "0x51c72848c68a965f66fa7a88855f9f7784502a7f",
    "txs": 21
   },
   {
    "to": "0x278d858f05b94576c1e6f73285886876ff6ef8d2",
    "txs": 18
   },
   {
    "to": "0x39da71e4880640a15a07bdb440ea33eb90d915e2",
    "txs": 6
   }
  ],
  "note": "diagnostic only: an EOA recipient suggests a real user behind a relayer (a possible later attribution rule); a contract suggests a bot or aggregator"
 },
 "tx_targets": {
  "top_to_for_txs_with_a_trade": [
   {
    "to": "0xe592427a0aece92de3edee1f18e0157c05861564",
    "txs": 871
   },
   {
    "to": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    "txs": 553
   },
   {
    "to": "0x23617e59a5925b2a4bf75d73ff6711cd0b29de85",
    "txs": 136
   },
   {
    "to": "0x8feab81d36e7576107d5de0758c1b839be31b4f6",
    "txs": 83
   },
   {
    "to": "0x111111125421ca6dc452d289314280a0f8842a65",
    "txs": 44
   },
   {
    "to": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    "txs": 39
   },
   {
    "to": "0x6131b5fae19ea4f9d964eac0408e4408b66337b5",
    "txs": 36
   },
   {
    "to": "0x881d40237659c251811cec9c364ef91dc08d300c",
    "txs": 32
   }
  ],
  "top_to_for_unattributed_txs": [
   {
    "to": "0xbdb3ba9ffe392549e1f8658dd2630c141fdf47b6",
    "txs": 900
   },
   {
    "to": "0x51c72848c68a965f66fa7a88855f9f7784502a7f",
    "txs": 787
   },
   {
    "to": "0x278d858f05b94576c1e6f73285886876ff6ef8d2",
    "txs": 490
   },
   {
    "to": "0x90c496dea71307da373ea6fbca54b24bf5025de3",
    "txs": 197
   },
   {
    "to": "0x6ddab021daedcfba8c4e12911b906a69da0e6795",
    "txs": 183
   },
   {
    "to": "0x4337084d9e255ff0702461cf8895ce9e3b5ff108",
    "txs": 177
   },
   {
    "to": "0x4313c378cc91ea583c91387b9216e2c03096b27f",
    "txs": 108
   },
   {
    "to": "0xeff6cb8b614999d130e537751ee99724d01aa167",
    "txs": 103
   }
  ],
  "unattributed_txs": 4471,
  "note": "addresses are not labelled here; a 'to' that is frequent among attributed trades is a public router, one that appears only among unattributed txs is typically a private bot contract"
 },
 "wallets": {
  "pnl_overview": {
   "wallets_with_a_known_cost_closed_trade": 34,
   "closed_trades_with_known_cost": 539,
   "win_rate_on_those": 0.0056,
   "total_realized_known_cost_usd": -241.41,
   "total_unrealized_usd_all_wallets": -972.15,
   "top_by_realized_known_cost": [
    {
     "wallet": "0xf9b6a1eb0190bf76274b0876957ee9f4f508af41",
     "closed_trades": 10,
     "closed_with_known_cost": 5,
     "wins": 3,
     "realized_pnl_known_cost_usd": 4.33003955218433,
     "unrealized_pnl_usd": -0.00027439126142699596,
     "fees_in_trades_usd": 0.17939156516725094,
     "sells_with_unknown_basis_usd": 506.5199178235079,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0x5feea8f691be66225cb7add010d9ec04333f2289",
     "closed_trades": 2,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": 1.649706143748885,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.1810871739256371,
     "sells_with_unknown_basis_usd": 303.11485396908216,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0x97501550c1491310ece644e1ace14776079f4805",
     "closed_trades": 25,
     "closed_with_known_cost": 11,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.27067309303473824,
     "unrealized_pnl_usd": -2.3970891921735045,
     "fees_in_trades_usd": 0.5318361380542214,
     "sells_with_unknown_basis_usd": 779.2332330341935,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xb97f8246d2f141b37d8bec66aa49f0ae3fdbbf3f",
     "closed_trades": 1,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.3132673252646502,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.2996273877716246,
     "sells_with_unknown_basis_usd": 0.0,
     "open_positions_marked_at_last_price": 0
    },
    {
     "wallet": "0x631b18e9110d0549b4e32cca35441f373e193b31",
     "closed_trades": 29,
     "closed_with_known_cost": 23,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.4035867947530496,
     "unrealized_pnl_usd": 0.7190182576529416,
     "fees_in_trades_usd": 0.5727348652804385,
     "sells_with_unknown_basis_usd": 8.583284582668412,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xa645d09a9a5668e4d060234b1288f0c1298a1cca",
     "closed_trades": 23,
     "closed_with_known_cost": 6,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.5211782693230878,
     "unrealized_pnl_usd": 0.021305629738672012,
     "fees_in_trades_usd": 0.7890534068021183,
     "sells_with_unknown_basis_usd": 209.12741794371252,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xa0dc8550e9aee9fe34c56abe03e6a3155e55d552",
     "closed_trades": 28,
     "closed_with_known_cost": 10,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.5588713644795917,
     "unrealized_pnl_usd": -0.3255708465683731,
     "fees_in_trades_usd": 0.8170862095193296,
     "sells_with_unknown_basis_usd": 180.65970655944406,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0x4ec3cc033535e97124f0eb87cd651f6d64bc3564",
     "closed_trades": 20,
     "closed_with_known_cost": 13,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.5809909627366419,
     "unrealized_pnl_usd": 0.778020979562851,
     "fees_in_trades_usd": 0.7612488811397417,
     "sells_with_unknown_basis_usd": 10.120861074254522,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xa847e1f63d9b00689f3c9630c561f18ee58485a7",
     "closed_trades": 32,
     "closed_with_known_cost": 20,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.6284006107732006,
     "unrealized_pnl_usd": 0.8886436747058172,
     "fees_in_trades_usd": 0.8957899497742902,
     "sells_with_unknown_basis_usd": 14.815223263669154,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xb84aa1eea10cf3347ef95f13ac5e09e40bdd3f03",
     "closed_trades": 32,
     "closed_with_known_cost": 16,
     "wins": 0,
     "realized_pnl_known_cost_usd": -0.717506812699942,
     "unrealized_pnl_usd": -0.4739748519853247,
     "fees_in_trades_usd": 0.9650278334104977,
     "sells_with_unknown_basis_usd": 20.049283236074263,
     "open_positions_marked_at_last_price": 1
    }
   ],
   "bottom_by_realized_known_cost": [
    {
     "wallet": "0x783212944ad54e98036bd5fbe873bf3bd294324f",
     "closed_trades": 35,
     "closed_with_known_cost": 29,
     "wins": 0,
     "realized_pnl_known_cost_usd": -19.542965255991632,
     "unrealized_pnl_usd": -1.0130830923106535,
     "fees_in_trades_usd": 1.4681616368553598,
     "sells_with_unknown_basis_usd": 2632.7596031907765,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xa64de29b9ad210165cfb9bf3a8d8134aa3611467",
     "closed_trades": 31,
     "closed_with_known_cost": 30,
     "wins": 0,
     "realized_pnl_known_cost_usd": -17.81169180349148,
     "unrealized_pnl_usd": -1.2692916602291027,
     "fees_in_trades_usd": 1.2789848813623053,
     "sells_with_unknown_basis_usd": 252.4571186428812,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xf83534338a5c03e1b73a39581d0cce2cd748881b",
     "closed_trades": 34,
     "closed_with_known_cost": 31,
     "wins": 0,
     "realized_pnl_known_cost_usd": -17.6480660465901,
     "unrealized_pnl_usd": -1.3580327262508094,
     "fees_in_trades_usd": 1.6140871428800811,
     "sells_with_unknown_basis_usd": 1200.6350711573107,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0x734e9b89818e25d3c6be8f5a02721aa10f0ebd54",
     "closed_trades": 32,
     "closed_with_known_cost": 31,
     "wins": 0,
     "realized_pnl_known_cost_usd": -16.82462099274485,
     "unrealized_pnl_usd": -1.9203709330904746,
     "fees_in_trades_usd": 1.4074432905476564,
     "sells_with_unknown_basis_usd": 355.6606172308612,
     "open_positions_marked_at_last_price": 1
    },
    {
     "wallet": "0xaa22e935a37ca1d669ca2c9c26c5af38bb109ffd",
     "closed_trades": 2,
     "closed_with_known_cost": 1,
     "wins": 0,
     "realized_pnl_known_cost_usd": -16.619751861701356,
     "unrealized_pnl_usd": 0.0,
     "fees_in_trades_usd": 0.33466502289039113,
     "sells_with_unknown_basis_usd": 227.0167680661487,
     "open_positions_marked_at_last_price": 0
    }
   ],
   "unrealized_caveat": "marked at the LAST execution price seen in this window; in thin pools that price is not what a position could be sold for, so treat it as indicative only",
   "caveat": "observed only inside this window: no history before it, so cost basis of earlier holdings is unknown (excluded, never invented); wallets are tx.from only; execution price only (no off-chain costs); a ranking from one window is NOT evidence of skill"
  },
  "wallets": 712,
  "wallets_with_confirmed_trade": 622,
  "wallets_with_2plus_trades": 94,
  "top_by_usd": [
   {
    "wallet": "0x783212944ad54e98036bd5fbe873bf3bd294324f",
    "trades": 70,
    "usd": 39191.770414
   },
   {
    "wallet": "0xf83534338a5c03e1b73a39581d0cce2cd748881b",
    "trades": 66,
    "usd": 35131.096076
   },
   {
    "wallet": "0xa64de29b9ad210165cfb9bf3a8d8134aa3611467",
    "trades": 66,
    "usd": 34581.539136
   },
   {
    "wallet": "0x62590f84ebdc8e02fd18ed5e513e9f72e084723e",
    "trades": 60,
    "usd": 32802.506798
   },
   {
    "wallet": "0x3f25124266234754ddc6c08b8951946329c0c88a",
    "trades": 63,
    "usd": 32576.442078
   },
   {
    "wallet": "0x08b00ceee2fb66029b53d76110b19eeaabfd1e65",
    "trades": 4,
    "usd": 32003.86907116171
   },
   {
    "wallet": "0x734e9b89818e25d3c6be8f5a02721aa10f0ebd54",
    "trades": 63,
    "usd": 31596.959756
   },
   {
    "wallet": "0xed0822826e171518281244b7f730a411ac550b83",
    "trades": 65,
    "usd": 31557.064438
   },
   {
    "wallet": "0x0dbffe1b15f9fe731e5e4f1d44b8ca616b544b22",
    "trades": 61,
    "usd": 30146.877682
   },
   {
    "wallet": "0xc5bafefb38e4778be736653112d805d9bdd31152",
    "trades": 1,
    "usd": 29357.800392
   }
  ],
  "pnl": {
   "wallets_with_pnl": 622,
   "closed_trades": 1216,
   "closed_trades_with_known_cost": 539,
   "sells_with_unknown_basis_usd": 168007.4080045622,
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
