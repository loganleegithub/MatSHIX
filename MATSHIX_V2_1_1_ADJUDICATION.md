# MatSHIX V2.1.1 施工裁决

- 裁决：`V2_STATION_NOT_READY`
- 停止层：`H3_Q_SURFACE`
- 核心门：`Q=FAIL`
- 停止原因：`EXACT_BRACKET_AVAILABILITY_AGREEMENT_BELOW_FROZEN_GATE`
- Authority：`MATSHIX_V2_1_1_AUTHORITY.md`
- Authority SHA-256：`03c06e4c861bd313d0502ecbc25ee1e18511c7a080b8bc2fa1fb3eaf451c0705`
- 施工合同 SHA-256：`785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f`
- 分支：`codex/matshix-weather-v2-1-settlement`
- Confirmation 执行提交：`86aebf1d763fd9382cf14dfa9eb71afb81f74d95`
- Failure ledger：`MATSHIX_V2_1_1_FAILURE_LEDGER.json`
- Failure ledger SHA-256：`3f2fe224910caf2ed24177d47c1db321cce96740c33c56c5668591cdbd236c9b`

本裁决按首次执行前冻结的 Authority 原门作出。V2.1.1 settlement primary 在
Confirmation 的 paired coverage、paired value delta、wing agreement 与 block CI
均达到冻结门，但 exact-bracket availability agreement 只有 `84.04%`，低于
`95%`。这是可评价的核心门失败，不是样本不足，也不能由其他通过项抵消。

H4 双侧天气、H5 P、H6 Q−P、candidate、forward shadow 与 external probe 均未执行。
没有读取 ShortVol 逐日收益，没有使用选腿、仓位、退出、概率降门、UNKNOWN/
ABSTAIN 或策略收益修补气象站。

---

## 1. 阶段裁决

| 阶段 | 裁决 | 证据边界 |
|---|---|---|
| H0 V1 baseline | `PASS_PRESERVED` | 冻结 V1 manifest、ShortVol 代码与失败产物 hash 复核不变 |
| 阶段 A 业务审计 | `COMPLETE_PRESERVED` | 原缺陷台账不重判；未读策略逐日收益 |
| V2.1 Authority | `FROZEN` | 独立合同提交 `4958816` |
| V2.1.1 坐标修正 | `FROZEN` | 首次 Confirmation 前独立提交 `f3ffcb1`；只纠正 Q spot 坐标 |
| H1 DATA/ERA | `PASS` | 四载体上市与 era registry 一致 |
| H2 OUTCOME | `PASS` | raw RV 与 V2.0 逐行一致；path 按冻结的 15:00 基准重建 |
| H3 Q | `FAIL` | settlement-vs-14:56 availability agreement 未达到冻结门 |
| H4–H6 | `NOT_EXECUTED` | H3 核心停止门已触发 |
| Candidate/forward/probe | `NOT_EXECUTED` | 顶层不是 retrospective accepted station |

顶层不得发布 `V2_RETROSPECTIVE_SCORE_ACCEPTED`、`V2_CANDIDATE_FROZEN`、
`V2_FORWARD_SCORE_ACCEPTED` 或 `V2_CALIBRATED_PROBABILITY_ACCEPTED`。

---

## 2. 首次执行前合同修正

预执行定价复核确认 option strike、option settlement 与 parity spot 必须在同一当日
名义价格坐标。Development 区间的 ETF `adj_factor` 并非 1；若用
`ETF close × adj_factor` 作为 option surface spot，会破坏 strike/spot 坐标。

因此在未读取 Confirmation settlement 之前，V2.1.1 独立冻结：

```text
Q spot = split-consistent unadjusted ETF close
primary spot time = 15:00
comparator spot time = 14:56
adj_factor = only for H2 outcomes and H4/H5 ETF returns
```

该修正没有改变 settlement/minute option price、Confirmation、bootstrap、样本门或
acceptance threshold。原 `MATSHIX_V2_1_AUTHORITY.md` 字节与提交保留不变。

---

## 3. H1/H2 outcome 结果

冻结历史仍为 `2023-01-03..2026-06-05`，827 个 forecast session，H2 产生
9,924 行。V2.1.1 与 V2.0 对相同 key 的下列 raw 字段逐行完全一致：

```text
rv_variance_h / rv_volatility_h
rv_intraday_h / rv_overnight_h
overnight_gap_max_h
valid_bar_count / expected_bar_count
label_status / data_status / corporate_action_status
```

只有 Authority 明确覆盖的 path 基准由 14:56 改为 15:00；7,452 行 observed path
字段相对 V2.0 发生预期变化。所有 `input_known_at` 为 t 日 `23:59:59+08:00`，
`forecast_mark_kind=ETF_ADJUSTED_CLOSE_1500`。

H2 产物两次构建 hash 完全一致：

