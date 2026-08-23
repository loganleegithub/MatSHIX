# MatSHIX V2.2.3 CSI300_LOCAL 开发裁决

- 裁决：`DEVELOPMENT_FAIL`
- 顶层状态：`V2_2_LOCAL_RESEARCH_BUILT`
- 停止层：`H5_PHYSICAL_FORECAST_ACCEPTANCE`
- 停止原因：`P_VARIANCE_H20_FROZEN_GATE_FAILED`
- Authority：`MATSHIX_V2_2_3_AUTHORITY.md`
- Authority SHA-256：`d47dc66aac34061d0b7287d6caa7877f3077d7f7aca1cd158b5d3805315de665`
- 首次执行提交：`d034d7cb3f059b6bf8c2a92abbc2785a11bd68cb`
- 分支：`codex/matshix-weather-v2-2-local`

本裁决来自 Authority 独立冻结、实现与测试提交后的第一次完整真实重跑。Era、targets、Q、
H4、252/126/70% 数值门、bootstrap 和 skill gates 均未在结果后修改。

## 1. 缺陷修复验收

H20 C2 只使用 exact H20 Q，H10 两侧 C2 只使用 exact H10 Q；
`q_term_log_ratio_h10_h20` 只保留为 ledger diagnostic。定向测试证明任一模型不再因另一
horizon 缺失而停发。

```text
H20 calendar opportunities              1263
H20 exact + complete H4                   715  (raw availability 56.61%)
H20 causally trainable model opportunities 528
H20 finite C2 / model opportunities   528/528  (coverage 100.00%)

H10 calendar opportunities per side       176
H10 exact + complete H4                    137  (raw availability 77.84%)
H10 causally trainable opportunities        64
H10 finite C2 / model opportunities      64/64  (coverage 100.00%)
```

V2.2.2 的联合期限绑定不再限制模型出勤。原始 horizon availability 继续如实披露，未被
改写为 70% PASS；冻结的 70% 模型出勤门按 V2.2.3 Authority 在各自 horizon 的 causally
trainable opportunities 上执行。

## 2. H20 variance 核心门

| Gate | 冻结要求 | 结果 | 裁决 |
|---|---:|---:|---|
| paired rows | >=126 | 528 | PASS |
| model coverage | >=70% | 100.00% | PASS |
| paired QLIKE skill | >=2% | -2.2433% | FAIL |
| 90% bootstrap skill lower | >0 | -14.5938% | FAIL |
| absolute normalized bias | <=20% | 8.2357% | PASS |
| 80% interval empirical coverage | 65%..95% | 62.3106% | FAIL |
| finite positive C2 | all | 528/528 | PASS |

```text
mean QLIKE C2 = 0.1626960389
mean QLIKE B1 = 0.1805356048
mean QLIKE B2 = 0.1591263347
```

C2 虽优于 B1，但差于冻结的最佳基线 B2，因此不能解释为正 skill。H20 结论是
`FROZEN_VARIANCE_GATE_FAILED`，不再是 coverage 或样本不足。

## 3. H10 path 与 Q−P

```text
upside:   64 paired rows, 17 positive / 47 negative, coverage 100%
downside: 64 paired rows, 10 positive / 54 negative, coverage 100%
```

两侧均少于 126 rows，且 model-opportunity cohort 未同时达到 20 positive / 20 negative，
裁决为 `INSUFFICIENT_EVIDENCE`。由于 H20 P 未 PASS，Q−P 为 `NOT_APPLICABLE`；未执行
前瞻接受。

## 4. 核心门与停止

```text
ENGINEERING       PASS
P_VARIANCE_H20    FAIL
P_UP_PATH_H10     INSUFFICIENT_EVIDENCE
P_DOWN_PATH_H10   INSUFFICIENT_EVIDENCE
Q_MINUS_P_H20     NOT_APPLICABLE
```

按合同在 H5 停止。不得通过恢复跨期限特征、调整模型、改变阈值、填补 Q，或读取选腿、
仓位、退出和策略收益修补本次失败。

## 5. 产物与 hash

```text
data/processed/v2_2/csi300_local_q_ledger.parquet
  939a3ade52eda96abd1ebacac9be45bd72124702a36fd733ed7c9573c9dd8c94

data/processed/v2_2/csi300_local_outcome_ledger.parquet
  6285142b36b9e7530ded6cb3a5f0eb93447fe81c0b6450052bee0b300559d88a

data/processed/v2_2/csi300_local_ledger.parquet
  7c58566ea94ed040c394cd1654779252f4cc026325e58ebe3dc7d6df4f1e9137

outputs/v2_2_local/development_score.json
  a9675b2041e0129572709c931e5d0dc6618226704f955ba699e6210646980f13

outputs/v2_2_local/failure_ledger.json
  1744f752a09a506b57baa8e944c2d0dd6c54e76e972c67eb5b83eb69d127c7a5
```

`deterministic_replay=true`、`strategy_inputs_used=false`、`formal_pit_claimed=false`、
`forward_accepted=false`。V2.2.0–V2.2.2 历史裁决与 hash 未改写。
