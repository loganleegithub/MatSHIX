# MATSHIX V2.1 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_EXECUTION`
- Authority 版本：`2.1.0`
- Challenger：`Q-ROBUSTNESS-002 / PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT`
- 父 Authority：`MATSHIX_V2_AUTHORITY.md`
- 父 Authority SHA-256：`18309ed4e71c8e8074ea3abc5645f25e465b612b300ad3b80ed9379776dad152`
- 父裁决：`MATSHIX_V2_ADJUDICATION.md`
- 父裁决 SHA-256：`eb0a0b90db9d3e3213c620568bc472ba2bbe62cb0a36fba78f042ec9e0315ebc`
- 施工合同 SHA-256：`785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f`
- V2.1 设计审计 SHA-256：`4adffd096aa937196c97b905a8f3c3f088d32b026ea5763677e5a147d39ca579`
- 冻结分支：`codex/matshix-weather-v2-1-settlement`
- Authority 父提交：`5e4027a9642f28565f0526b793613cc2e7d062e5`

本文件与 SHA 锁定的 V2.0 父 Authority 共同构成 MatSHIX V2.1 的唯一施工
Authority。本文件仅覆盖明确列出的条款；其余 era、公式、predictor registry、
模型、score/probability gate、failure ledger、停止规则和策略隔离边界逐字继承
V2.0。发生冲突时以本文件为准。

V2.0 的 `Q=INSUFFICIENT_EVIDENCE` 与 `V2_STATION_NOT_READY` 是不可变历史事实，
不得重判、覆盖或改名。V2.1 是新 challenger，不是对 V2.0 gate 的事后降门。

第一行语义代码修改只能发生在本文件独立提交之后。V2.1 首次 Confirmation 运行
之后，本版本的输入时点、price proxy、target、feature、模型、阈值、样本门、
failure 分类和输出状态不得修改。任何修改必须再升级 Authority、definition/model
version 与 candidate ID，并保留本版本证据。

---

## 1. 不可跨越边界

MatSHIX V2.1 仍是研究级 ETF 期权气象站，不是策略、交易许可、选腿、仓位或
订单引擎。站内施工和验收不得读取：

```text
strategy_permission / allow_or_block
option_structure / selected_legs
position / risk_unit / order / fill_scenario
strategy_cost / strategy_pnl / account_nav
ShortVol daily returns
```

当前历史证据固定为：

```text
evidence_tier = RESEARCH_ONLY
vintage_kind = PROVIDER_RECONSTRUCTED
history_evidence_kind = RETROSPECTIVE_WALK_FORWARD
formal_publication_status = NOT_ELIGIBLE
tradable_price_claim = false
```

结算价不得称为 bid/ask、可成交 mid、正式 PIT 或 production evidence；
Q−P 只能称为 settlement-implied research premium，不是具体期权结构预期收益。

---

## 2. 时间与因果合同

对 `forecast_session=t`：

```text
q_observation_time            = t 15:00:00 Asia/Shanghai
input_cutoff                  = t POST_CLOSE_SETTLEMENT
input_known_at                = t 23:59:59 Asia/Shanghai
consumer_decision_as_of       = next_exchange_session(t) 09:00:00 Asia/Shanghai
target_start_session          = next_exchange_session(t)
target_end_session(H)         = add_exchange_sessions(t, H)
outcome_available_at(H)       = next_exchange_session(target_end_session(H)) 09:00:00
```

`input_known_at=23:59:59` 是 provider-reconstructed 历史的保守研究可用时点，
不是交易所精确发布时间声明。它晚于交易所收盘后发布结算价、早于下一交易日决策。
未来正式证据必须保存真实 publication/receipt timestamp，不得沿用该假定。

V2.0 的 purge、outcome-complete、current-row exclusion、future-mutation invariance、
`CENSORED/UNKNOWN/NOT_LISTED` 和 causal percentile 规则全部继承。

---

## 3. Outcome 2.1 覆盖条款

5 分钟 realized variance、午休、隔夜、公司行动、H5/H10/H20 exchange-session
窗口与 V2.0 完全相同。仅路径基准从 t 日 14:56 改为与结算 Q 同步的复权 ETF
15:00 mark：

```text
frozen_mark_t = adjusted ETF mark at t 15:00
max_up_log_move_h       = max(ln(future_mark / frozen_mark_t), 0)
max_down_log_move_h     = max(-ln(future_mark / frozen_mark_t), 0)
close_to_close_return_h = ln(target_end_1500 / frozen_mark_t)
```