```text
data/processed/v2_1/era_registry.parquet
  297b52f74f6882be5024b83a9955424dc47b209eee5b9319af43818069672be8

data/processed/v2_1/realized_outcome_ledger.parquet
  4204f5a57e144309627e7ce41510c3fa065c590214a291b1a647729c855652d4

data/processed/v2_1/outcome_issue_ledger.parquet
  2a95574fda951a2e4d5d0541e860249dcb49cabc8d3f9c0545552dbb6e23071d

outputs/v2_1_outcomes/coverage.json
  747fb9ab303477227409876b62351ef182f586aea0032c21fe5a25d534563ce2

outputs/v2_1_outcomes/handcheck.md
  daf40a7fed2321053243118f1778a31d388ef6cb67176620428edecd062039fd
```

---

## 4. H3 frozen Confirmation gate

正式 cohort 只使用 `2025-01-02..2026-06-05` 的 H20 rows：

| Gate | Frozen threshold | Observed | Verdict |
|---|---:|---:|---|
| paired exact H20 rows | >=126 | 793 | `PASS` |
| paired exact H20 coverage | >=70% | 793/805 = 98.51% | `PASS` |
| median absolute relative Q variance delta | <=5% | 0.7460% | `PASS` |
| p90 absolute relative Q variance delta | <=15% | 2.8650% | `PASS` |
| exact-bracket availability agreement | >=95% | 84.04% | **`FAIL`** |
| wing dominant-side agreement | >=90% | 92.52% / 1,203 rows | `PASS` |
| 90% block CI of median signed delta | within [-5%, +5%] | [0.3362%, 0.6629%] | `PASS` |

Bootstrap 固定为 2,000 次、20-session moving-date blocks、seed `2026082300`。
唯一全局硬门失败为 exact availability；按 Authority，正式裁决必须是：

```text
Q = FAIL
top_level = V2_STATION_NOT_READY
stop_required = true
```

### 4.1 为什么 98.51% paired coverage 仍不能通过

`paired_exact_coverage` 的分母只包含 primary 已 exact 的 805 行；其中 793 行
comparator 也 exact，所以该指标很高。但在全部 1,372 个 listed Confirmation H20
rows 上，exact 状态交叉表为：

```text
both exact                              793
primary exact / comparator not exact    12
primary not exact / comparator exact   207
neither exact                          360
```

207 个 comparator-only exact rows 使整体 availability agreement 降至 84.04%。
最大集中 cohort 为 `CSI500_510500 × 2025`：243 行中 primary exact 44、paired 44、
comparator-only exact 138，availability agreement 43.21%；该 cohort 的 wing
agreement 也只有 81.32%。配对行上的低 value delta 无法证明这些未配对日期稳定。

### 4.2 H3 确定性产物

首次运行与同提交重放的以下 5 个 hash 全部一致，mismatch count=0：

```text
data/processed/v2_1/q_weather_ledger.parquet
  0303c2ef0f1f143d03f791e008cee6f36c3b368bf2066ad51b33bddefe706bbd

data/processed/v2_1/q_robustness_ledger.parquet
  86c9b1bae91a9336b47638da38b4c8c2d88dc2a19fd4cea01e25cccd11d13014

data/processed/v2_1/realized_outcome_q_labeled_ledger.parquet
  30d174319223e2a32f5031abf2518bcd64366f8d63a2129d92e6fb0cf3cf6626

outputs/v2_1_q_acceptance/summary.json
  b3c5ceb15af6280a37452a83246e92e562cf8150c425ced2ca80d3693762e8ff

outputs/v2_1_q_acceptance/report.md
  f5d6b17ec20f491aa8b621e78825c2bf88d714c01541e36df4c4536f9571e0bd
```

---

## 5. 证据等级与停止边界

通过的 paired-row 指标只证明：当 settlement primary 与 14:56 comparator 都能形成
exact H20 时，两者的 Q variance 和 wing 多数接近。它不证明全历史的 exact
availability 稳定，也不把 provider-reconstructed settlement 升级为 bid/ask、mid、
tradable、formal PIT 或 production evidence。

未生成：

```text
v2_1 carrier/market state ledger
physical forecast / OOF ledger
Q-P premium ledger
station acceptance
candidate manifest
forward shadow
external economic probe
```

当前版本禁止：改用另一个窗口、降低 95% 门、nearest-expiry 填洞、根据策略收益选择
proxy，或继续 H4–H6 试图抵消 Q FAIL。

---

## 6. 验证与冻结 hash

施工提交 `86aebf1` 的验证：

```text
pytest                         PASS, 43 tests
Ruff                           PASS
Mypy strict                    PASS, 43 source files
runtime doctor                 PASS
AETF source validation         PASS
H2 deterministic replay       PASS
H3 deterministic replay       PASS, 5/5 file hashes equal
Authority chain verification  PASS
```

ShortVol 源码与冻结 V1 失败产物未改变：

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

后续若研究 settlement exact-bracket 失配，只能作为新的业务/数据语义审计；任何新
challenger 必须先升级 Authority/version、保留本次 FAIL，并使用未参与此次裁决的
新证据完成验收。当前 V2.1.1 施工到此停止。
