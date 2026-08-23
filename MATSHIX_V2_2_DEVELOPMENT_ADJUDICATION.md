# MatSHIX V2.2 CSI300_LOCAL 开发裁决

- 裁决：`INSUFFICIENT_EVIDENCE`
- 顶层状态：`V2_2_LOCAL_RESEARCH_BUILT`
- 停止层：`H5_PHYSICAL_FORECAST`
- 停止原因：`H10_EXACT_Q_HISTORY_BELOW_FROZEN_252_TRAINING_GATE`
- Authority：`MATSHIX_V2_2_AUTHORITY.md`
- Authority SHA-256：`2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8`
- 首次执行提交：`424a9f2254670996d1dc24ab8f6ea5226e058b49`
- 分支：`codex/matshix-weather-v2-2-local`

本裁决来自冻结后的第一次完整执行。没有读取或修改 ShortVol 逐日收益、选腿、仓位、
退出或策略结果；没有更换特征、降低样本门或用 nearest expiry 填补 Q。

## 1. 阶段结果

| 阶段 | 裁决 | 证据 |
|---|---|---|
| A baseline | `PASS` | main/runtime/AETF/双 V1 重放和冻结 hash 全部通过 |
| B1 Authority | `FROZEN` | 独立提交 `eb6a1b7` |
| B2 engineering | `PASS` | 50 tests、Ruff、Mypy、local-only、UNKNOWN、双重重放通过 |
| H4 local state | `BUILT` | 827 sessions，420 行完整 vector |
| H5 variance P | `INSUFFICIENT_EVIDENCE` | 0 个 C2 forecast；联合 exact 历史不足 252 |
| H5 upside P | `INSUFFICIENT_EVIDENCE` | 221 个可定义 target，低于 252 |
| H5 downside P | `INSUFFICIENT_EVIDENCE` | 221 个可定义 target，低于 252 |
| H6 Q−P | `NOT_APPLICABLE` | H20 P 未通过，不执行 |
| Forward acceptance | `NOT_EXECUTED` | 开发主线核心证据不足 |

## 2. 客观样本边界

`DEVELOPMENT_ERA=2023-01-03..2026-06-05` 共 827 个 forecast sessions：

```text
H10 exact Q                         221 / 827 = 26.72%
H20 exact Q                         554 / 827 = 66.99%
H10 and H20 joint exact             220 / 827 = 26.60%
joint exact plus complete H4 state  126 / 827 = 15.24%
complete H4 state                   420 / 827 = 50.79%
observed H20 outcomes               807
```

H10 Q-defined path labels：

```text
upside    221 total / 37 positive / 184 negative
downside  221 total / 36 positive / 185 negative
```

正负例数量分别达到 20，但冻结合同还要求至少 252 个 outcome-complete training rows。
因此两个 path Logistic 永远无法在当前历史内首次拟合。

H20 C2 variance 固定包含 `q_term_log_ratio_h10_h20`，所以训练行必须同时具备 H10/H20
exact Q 和完整 H4 vector。全历史只有 126 个此类行，也低于 252；因此没有任何
`p_c2_variance_h20`，而不是模型拟合后预测失败。

## 3. 核心门

```text
ENGINEERING       PASS
P_VARIANCE_H20    INSUFFICIENT_EVIDENCE
P_UP_PATH_H10     INSUFFICIENT_EVIDENCE
P_DOWN_PATH_H10   INSUFFICIENT_EVIDENCE
Q_MINUS_P_H20     NOT_APPLICABLE
```

Q−P 不计算，前瞻接受入口不施工。510500 settlement audit 是独立支线，可继续执行且
不得改变本裁决。

## 4. 产物与 hash

```text
data/processed/v2_2/csi300_local_ledger.parquet
  ddc2d5ee8935a83eefc39d1ae7fadd7b9f1118630a3f65c6161ef99da7a1051d

outputs/v2_2_local/development_score.json
  aea13c6a659b43a47065d71e989986fe0ed77668cc1297e142fae1897031bc14

outputs/v2_2_local/failure_ledger.json
  553cedcd33f1afd07fb61e4d35916f85fbde03fc5e58d40d70909500c8857f1d
```

首次执行在提交 `424a9f2` 的 clean worktree 中完成，内存完整重放两次，ledger 与 gate
结果逐字段相同。

## 5. 冻结文件复核

```text
src/matshix/research/shortvol.py
  8ff1e988937229abf591dde95b0d0b796fb756e9b2dd988ec11da4260c6641c8

src/matshix/research/shortvol_timing.py
  1034a0d942491ab084ee2ac20e7a172ea678927d829907aa0fccd5fd69bd0cd6

outputs/v2_baseline/v1_shortvol_timing_report.json
  e00346c5410900db96f32459dca1e9539d573fcdc2a691a090072195fb9b7503

outputs/v2_baseline/v1_shortvol_timing_panel.parquet
  1fc8885f936df321f1b094b647b69e19a4d3d2ad18c2bee55c6d7acf16e2398e
```

## 6. 停止声明

`CSI300_LOCAL` 本版到此停止。不得事后删除 `q_term_log_ratio_h10_h20`、把 252 改成
221、用 H20 替代 H10 target、使用 nearest expiry，或读取策略收益选择新定义。
