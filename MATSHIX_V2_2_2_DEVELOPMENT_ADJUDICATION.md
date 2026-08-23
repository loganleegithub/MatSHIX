# MatSHIX V2.2.2 CSI300_LOCAL 开发裁决

- 裁决：`INSUFFICIENT_EVIDENCE`
- 顶层状态：`V2_2_LOCAL_RESEARCH_BUILT`
- 停止层：`H5_PHYSICAL_FORECAST_ACCEPTANCE`
- 停止原因：`C2_EVALUATION_SAMPLE_BELOW_126`
- Authority：`MATSHIX_V2_2_2_AUTHORITY.md`
- Authority SHA-256：`5f21d1f2842ae91a0a845324b3823302f33da54a39efa9ae847b7d40b20d056b`
- 首次执行提交：`34e8926dd6f27d34825df730ebb47735806723e3`
- 分支：`codex/matshix-weather-v2-2-local`

本裁决来自 Authority 冻结后的第一次完整重跑。只把 Development Era 向前扩展到
2020-01-02；模型、特征、Q exact、252/126/70% 门和 UNKNOWN 语义均未改变。

## 1. 新数据效果

| 样本 | V2.2.1 | V2.2.2 |
|---|---:|---:|
| forecast sessions | 1,069 | 1,555 |
| H10 exact Q | 289 | 431 |
| H20 exact Q | 724 | 1,099 |
| H10/H20 joint exact | 288 | 430 |
| complete H4 state | 597 | 1,017 |
| joint exact + complete state | 187 | 319 |
| max causal variance training | 181 | 313 |
| max causal path training | 187 | 319 |

2020–2021 新增 H10 exact 142 行、H20 exact 375 行。冻结的 252 训练门已跨过，C2
首次在 2025-05-14 发布，证明新增数据有效进入完整训练链。

## 2. 正式评价门

```text
H20 variance opportunities       1263
C2 variance forecasts              64
fully paired evaluation rows       58
eligible coverage               4.59%

H10 upside opportunities           176
C2 upside scores                    64
eligible coverage               36.36%
opportunity positives/negatives  27 / 149

H10 downside opportunities         176
C2 downside scores                  64
eligible coverage               36.36%
opportunity positives/negatives  25 / 151
```

三个维度都未达到 126 个正式评价样本，且 coverage 未达到 70%，因此不能计算完整
bootstrap gate，也不能判为 PASS 或 FAIL。当前 cohort 的 variance opportunity 中，joint
exact Q + complete state 仅占 22.49%，即使忽略 252-row warm-up，也低于冻结的 70%。

## 3. 核心门

```text
ENGINEERING       PASS
P_VARIANCE_H20    INSUFFICIENT_EVIDENCE
P_UP_PATH_H10     INSUFFICIENT_EVIDENCE
P_DOWN_PATH_H10   INSUFFICIENT_EVIDENCE
Q_MINUS_P_H20     NOT_APPLICABLE
```

Q−P 和前瞻接受不执行；不得通过降低 126/70%、填补 exact Q 或修改 state completeness
追求绿灯。

## 4. 产物与 hash

```text
data/processed/v2_2/csi300_local_q_ledger.parquet
  939a3ade52eda96abd1ebacac9be45bd72124702a36fd733ed7c9573c9dd8c94

data/processed/v2_2/csi300_local_outcome_ledger.parquet
  6285142b36b9e7530ded6cb3a5f0eb93447fe81c0b6450052bee0b300559d88a

data/processed/v2_2/csi300_local_ledger.parquet
  5bcd5ba0ae99e12c7b50f32112e02d58c65d64619ba5de9316c97cd5917073d1

outputs/v2_2_local/development_score.json
  1cc7c7fdf23d79b88fa3917c042892037d2955642619d58ece17eaa96e89e053

outputs/v2_2_local/failure_ledger.json
  e45dc266ea22a9549e234421e00479b31a386d5ef85aa12f93288f5053a39382
```

`deterministic_replay=true`、`strategy_inputs_used=false`、`formal_pit_claimed=false`、
`forward_accepted=false`。V2.2.0/V2.2.1 的历史裁决与 hash 未改写。