未来 path 仍只使用 target_start 至 target_end 的冻结 5 分钟 endpoints；目标开始前
的价格不进入 outcome。Raw RV 结果应与 V2.0 逐行相同，path 字段按 15:00 基准重建。

---

## 4. Q 2.1 主测量与对照

### 4.1 Primary

```text
price_proxy = PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT
option_price = OPTION/1d_opt_price.settle
spot = adjusted ETF 15:00 close
observation_time = t 15:00:00 Asia/Shanghai
```

只接纳有限、严格大于 0 的 settlement value、有效 contract unit、已上市且未退市
的四载体合约；`OP588080.SH` 继续排除。保留 adjusted-contract identity，不伪造
条款历史。Settlement 为交易所结算概念的 provider reconstructed 历史字段，
不是成交或双边报价。

### 4.2 Robustness comparator

```text
price_proxy = MINUTE_CLOSE_1456
option_price = OPTION/1m_opt 14:56 close
spot = adjusted ETF 14:56 close
observation_time = t 14:56:59 Asia/Shanghai
```

该 comparator 沿用 V2.0 主 Q；零成交 bar 明确标记为 reconstructed as-of close。
Comparator 只用于 outcome-blind Q robustness，不替换 primary，不择优。

### 4.3 共同数学

两者都复用 V1 已测试的 parity forward/discount、model-free variance、25D put/call
和 total-variance interpolation。H5/H10/H20 必须以各自 observation time 到
target-end 15:00 的 ACT/365F target year fraction 严格 expiry bracket；主 cohort
不得使用 nearest expiry。所有 Q fact 保存 price proxy、observation/known time、
contract/strike/parity counts、method、unit、surface/horizon/liquidity status 和版本。

---

## 5. Confirmation 与 Q gate

### 5.1 样本隔离

```text
DEVELOPMENT = 2023-01-03..2024-12-31
CONFIRMATION = 2025-01-02..2026-06-05
```

Development 只提供 `MATSHIX_V2_1_DESIGN_AUDIT.md` 中的合同设计证据，不进入
正式 verdict。V2.1 Q 只在 Confirmation H20 rows 上一次性裁决；不得先看
Confirmation settlement 结果再修改 proxy、阈值或 failure 分类。

### 5.2 冻结统计

```text
paired_exact_coverage
  = both primary/comparator exact H20 rows / primary exact H20 rows

signed_relative_delta
  = (comparator_q_variance_h20 - primary_q_variance_h20)
    / primary_q_variance_h20

absolute_relative_delta = abs(signed_relative_delta)

exact_availability_agreement
  = mean(primary_exact == comparator_exact) over listed H20 rows
```

Wing agreement 只在双方 dominant side 均可观察的 H20 rows 上计算。四载体同日为
同一日期 block；moving-date-block 固定：

```text
bootstrap_repetitions = 2000
bootstrap_block_length_sessions = 20
bootstrap_confidence = 90%
bootstrap_seed_q = 2026082300
```

### 5.3 冻结门

必须全部满足：

```text
paired exact H20 rows >= 126
paired exact H20 coverage >= 70%
median absolute relative Q variance delta <= 5%
90th percentile absolute relative Q variance delta <= 15%
exact-bracket availability agreement >= 95%
DownTail-vs-UpTail dominant-side agreement >= 90%
90% moving-date-block CI of median signed relative delta
    entirely within [-5%, +5%]
```

同时按 carrier、year 和 carrier×year 报告 paired coverage、absolute/signed delta、
availability 与 wing agreement；不以分层结果重新选择 proxy。Pair 数或 coverage
不足为 `Q=INSUFFICIENT_EVIDENCE`；样本充足但任一稳定性门不满足为 `Q=FAIL`；
全部满足才为 `Q=PASS`。

缺 bid/ask 只限制 evidence tier。通过本门也不得发布 formal PIT、production 或
tradable Q claim。

---

## 6. H4 state 2.1 覆盖条款

V2.0 第 8 节的 carrier-local 双侧 vector、ERA-D market breadth、phase 条件、
causal percentile、UNKNOWN 和 hysteresis 全部继承。所有当前价格事实改为 EOD：

```text
ETF return source = adjusted ETF 15:00 close
Q surface source = PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT
```

EWMA94 同步改为 carrier 的 15:00 adjusted close-to-close return；lambda、252-row
初始化和缺失重置保持不变。

为消除 hysteresis 实现歧义，phase severity 冻结为：

