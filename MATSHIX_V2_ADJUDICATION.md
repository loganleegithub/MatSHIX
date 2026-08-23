# MatSHIX V2 施工裁决

- 裁决：`V2_STATION_NOT_READY`
- 停止层：`H3_Q_SURFACE`
- 核心门：`Q=INSUFFICIENT_EVIDENCE`
- 停止原因：`PAIRED_Q_ROBUSTNESS_COVERAGE_BELOW_FROZEN_GATE`
- Authority：`MATSHIX_V2_AUTHORITY.md` / SHA-256 `18309ed4e71c8e8074ea3abc5645f25e465b612b300ad3b80ed9379776dad152`
- 施工合同：`MATSHIX_V2_CONSTRUCTION_PLAN.md` / SHA-256 `785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f`
- 分支：`codex/matshix-weather-v2`
- 最后施工提交：`6a5cb810a6a0c48365274cef4b75613b518a5fe4`

本裁决按已冻结 Authority 执行。Q 核心门证据不足后，H4 双侧 state、H5 P、H6 Q−P、H7 probability、H8 station acceptance、candidate、forward shadow 与 510300 外部探针均未执行。没有使用选腿、仓位、退出、概率降门或策略收益修补气象站。

---

## 1. 阶段裁决

| 阶段 | 裁决 | 证据边界 |
|---|---|---|
| H0 V1 baseline | `PASS` | 两次隔离重放 744 个文件，byte mismatch=0；V1 calibrated model rows=0 |
| 阶段 A 业务审计 | `COMPLETE` | 12 CONFIRMED、1 REJECTED_LEAD、1 INSUFFICIENT_EVIDENCE；未读策略逐日收益 |
| 阶段 B Authority | `FROZEN` | 独立文档提交 `9668a4fc453dec86639d90a2db9e56c2ea5dfc4b` |
| H1 DATA/ERA | `PASS` | contract master 四个上市日与 Authority 一致；ERA_C 的 STAR50 为 NOT_LISTED |
| H2 OUTCOME | `PASS` | 5 分钟、午休、隔夜、公司行动、H5/H10/H20、CENSORED 与镜像测试通过 |
| H3 Q | `INSUFFICIENT_EVIDENCE` | exact target Q 已建；冻结 near-close VWAP paired coverage 不足 |
| H4–H10 | `NOT_EXECUTED` | Authority 停止条件触发，不得继续 |

顶层不能发布 `V2_RETROSPECTIVE_SCORE_ACCEPTED`、`V2_CANDIDATE_FROZEN`、`V2_FORWARD_SCORE_ACCEPTED` 或 `V2_CALIBRATED_PROBABILITY_ACCEPTED`。

---

## 2. H1/H2 结果

### 2.1 Era 与上市

```text
SSE50_510050   2015-02-09
CSI300_510300  2019-12-23
CSI500_510500  2022-09-19
STAR50_588000  2023-06-05
```

当前冻结历史为 2023-01-03 至 2026-06-05，共 827 个 forecast session。H2 产生 9,924 行：

```text
OBSERVED     9,484
NOT_LISTED     300
CENSORED       140
```

300 行均为 ERA_C 的 STAR50 三个 horizon；140 行均为样本末端尚未完成的 H5/H10/H20 窗口。两类行的 outcome 均为空，不是 0。中段没有缺失 target window。

### 2.2 Outcome 证据

- 日内固定 48 个收益；午休只计算一次 `11:30 -> 13:05`；不 forward-fill；
- overnight 独立计入；
- 公司行动实际手检：CSI300 2023-01-16，adj factor `1.164 -> 1.182`，重算与保存的 overnight log return 均为 `0.0010057894802581544`；
- target 从 t+1 开始，H5/H10/H20 使用 XSHG exchange session；
- 上下路径 reciprocal fixture 交换 up/down；
- 修改 target end 之后的数据不改变已冻结 outcome；
- 四载体同日共享 date cluster，重叠窗口 cluster 可重放；
- outcome builder 未读取 weather、phase、probability 或策略字段。

