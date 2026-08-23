# MatSHIX V2.2.1 CSI300_LOCAL 开发裁决

- 裁决：`INSUFFICIENT_EVIDENCE`
- 顶层状态：`V2_2_LOCAL_RESEARCH_BUILT`
- 停止层：`H5_PHYSICAL_FORECAST`
- 停止原因：`EXACT_Q_AND_COMPLETE_STATE_CAUSAL_TRAINING_BELOW_252`
- Authority：`MATSHIX_V2_2_1_AUTHORITY.md`
- Authority SHA-256：`eb10f33b6b45da6707fabebba9a1556854c5e52f44978d4e3f82a47f9d4886b0`
- 首次执行提交：`bacaecc4a90b5dc033781faa9fd25ac3bd7a7759`
- 分支：`codex/matshix-weather-v2-2-local`

本裁决来自 Authority 冻结后的第一次完整重跑。只把 Development Era 向前扩展到
2022-01-04；模型、特征、252/126/70% 门、Q exact 定义和 UNKNOWN 语义均未改变。
没有读取策略收益、仓位、选腿或退出结果。

## 1. 新数据效果

| 样本 | V2.2.0 | V2.2.1 |
|---|---:|---:|
| forecast sessions | 827 | 1,069 |
| H10 exact Q | 221 | 289 |
| H20 exact Q | 554 | 724 |
| H10/H20 joint exact | 220 | 288 |
| complete H4 state | 420 | 597 |
| joint exact + complete state | 126 | 187 |

2022 年本身贡献 H10 exact 68 行、H20 exact 170 行。新增数据有效进入 Q、outcome、
状态和训练链，并非被起始日或旧输入 hash 排除。

## 2. 冻结样本门

```text
maximum causal variance exact+state training rows   181
maximum causal path exact+state training rows       187
frozen minimum training rows                        252

H10 upside labels      289 total / 42 positive / 247 negative
H10 downside labels    289 total / 63 positive / 226 negative
H20 observed outcomes  1049
```

正负例总量已经超过 20，但 C2 可用训练行仍低于 252。结果是：

```text
variance opportunities  777 / C2 forecasts 0
upside opportunities     36 / C2 scores    0
downside opportunities   36 / C2 scores    0
```

不得通过删除 exact/state 要求、降低 252、缩短 causal percentile warm-up 或填补 Q 缺口
把 187 改造成可训练样本。

## 3. 核心门

```text
ENGINEERING       PASS
P_VARIANCE_H20    INSUFFICIENT_EVIDENCE
P_UP_PATH_H10     INSUFFICIENT_EVIDENCE
P_DOWN_PATH_H10   INSUFFICIENT_EVIDENCE
Q_MINUS_P_H20     NOT_APPLICABLE
```

Q−P 和前瞻接受不执行；全局站继续为 `V2_STATION_NOT_READY`。

## 4. 产物与 hash

```text
data/processed/v2_2/csi300_local_q_ledger.parquet
  079591e570fe2f992b84bc9b4169340f0810925c26bb94a52addfc920d9b36b5

data/processed/v2_2/csi300_local_outcome_ledger.parquet
  642ecec6899e0d520c01b8717bc09c93fb95f7edc24bdabb4afde53fc6ccebd2

data/processed/v2_2/csi300_local_ledger.parquet
  ac5318740d0b915d0af9769fce018a179f3e9bfda3c98bfc288a8b535c746032

outputs/v2_2_local/development_score.json
  501b38caddceeb7013dff7f347879b515e7cdc37a592fb3f365cda3dc6babb6e

outputs/v2_2_local/failure_ledger.json
  c3271604c73d52b9ce5bd303dc25b263287b955444177c6f9caa3b5e09a3d838
```

重跑的内存 ledger 与 gate 逐字段确定性一致，`strategy_inputs_used=false`，
`formal_pit_claimed=false`，`forward_accepted=false`。V2.2.0 首次裁决及其旧 hash 未改写。
