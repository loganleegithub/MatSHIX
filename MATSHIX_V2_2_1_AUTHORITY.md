# MATSHIX V2.2.1 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_RERUN`
- 冻结时间：`2026-08-23T14:44:35Z`
- 冻结分支：`codex/matshix-weather-v2-2-local`
- Authority 版本：`2.2.1`
- 父 Authority：`MATSHIX_V2_2_AUTHORITY.md`
- 父 Authority SHA-256：`2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8`
- 父开发裁决 SHA-256：`c4f376d3d177a95d23ad2c8cd6059c40b83b1878d13c8bd61c7a0f31a47acf6b`
- 父失败台账 SHA-256：`a3a4350016cc4e223adda8d4f0521cf1b18536340ffbdab4f9db58f34d07938e`
- 人类授权：`已经补齐数据，开始重跑`

本补充只授权把 `CSI300_LOCAL` 的 `DEVELOPMENT_ERA` 向前扩展一年并重跑。
`MATSHIX_V2_2_AUTHORITY.md` 的 targets、Q、H4、P、Q−P、模型、特征、样本门、
acceptance gates、UNKNOWN 语义和禁止事项全部原样继承。

## 1. 唯一语义变更

```text
old DEVELOPMENT_ERA = 2023-01-03..2026-06-05
new DEVELOPMENT_ERA = 2022-01-04..2026-06-05
price_proxy = MINUTE_CLOSE_1456
evidence_tier = RESEARCH_ONLY
```

2022 数据不得称为 OOF Confirmation 或 `FORMAL_PIT_QUOTES`，不得补足前瞻接受门。

## 2. 输入重建

不得改写或冒充 V2.1.1 与 V2.2.0 的冻结产物。V2.2.1 从原始 AETF 在内存中重建：

- 510300 ETF 1分钟 realized inputs 与 H10/H20 outcomes；
- 510300 14:56 minute-close exact H10/H20 Q；
- 510300 本地 H4、P 与通过 P 门后才允许的 Q−P。

outcome、Q 和 sampling-grid 算法继续复用冻结实现，不新增 proxy 或近邻到期填补。

## 3. 冻结前数据预检

```text
2022 CSI300 option sessions             242
2022 option rows at 14:56             30738
2022 CSI300 ETF 14:56 sessions          242
2022 CSI300 ETF minute sessions         242
2022 realized-input OK / censored    241 / 1
first-day censor reason      MISSING_OVERNIGHT_INPUT
```

首日缺少 2021 前收仅按原定义保留 `CENSORED`，不得补值。

## 4. 首次重跑与停止边界

实现和测试独立提交后只运行一次完整重跑。结果仍只允许
`DEVELOPMENT_PASS / DEVELOPMENT_FAIL / INSUFFICIENT_EVIDENCE`。

任何核心门 FAIL 或证据不足时停止；不得改变 252/126/70% 等冻结门，不得读取选腿、
仓位、退出、概率降门或策略收益修补天气站。V2.2.0 首次失败产物与 hash 永久保留在
父裁决中，不因本次重跑改写历史事实。
