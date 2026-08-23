# MATSHIX V2.2.2 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_RERUN`
- 冻结时间：`2026-08-23T16:05:43Z`
- 冻结分支：`codex/matshix-weather-v2-2-local`
- Authority 版本：`2.2.2`
- 父 Authority SHA-256：`eb10f33b6b45da6707fabebba9a1556854c5e52f44978d4e3f82a47f9d4886b0`
- 父开发裁决 SHA-256：`7f1d629b8d77f61b484d289a3e1bf05e1a0756399294651af85003ad6136f7ac`
- 父失败台账 SHA-256：`3e15522e4cb3a579bb610ffabf602fe97043a04e5d95c79b8f68efe13d8dcc50`
- 人类授权：`再次补充了 2020 和 2021 年的数据，开始重跑`

本补充只把 `CSI300_LOCAL DEVELOPMENT_ERA` 起点改为 `2020-01-02`。终点仍为
`2026-06-05`；price proxy 仍为 `MINUTE_CLOSE_1456 / RESEARCH_ONLY`。

`MATSHIX_V2_2_AUTHORITY.md` 和 `MATSHIX_V2_2_1_AUTHORITY.md` 的 targets、Q、H4、P、
Q−P、模型、特征、252/126/70% 门、UNKNOWN 语义和禁止事项全部原样继承。

## 数据预检

```text
year                         2020     2021
CSI300 option sessions        243      243
option rows at 14:56        28208    26944
CSI300 ETF 14:56 sessions     243      243
CSI300 ETF minute sessions    243      243
realized-input OK/censored  242/1    243/0
```

2020 首日缺少 2019 前收，继续保留 `MISSING_OVERNIGHT_INPUT / CENSORED`，不得补值。
V2.2.2 继续从原始 AETF 在内存中重建本地 Q/outcome，不改写 V2.1 冻结产物。

实现提交后只运行一次完整重跑。任一核心门 FAIL 或证据不足时停止；不得改门、填 Q、
读取选腿、仓位、退出或策略收益。V2.2.0/V2.2.1 历史裁决与 hash 不得改写。