H2 原始产物保持独立，不再被 Q 标签覆盖：

```text
data/processed/v2/era_registry.parquet
  sha256 297b52f74f6882be5024b83a9955424dc47b209eee5b9319af43818069672be8

data/processed/v2/realized_outcome_ledger.parquet
  sha256 628fa340ee2d21068799564b52adadfd2a72016ff72e4eabd3a99725df216316

data/processed/v2/outcome_issue_ledger.parquet
  sha256 77d0396c9a4eaff17f25a1f9303d252349761159597e0a7303cceb11e170668a
```

`outputs/v2_outcomes/coverage.json` 保存的 raw outcome hash 与当前文件逐字节一致。

---

## 3. H3 exact Q 结果

主 Q 只使用 `MINUTE_CLOSE_1456`；H5/H10/H20 都按实际 target-end ACT/365F year fraction，从有效 expiry total variance 严格夹逼。`NO_EXACT_BRACKET` 行保持空值，没有 nearest-expiry proxy 进入主 cohort。

### 3.1 Main exact coverage

| Carrier | H5 | H10 | H20 |
|---|---:|---:|---:|
| CSI300_510300 | 44/827 = 5.32% | 221/827 = 26.72% | 554/827 = 66.99% |
| CSI500_510500 | 45/827 = 5.44% | 230/827 = 27.81% | 595/827 = 71.95% |
| SSE50_510050 | 49/827 = 5.93% | 246/827 = 29.75% | 614/827 = 74.24% |
| STAR50_588000 | 35/727 = 4.81% | 195/727 = 26.82% | 497/727 = 68.36% |

全部 horizon 合计：

```text
OK                 3,325
NO_EXACT_BRACKET   6,299
NOT_LISTED           300
```

H10 exact Q 只形成 892 个可观察 path 标签：upside positive=156，downside positive=176。该事实没有被用于调整 Q proxy 或 gate。

### 3.2 V1 数学 golden

V2 只给 V1 surface builder 增加了可选 observation timestamp；默认 V1 调用不变，原 surface tests 全部通过。V2 以 Authority 的 14:56:59 cutoff 重放后，与冻结 V1 的 surface status mismatch=0。因 59 秒 ACT/365F 差异，IV 的最大绝对变化为：

```text
iv30_mf         0.0027014164 volatility points
atm_iv30        0.0027328390 volatility points
put25_iv30      0.0025110853 volatility points
call25_iv30     0.0031607282 volatility points
```

定价核心、parity、model-free variance 与 total-variance interpolation 未重写。

---

## 4. 冻结 Q robustness gate

Robustness proxy 严格为 `NEAR_CLOSE_PRINT_VWAP_1452_1456`：只使用正 volume/amount，`amount/(volume*contract_unit)` 必须落在窗口 OHLC 内；不使用日结算、future outcome 或策略结果。

| Gate | Frozen threshold | Observed | 局部结果 |
|---|---:|---:|---|
| paired exact H20 coverage | >=70% | 938/2,260 = 41.50% | 不足 |
| median abs relative Q variance delta | <=5% | 1.1672% | paired cohort 内通过 |
| p90 abs relative Q variance delta | <=15% | 4.5503% | paired cohort 内通过 |
| exact-bracket availability agreement | >=95% | 58.79% | 未达到 |
| wing dominant-side agreement | >=90% | 96.38% / 2,621 rows | paired cohort 内通过 |

`paired_exact_h20_rows=938` 虽大于最小 126，但只覆盖主 exact H20 的 41.50%，远低于冻结的 70%。可观察 pair 内的低差异与高 wing agreement 不能证明缺失 58.50% 的日期也稳定；因此 Authority 要求的正式结论是：