```text
BALANCED_MARKET                    0
REPAIR_IN_PROGRESS                 1
BROAD_PRESSURE                     2
BROAD_PERSISTENT_PRESSURE          3
UPTAIL_BUILDING                    4
LOCALIZED_ACUTE_STRESS             4
TWO_SIDED_CONVEXITY_BUILDING       5
SYSTEMIC_ACUTE_STRESS              5
```

severity 上升即时；下降需连续两个 consumer decision 满足新 raw phase；同 severity
不同 phase 即时切换；`UNKNOWN` 即时传播且清空 pending decline。

---

## 7. H5 P 与 H6 Q−P

V2.0 第 9、10 节的 B0/B1/B2/C1/C2 registry、feature list、ridge/logistic 参数、
训练窗、purge、interval、score percentile、bootstrap、QLIKE、path score、sample
gate 和 acceptance threshold 全部不变。只覆盖：

- 输入 Q/state/outcome 使用 2.1 定义和时间；
- EWMA94 使用 15:00 adjusted close；
- `q_minus_p_h20 = settlement_q_variance_h20 - physical_forecast_variance_h20`；
- 输出 measure 名为 `SETTLEMENT_IMPLIED_Q_MINUS_P_RESEARCH`；
- Q 未 PASS 时 H4–H6 不执行；
- H4 未 PASS 时 H5/H6 不执行；
- 任一 P primary FAIL/不足时 H6 不执行或为 `INSUFFICIENT_EVIDENCE`。

H4、H5、H6 仍不得读取 strategy/P&L。H6 结果不得用于反向选择 H4 feature、P
模型或 Q proxy。

---

## 8. 版本与产物 registry

```yaml
versions:
  authority_version: "2.1.0"
  era_definition_version: "2.0.0"
  sampling_grid_version: "ETF_5M_GRID_XSHG_2.0.0"
  outcome_definition_version: "2.1.0"
  q_definition_version: "2.1.0"
  state_definition_version: "2.1.0"
  phase_definition_version: "2.1.0"
  capability_definition_version: "2.1.0"
  target_definition_version: "2.1.0"
  predictor_registry_version: "2.1.0"
  physical_model_version: "2.1.0"
  qp_definition_version: "2.1.0"
  probability_definition_version: "2.1.0"
  acceptance_definition_version: "2.1.0"
  failure_ledger_version: "2.1.0"
  weather_snapshot_schema_version: "2.1.0"
```

V2.1 产物写入独立证据路径，不覆盖 V2.0 hashes：

```text
data/processed/v2_1/
outputs/v2_1_outcomes/
outputs/v2_1_q_acceptance/
outputs/v2_1_state_acceptance/
outputs/v2_1_physical_acceptance/
outputs/v2_1_qp_acceptance/
```

V2.0 可执行状态由 Git commit `5e4027a...` 与原产物 hash 保存；当前代码不提供
隐式 V2.0 fallback。所有 V2.1 artifact manifest 保存父 Authority/adjudication hash、
本 Authority hash、Git SHA、输入路径、版本、cohort、runtime 和输出 hash。

---

## 9. 施工顺序与停止规则

```text
H1 ERA revalidation
→ H2 outcome 2.1 rebuild
→ H3 settlement Q + isolated Confirmation
→ only if Q PASS: H4 two-sided state
→ only if H4 PASS: H5 physical forecasts
→ only if all P primaries PASS: H6 settlement-implied Q−P
```

任一核心门 `FAIL` 或 `INSUFFICIENT_EVIDENCE`：

1. 保存 deterministic artifacts、hash、failure ledger 和裁决；
2. 顶层保持 `V2_STATION_NOT_READY`；
3. 立即停止后续阶段；
4. 不通过选腿、仓位、退出、概率降门、策略收益、UNKNOWN/ABSTAIN 或另一个窗口
   给气象站补洞；
5. 不运行 candidate、forward shadow 或 external probe。

只有 H1–H6 依序达到各自冻结门，才允许产生 V2.1 retrospective station verdict；
它仍不等于 formal PIT、production、forward 或 calibrated-probability acceptance。

---

## 10. 冻结声明

从本文件独立提交开始：

- Settlement primary、14:56 comparator、15:00 spot、时间合同、Development/
  Confirmation 切分和 Q gate 全部冻结；
- H4–H6 继承的 vector、predictor registry、模型参数与 gates 全部冻结；
- 第一轮结果无论 PASS、FAIL 或证据不足，都按本合同报告；
- V2.0 Authority、裁决、ShortVol 源码与失败产物保持不变。
