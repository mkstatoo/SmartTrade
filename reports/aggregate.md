# Walk-forward over merged runs

```json
{
 "runs": 58,
 "merge": {
  "duplicates": 12127,
  "agreeing_exact": 10560,
  "differing_minor": 1446,
  "quarantined": 121,
  "gaps": [
   {
    "from_block": 26307753,
    "to_block": 26308016,
    "blocks": 264
   },
   {
    "from_block": 26314662,
    "to_block": 26315446,
    "blocks": 785
   },
   {
    "from_block": 26321961,
    "to_block": 26322708,
    "blocks": 748
   },
   {
    "from_block": 26326353,
    "to_block": 26326591,
    "blocks": 239
   },
   {
    "from_block": 26336734,
    "to_block": 26336991,
    "blocks": 258
   },
   {
    "from_block": 26344007,
    "to_block": 26347621,
    "blocks": 3615
   },
   {
    "from_block": 26351276,
    "to_block": 26354605,
    "blocks": 3330
   },
   {
    "from_block": 26358254,
    "to_block": 26358344,
    "blocks": 91
   },
   {
    "from_block": 26365000,
    "to_block": 26365612,
    "blocks": 613
   },
   {
    "from_block": 26372130,
    "to_block": 26373003,
    "blocks": 874
   },
   {
    "from_block": 26376646,
    "to_block": 26377033,
    "blocks": 388
   },
   {
    "from_block": 26387108,
    "to_block": 26387246,
    "blocks": 139
   },
   {
    "from_block": 26394449,
    "to_block": 26394528,
    "blocks": 80
   },
   {
    "from_block": 26408638,
    "to_block": 26408651,
    "blocks": 14
   },
   {
    "from_block": 26415357,
    "to_block": 26415972,
    "blocks": 616
   },
   {
    "from_block": 26422679,
    "to_block": 26423262,
    "blocks": 584
   },
   {
    "from_block": 26426922,
    "to_block": 26427281,
    "blocks": 360
   },
   {
    "from_block": 26444929,
    "to_block": 26444967,
    "blocks": 39
   },
   {
    "from_block": 26465985,
    "to_block": 26466328,
    "blocks": 344
   },
   {
    "from_block": 26473208,
    "to_block": 26473804,
    "blocks": 597
   },
   {
    "from_block": 26477459,
    "to_block": 26478221,
    "blocks": 763
   },
   {
    "from_block": 26499092,
    "to_block": 26502541,
    "blocks": 3450
   }
  ]
 },
 "ignored_older_method_files": [],
 "result": {
  "trades_total": 173957,
  "trades_confirmed": 158915,
  "first_ts": 1793279411,
  "last_ts": 1795820747,
  "span_days": 29.41,
  "split_ts": 1794550079,
  "eligible_wallets": 367,
  "wallets_positive_in_A": 259,
  "selected": 20,
  "supplementary_rank_persistence": {
   "wallets": 74,
   "spearman": 0.4330692336171788,
   "p_value_one_sided": 0.0001999600079984003,
   "mean_B_return_better_half": -0.02907300310675253,
   "mean_B_return_worse_half": -0.3990028552183238,
   "status": "computed",
   "note": "supplementary only; does not enter the verdict; no cost haircut; return per wallet = pnl / known cost of its closed trades after the split"
  },
  "selected_B": {
   "haircut_0": {
    "mean_usd": 0.0,
    "median_usd": 0.0,
    "wallets_positive": 0,
    "all_eligible_mean_usd": -119.51460524576176
   },
   "haircut_0.003": {
    "mean_usd": 0.0,
    "median_usd": 0.0,
    "wallets_positive": 0,
    "all_eligible_mean_usd": -244.469079154884
   },
   "haircut_0.01": {
    "mean_usd": 0.0,
    "median_usd": 0.0,
    "wallets_positive": 0,
    "all_eligible_mean_usd": -536.0295182761693
   }
  },
  "p_value_vs_random_sets": 0.11009449527523624,
  "rank_correlation_A_vs_B": {
   "wallets": 74,
   "spearman": 0.4330692336171788
  },
  "verdict": "no_evidence",
  "note": "one pre-specified test on one split; 'signal' is a reason to look closer (more data, other split), never a go-live decision"
 },
 "files": [
  {
   "file": "trades_20261030T014206Z_4dc8248.jsonl.gz",
   "trades": 4739,
   "window": {
    "head": 26302213,
    "discovery": [
     26298299,
     26298598
    ],
    "watch": [
     26298599,
     26302257
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261030T090922Z_4dc8248.jsonl.gz",
   "trades": 2440,
   "window": {
    "head": 26304513,
    "discovery": [
     26300599,
     26300898
    ],
    "watch": [
     26300899,
     26304532
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261030T195715Z_4dc8248.jsonl.gz",
   "trades": 3589,
   "window": {
    "head": 26307728,
    "discovery": [
     26303814,
     26304113
    ],
    "watch": [
     26304114,
     26307752
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261031T090616Z_4dc8248.jsonl.gz",
   "trades": 3476,
   "window": {
    "head": 26311631,
    "discovery": [
     26307717,
     26308016
    ],
    "watch": [
     26308017,
     26311664
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261031T191140Z_4dc8248.jsonl.gz",
   "trades": 4293,
   "window": {
    "head": 26314626,
    "discovery": [
     26310712,
     26311011
    ],
    "watch": [
     26311012,
     26314661
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261101T100136Z_4dc8248.jsonl.gz",
   "trades": 4489,
   "window": {
    "head": 26319061,
    "discovery": [
     26315147,
     26315446
    ],
    "watch": [
     26315447,
     26319113
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261101T193138Z_4dc8248.jsonl.gz",
   "trades": 4910,
   "window": {
    "head": 26321917,
    "discovery": [
     26318003,
     26318302
    ],
    "watch": [
     26318303,
     26321960
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261102T100953Z_a14861a.jsonl.gz",
   "trades": 5829,
   "window": {
    "head": 26326323,
    "discovery": [
     26322409,
     26322708
    ],
    "watch": [
     26322709,
     26326352
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261102T230900Z_a14861a.jsonl.gz",
   "trades": 4115,
   "window": {
    "head": 26330206,
    "discovery": [
     26326292,
     26326591
    ],
    "watch": [
     26326592,
     26330226
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261103T100327Z_a14861a.jsonl.gz",
   "trades": 5789,
   "window": {
    "head": 26333497,
    "discovery": [
     26329583,
     26329882
    ],
    "watch": [
     26329883,
     26333509
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261103T205202Z_a14861a.jsonl.gz",
   "trades": 4135,
   "window": {
    "head": 26336707,
    "discovery": [
     26332793,
     26333092
    ],
    "watch": [
     26333093,
     26336733
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261104T095830Z_a14861a.jsonl.gz",
   "trades": 4221,
   "window": {
    "head": 26340606,
    "discovery": [
     26336692,
     26336991
    ],
    "watch": [
     26336992,
     26340640
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261104T211444Z_a14861a.jsonl.gz",
   "trades": 2797,
   "window": {
    "head": 26343973,
    "discovery": [
     26340059,
     26340358
    ],
    "watch": [
     26340359,
     26344006
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261105T212823Z_a14861a.jsonl.gz",
   "trades": 4669,
   "window": {
    "head": 26351236,
    "discovery": [
     26347322,
     26347621
    ],
    "watch": [
     26347622,
     26351275
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261106T204829Z_a14861a.jsonl.gz",
   "trades": 2622,
   "window": {
    "head": 26358220,
    "discovery": [
     26354306,
     26354605
    ],
    "watch": [
     26354606,
     26358253
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261107T091423Z_a14861a.jsonl.gz",
   "trades": 2017,
   "window": {
    "head": 26361959,
    "discovery": [
     26358045,
     26358344
    ],
    "watch": [
     26358345,
     26361978
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261107T112249Z_523879c.jsonl.gz",
   "trades": 2121,
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
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261107T192514Z_523879c.jsonl.gz",
   "trades": 2716,
   "window": {
    "head": 26364945,
    "discovery": [
     26361031,
     26361330
    ],
    "watch": [
     26361331,
     26364999
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261108T093353Z_523879c.jsonl.gz",
   "trades": 1931,
   "window": {
    "head": 26369227,
    "discovery": [
     26365313,
     26365612
    ],
    "watch": [
     26365613,
     26369250
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261108T191342Z_523879c.jsonl.gz",
   "trades": 4531,
   "window": {
    "head": 26372100,
    "discovery": [
     26368186,
     26368485
    ],
    "watch": [
     26368486,
     26372129
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261109T102134Z_523879c.jsonl.gz",
   "trades": 989,
   "window": {
    "head": 26376618,
    "discovery": [
     26372704,
     26373003
    ],
    "watch": [
     26373004,
     26376645
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261110T000142Z_523879c.jsonl.gz",
   "trades": 3143,
   "window": {
    "head": 26380648,
    "discovery": [
     26376734,
     26377033
    ],
    "watch": [
     26377034,
     26380682
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261110T105215Z_523879c.jsonl.gz",
   "trades": 3855,
   "window": {
    "head": 26383850,
    "discovery": [
     26379936,
     26380235
    ],
    "watch": [
     26380236,
     26383897
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261110T213346Z_523879c.jsonl.gz",
   "trades": 3507,
   "window": {
    "head": 26387057,
    "discovery": [
     26383143,
     26383442
    ],
    "watch": [
     26383443,
     26387107
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261111T102151Z_523879c.jsonl.gz",
   "trades": 2981,
   "window": {
    "head": 26390861,
    "discovery": [
     26386947,
     26387246
    ],
    "watch": [
     26387247,
     26390904
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261111T221151Z_523879c.jsonl.gz",
   "trades": 2391,
   "window": {
    "head": 26394401,
    "discovery": [
     26390487,
     26390786
    ],
    "watch": [
     26390787,
     26394448
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261112T103312Z_523879c.jsonl.gz",
   "trades": 2350,
   "window": {
    "head": 26398143,
    "discovery": [
     26394229,
     26394528
    ],
    "watch": [
     26394529,
     26398180
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261112T222416Z_523879c.jsonl.gz",
   "trades": 3004,
   "window": {
    "head": 26401596,
    "discovery": [
     26397682,
     26397981
    ],
    "watch": [
     26397982,
     26401630
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261113T003702Z_140e10a.jsonl.gz",
   "trades": 2236,
   "window": {
    "head": 26402302,
    "discovery": [
     26398388,
     26398687
    ],
    "watch": [
     26398688,
     26402350
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261113T103333Z_140e10a.jsonl.gz",
   "trades": 2986,
   "window": {
    "head": 26405267,
    "discovery": [
     26401353,
     26401652
    ],
    "watch": [
     26401653,
     26405313
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261113T213116Z_140e10a.jsonl.gz",
   "trades": 2992,
   "window": {
    "head": 26408596,
    "discovery": [
     26404682,
     26404981
    ],
    "watch": [
     26404982,
     26408637
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261114T094157Z_140e10a.jsonl.gz",
   "trades": 2994,
   "window": {
    "head": 26412266,
    "discovery": [
     26408352,
     26408651
    ],
    "watch": [
     26408652,
     26412313
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261114T201028Z_140e10a.jsonl.gz",
   "trades": 2743,
   "window": {
    "head": 26415300,
    "discovery": [
     26411386,
     26411685
    ],
    "watch": [
     26411686,
     26415356
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261115T100945Z_140e10a.jsonl.gz",
   "trades": 2625,
   "window": {
    "head": 26419587,
    "discovery": [
     26415673,
     26415972
    ],
    "watch": [
     26415973,
     26419633
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261115T202550Z_140e10a.jsonl.gz",
   "trades": 2046,
   "window": {
    "head": 26422641,
    "discovery": [
     26418727,
     26419026
    ],
    "watch": [
     26419027,
     26422678
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261116T103523Z_140e10a.jsonl.gz",
   "trades": 2130,
   "window": {
    "head": 26426877,
    "discovery": [
     26422963,
     26423262
    ],
    "watch": [
     26423263,
     26426921
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261117T001038Z_140e10a.jsonl.gz",
   "trades": 1991,
   "window": {
    "head": 26430896,
    "discovery": [
     26426982,
     26427281
    ],
    "watch": [
     26427282,
     26430947
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261117T113103Z_140e10a.jsonl.gz",
   "trades": 2604,
   "window": {
    "head": 26434329,
    "discovery": [
     26430415,
     26430714
    ],
    "watch": [
     26430715,
     26434363
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261117T231706Z_140e10a.jsonl.gz",
   "trades": 2795,
   "window": {
    "head": 26437789,
    "discovery": [
     26433875,
     26434174
    ],
    "watch": [
     26434175,
     26437847
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261118T110427Z_140e10a.jsonl.gz",
   "trades": 3128,
   "window": {
    "head": 26441356,
    "discovery": [
     26437442,
     26437741
    ],
    "watch": [
     26437742,
     26441415
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261118T224420Z_140e10a.jsonl.gz",
   "trades": 2785,
   "window": {
    "head": 26444878,
    "discovery": [
     26440964,
     26441263
    ],
    "watch": [
     26441264,
     26444928
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261119T111028Z_140e10a.jsonl.gz",
   "trades": 2311,
   "window": {
    "head": 26448582,
    "discovery": [
     26444668,
     26444967
    ],
    "watch": [
     26444968,
     26448619
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261119T231442Z_140e10a.jsonl.gz",
   "trades": 2433,
   "window": {
    "head": 26452103,
    "discovery": [
     26448189,
     26448488
    ],
    "watch": [
     26448489,
     26452170
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261120T111819Z_140e10a.jsonl.gz",
   "trades": 5486,
   "window": {
    "head": 26455671,
    "discovery": [
     26451757,
     26452056
    ],
    "watch": [
     26452057,
     26455725
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261120T225840Z_140e10a.jsonl.gz",
   "trades": 4611,
   "window": {
    "head": 26459137,
    "discovery": [
     26455223,
     26455522
    ],
    "watch": [
     26455523,
     26459201
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261121T104705Z_140e10a.jsonl.gz",
   "trades": 3783,
   "window": {
    "head": 26462761,
    "discovery": [
     26458847,
     26459146
    ],
    "watch": [
     26459147,
     26462814
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261121T211448Z_140e10a.jsonl.gz",
   "trades": 2843,
   "window": {
    "head": 26465926,
    "discovery": [
     26462012,
     26462311
    ],
    "watch": [
     26462312,
     26465984
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261122T104022Z_140e10a.jsonl.gz",
   "trades": 3176,
   "window": {
    "head": 26469943,
    "discovery": [
     26466029,
     26466328
    ],
    "watch": [
     26466329,
     26469980
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261122T212148Z_140e10a.jsonl.gz",
   "trades": 2637,
   "window": {
    "head": 26473158,
    "discovery": [
     26469244,
     26469543
    ],
    "watch": [
     26469544,
     26473207
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261123T113624Z_140e10a.jsonl.gz",
   "trades": 2154,
   "window": {
    "head": 26477419,
    "discovery": [
     26473505,
     26473804
    ],
    "watch": [
     26473805,
     26477458
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261124T022505Z_140e10a.jsonl.gz",
   "trades": 4712,
   "window": {
    "head": 26481836,
    "discovery": [
     26477922,
     26478221
    ],
    "watch": [
     26478222,
     26481876
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261124T132457Z_140e10a.jsonl.gz",
   "trades": 1892,
   "window": {
    "head": 26485126,
    "discovery": [
     26481212,
     26481511
    ],
    "watch": [
     26481512,
     26485174
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261125T000826Z_140e10a.jsonl.gz",
   "trades": 2484,
   "window": {
    "head": 26488359,
    "discovery": [
     26484445,
     26484744
    ],
    "watch": [
     26484745,
     26488408
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261125T121101Z_140e10a.jsonl.gz",
   "trades": 3221,
   "window": {
    "head": 26491941,
    "discovery": [
     26488027,
     26488326
    ],
    "watch": [
     26488327,
     26491982
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261125T234737Z_140e10a.jsonl.gz",
   "trades": 4232,
   "window": {
    "head": 26495421,
    "discovery": [
     26491507,
     26491806
    ],
    "watch": [
     26491807,
     26495456
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261126T114736Z_140e10a.jsonl.gz",
   "trades": 2154,
   "window": {
    "head": 26499044,
    "discovery": [
     26495130,
     26495429
    ],
    "watch": [
     26495430,
     26499091
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261127T113830Z_140e10a.jsonl.gz",
   "trades": 3077,
   "window": {
    "head": 26506156,
    "discovery": [
     26502242,
     26502541
    ],
    "watch": [
     26502542,
     26506201
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  },
  {
   "file": "trades_20261127T232734Z_140e10a.jsonl.gz",
   "trades": 3298,
   "window": {
    "head": 26509665,
    "discovery": [
     26505751,
     26506050
    ],
    "watch": [
     26506051,
     26509725
    ]
   },
   "chain": "ethereum",
   "method_version": 1
  }
 ]
}
```