```text
Q = INSUFFICIENT_EVIDENCE
top_level = V2_STATION_NOT_READY
stop_required = true
```

不得把 41.50% 门改低，不得允许 nearest expiry 填充，也不得依据后续 P、Q−P 或 ShortVol 收益选择另一个价格 proxy。

H3 产物：

```text
data/processed/v2/q_weather_ledger.parquet
  sha256 ae618966fbc78cfe2f438410d9c599c0f66bd873b119a021385bcf6930f2504e

data/processed/v2/q_robustness_ledger.parquet
  sha256 fb623e3a9c2e817fc99dafb96266ea9c95d7bcb935a7eea7b77e7e571dc9732d

data/processed/v2/realized_outcome_q_labeled_ledger.parquet
  sha256 1227a8caa5220eb0f9d3e2defc21989c12ac9ab09b6ec7f5de71f0bb08a67d0e

outputs/v2_q_acceptance/summary.json
  sha256 19c40f253d32c802467be084eca1540d45e9e080eb7d954ddacf5032df4f26db

outputs/v2_q_acceptance/report.md
  sha256 91cf0f8e149eb59a4145e9d9f2039f89842834ff0a6caa63039cd8cddbade943
```

Q 主表、robustness 表与 Q-labeled outcome 在重复重放前后 hash 完全一致。

---

## 5. Defect 裁决更新

| Defect | 当前状态 | 说明 |
|---|---|---|
| ERA-001 | `CLOSED` | era registry、listing age、NOT_LISTED 与可用载体数已实现 |
| OUTCOME-001 | `CLOSED` | 策略无关 H5/H10/H20 RV/path/gap ledger 已实现 |
| HORIZON-001 | `PARTIAL_STOP` | exact H10/H20 Q 已实现，但核心 Q robustness 证据不足 |
| UNIT-001 | `REJECTED_LEAD` | V1 arithmetic golden 保持；V2 单位显式 |
| Q-ROBUSTNESS-001 | `INSUFFICIENT_EVIDENCE` | paired exact H20 coverage 41.50% < 70% |
| UPSIDE-001/002 | `NOT_EXECUTED` | H4 未获施工许可延续 |
| TIMING-001 / PHASE-001 | `NOT_EXECUTED` | H4 未获施工许可延续 |
| P-001 / QP-001 | `NOT_EXECUTED` | H5/H6 被 Q 停止门阻断 |
| PROB-001 / SAMPLE-001 / ACCEPT-001 | `NOT_EXECUTED` | H7/H8 被 Q 停止门阻断；V1 baseline 仍为 0 calibrated rows |

“已实现”与“已验收”分开：exact Q builder 工程上可用，但 Q capability 没有通过 Authority 核心门。

---

## 6. 验证与冻结边界

最终验证：

```text
pytest                    PASS, 41 tests
Ruff                      PASS
Ruff format check         PASS, 53 files
Mypy strict               PASS, 42 source files
H1/H2 deterministic hash PASS
H3 Q deterministic hash  PASS
ShortVol source hashes   UNCHANGED
```

冻结 ShortVol 关键源码仍为：

```text
src/matshix/research/shortvol.py
  8ff1e988937229abf591dde95b0d0b796fb756e9b2dd988ec11da4260c6641c8

src/matshix/research/shortvol_timing.py
  1034a0d942491ab084ee2ac20e7a172ea678927d829907aa0fccd5fd69bd0cd6
```

未生成以下任何产物：

```text
physical_forecast_ledger
physical_oof_ledger
qp_premium_ledger
v2_station_acceptance
v2_candidate
forward_shadow
external_probe
```

合规的下一条证据路径只能是：在不改门的前提下追加足够的正成交 near-close 覆盖，或获得经授权的更高质量历史报价证据；若要改变 proxy 或 gate，必须预先升级 Authority/challenger/version，再进行全新一次运行。当前版本不得继续施工。
