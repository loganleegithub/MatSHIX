# MATSHIX V2.2 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_EXECUTION`
- Authority 版本：`2.2.0`
- 冻结时间：`2026-08-23T11:58:58Z`
- 冻结分支：`codex/matshix-weather-v2-2-local`
- 施工合同：`MATSHIX_V2_2_CONSTRUCTION_PLAN.md`
- 施工合同 SHA-256：`effaf0f0779dc0636a5b55814bcd935a47c6085cb751752b48c56f08b30d81b8`
- 基线清单：`MATSHIX_V2_2_BASELINE_MANIFEST.json`
- 基线清单 SHA-256：`f120300187c3b00b3038fbe73aa439fbc7ee03c6f3aea94a98d1f3e6dd43b6eb`
- 父 Authority：`MATSHIX_V2_1_1_AUTHORITY.md`
- 父 Authority SHA-256：`03c06e4c861bd313d0502ecbc25ee1e18511c7a080b8bc2fa1fb3eaf451c0705`
- 父裁决 SHA-256：`e18056289473b3979f10ae7377fc74582668e3bd394bff0b3d1e851f4446ea80`
- 父失败台账 SHA-256：`3f2fe224910caf2ed24177d47c1db321cce96740c33c56c5668591cdbd236c9b`

本 Authority 只授权 `CSI300_LOCAL` 历史研发、前瞻接受入口和 510500 结算价只读审计。
V2.1.1 的失败事实继续保留；本版本不追认历史正式接受，也不放行全局四品种站。

## 1. 范围与版本

```yaml
carrier_scope: CSI300_510300
economic_index_scope: CSI300
authority_version: 2.2.0
era_definition_version: 2.2.0
outcome_definition_version: 2.1.1
q_definition_version: 2.2.0
state_definition_version: 2.2.0
target_definition_version: 2.2.0
physical_model_version: 2.2.0
qp_definition_version: 2.2.0
acceptance_definition_version: 2.2.0
failure_ledger_version: 2.2.0
```

明确排除：上证 50、CSI500/STAR50 全局模型、market breadth、primary phase、条件概率、
candidate、策略 adapter 和外部收益探针。

## 2. Era 与证据等级

### 2.1 Development

```text
DEVELOPMENT_ERA = 2023-01-03..2026-06-05
price_proxy = MINUTE_CLOSE_1456
evidence_tier = RESEARCH_ONLY
vintage_kind = PROVIDER_RECONSTRUCTED
```

该区间已经参与诊断，只能产生 `DEVELOPMENT_*` 裁决。历史 95% exact availability
不再作为继续 H4–H6 的停止门；所有实际缺口仍保留 `UNKNOWN`，不得填补。

### 2.2 Forward

`FORWARD_ERA` 从本 Authority 冻结后的首个有效采集 session 开始。输入为 append-only
`data/raw/v2_2_forward/quotes.jsonl`，每条记录至少包含：

```text
session_date / instrument_kind / instrument_id / carrier_id
option_type / strike / expiry / contract_unit
last / bid / ask
source_timestamp / receive_timestamp / source
raw_receipt_sha256
```

ETF 与全部在场期权合约分别记录。`bid>0`、`ask>=bid` 才能形成 midpoint；last 与 midpoint
分别重建 Q。历史分钟数据不得写入该 cohort，也不得升级为 `FORMAL_PIT_QUOTES`。

## 3. 时间与 primary targets

```text
forecast_session = t
historical_q_known_at = t 14:56:59 Asia/Shanghai
consumer_decision_as_of = next exchange session 09:00 Asia/Shanghai
outcome begins = t+1 exchange session
```

Primary targets：

- H20 variance：`rv_variance_h20`，沿用 V2.1.1 5 分钟、午休、隔夜和复权算法；
- H10 downside：`max_down_log_move_h10 > q_expected_move_h10`；
- H10 upside：`max_up_log_move_h10 > q_expected_move_h10`。

标签只能使用 `t+1..target_end`。训练行只有在其 `outcome_available_at <= 当前 forecast
known_at` 时可用；当前行和未来行不得进入训练、percentile、imputation 或 threshold。

## 4. Q

### 4.1 历史 Q

- 价格源固定为 AETF 14:56 minute close；
- spot 为同刻未复权 ETF close，strike、option price 与 spot 位于同一名义坐标；
- 复用 V2.1.1 parity forward、model-free variance 和 total-variance interpolation；
- 只发布 H10/H20；target year fraction 沿用 exchange-session horizon 计算；
- 必须存在 exact target bracket；不得使用 nearest expiry；
- `q_variance` 为 252 日年化方差，`q_total_variance=q_variance*target_year_fraction`；
- 缺 bracket、wing 或有效价格时值为空并保存具体 status/issues。

每个 session 同时保存 surface facts：

```text
iv30_mf / fvol_30_90 / term_log_ratio_30_90
down_skew25 / up_skew25 / wing_dominance
surface_status / valid_strikes / parity_pair_count
observation_time / known_at / evidence_tier
```

### 4.2 前瞻 Q robustness

primary=`14:56 as-of last`，comparator=`14:56 bid/ask midpoint`。正式 Q 必须全部满足：

```text
paired exact H20 rows >= 126
paired exact H20 coverage >= 70%
median absolute relative q_variance delta <= 5%
p90 absolute relative q_variance delta <= 15%
exact-bracket availability agreement >= 95%
wing dominant-side agreement >= 90%
90% moving-date-block CI of median signed delta within [-5%, +5%]
```

bootstrap 固定 2,000 次、20-session block、seed `2026082300`。任一可评价门不满足为
`FAIL`；样本或 coverage 不足为 `INSUFFICIENT_EVIDENCE`。

## 5. H4 `CSI300_LOCAL` 天气

### 5.1 Causal percentile

所有 percentile 只使用当前日前最多 504 个有限值，当前排除，至少 126 个 reference，
使用 mid-rank，输出范围 0–1。正负方向分别计算：

```text
p_positive_etf_return_1d = percentile(etf_return_1d)
p_negative_etf_return_1d = percentile(-etf_return_1d)
p_positive_etf_return_5d = percentile(etf_return_5d)
p_negative_etf_return_5d = percentile(-etf_return_5d)
p_negative_d5_log_iv30 = percentile(-d5_log_iv30)
p_negative_d5_iv_vol_of_vol20 = percentile(-d5_iv_vol_of_vol20)
p_negative_d5_fvol_30_90 = percentile(-d5_fvol_30_90)
p_negative_d5_down_skew25 = percentile(-d5_down_skew25)
p_negative_d5_up_skew25 = percentile(-d5_up_skew25)
```

其余 `p_d1_log_iv30`、`p_d5_log_iv30`、`p_iv_vol_of_vol20`、两侧 skew 及 d5 skew
percentile 沿用 V2 定义。

### 5.2 Vector

```text
common_iv_shock
  = 100*(0.45*p_d1_log_iv30
        +0.30*p_d5_log_iv30
        +0.25*p_iv_vol_of_vol20)

downside_price_shock
  = 0.60*common_iv_shock + 40*p_negative_etf_return_1d
upside_price_shock
  = 0.60*common_iv_shock + 40*p_positive_etf_return_1d

down_tail = 100*(0.65*p_down_skew25 + 0.35*p_d5_down_skew25)
up_tail   = 100*(0.65*p_up_skew25   + 0.35*p_d5_up_skew25)

down_tail_persistence
  = 100*count(down_tail>=60 over current/prior 5 sessions)/5
up_tail_persistence
  = 100*count(up_tail>=60 over current/prior 5 sessions)/5

variance_repair
  = 100*(0.50*p_negative_d5_log_iv30
        +0.30*p_negative_d5_iv_vol_of_vol20
        +0.20*p_negative_d5_fvol_30_90)

downside_repair
  = 100*(0.50*p_negative_d5_down_skew25
        +0.30*p_positive_etf_return_5d
        +0.20*p_negative_d5_iv_vol_of_vol20)

upside_repair
  = 100*(0.50*p_negative_d5_up_skew25
        +0.30*p_negative_etf_return_5d
        +0.20*p_negative_d5_iv_vol_of_vol20)

term_repair = 100*p_negative_d5_fvol_30_90
```

任一公式的必需分量缺失则该值为 `UNKNOWN`。Persistence 必须有完整 5-session window。
`market_breadth=NOT_APPLICABLE`，`primary_phase=NOT_APPLICABLE`，两者不得进入模型。

## 6. H5 P predictor registry

### 6.1 通用顺序 OOF

- carrier-specific，只用 510300；
- 每次训练最多使用此前 1,260 个 outcome-complete rows，最少 252；
- 当前预测所需 H10/H20 Q 必须 exact，H4 vector 必须完整；否则 C2 不发布；
- 训练连续特征按训练窗 median impute、mean/std 标准化；当前行使用同一变换；
- 任一训练标准差为 0 则模型为 `UNOBSERVABLE`；
- Ridge：`alpha=1.0`；
- Logistic：L2、`C=1.0`、`solver=lbfgs`、`class_weight=None`、`max_iter=2000`；
- 不做 feature/model/threshold search；
- Logistic 只发布 `decision_function` raw score，不称为 probability。

Lag features 均截止 t−1：

```text
log_rv_d1_lag1 = log(252*daily_total_variance[t-1])
log_mean_rv_d5_lag1 = log(252*mean(daily_total_variance[t-5:t-1]))
log_mean_rv_d22_lag1 = log(252*mean(daily_total_variance[t-22:t-1]))
```

Path lag 为 t−5/t−20 至 t−1 的日内 adjusted path 最大上/下移动和 overnight gap 最大值；
窗口不完整则为空。

### 6.2 H20 variance

```yaml
B0_ROLLING_CLIMATOLOGY:
  target: log(max(rv_variance_h20, 1e-12))
  history: prior 252..504 complete targets
B1_EWMA94:
  recurrence: variance_t=0.94*variance_t-1+0.06*return_t^2
  output: 252*variance_t
B2_HAR_RV:
  kind: ridge_log_variance
  features: [log_rv_d1_lag1, log_mean_rv_d5_lag1, log_mean_rv_d22_lag1]
C2_HAR_Q_WEATHER:
  kind: ridge_log_variance
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
    - log_q_variance_h20
    - q_term_log_ratio_h10_h20
    - common_iv_shock
    - downside_price_shock
    - upside_price_shock
    - down_tail
    - up_tail
    - down_tail_persistence
    - up_tail_persistence
    - variance_repair
    - downside_repair
    - upside_repair
    - term_repair
```

C2 的 80% interval 使用当次训练 residual 在 log scale 的 causal 10%/90% empirical
quantile。少于 252 residual 不发布 interval。

### 6.3 H10 upside/downside

每侧分别拟合：

```yaml
B0_ROLLING_BASE_RATE:
  output: (positives+1)/(n+2), prior 252..504 complete targets
B1_REALIZED_PATH:
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
    - past_side_max_move_d5_lag1
    - past_side_max_move_d20_lag1
    - past_side_overnight_gap_d20_lag1
C2_LOCAL_Q_SIDE_WEATHER:
  features:
    - B1_REALIZED_PATH features
    - log_q_variance_h10
    - q_term_log_ratio_h10_h20
    - side_tail
    - side_raw_wing_skew
    - side_tail_persistence
    - side_repair
```

`side_tail_breadth` 被明确删除。训练除 252 rows 外还要求至少 20 positives 与 20
negatives。up/down 独立，不平均、不互相抵消。

### 6.4 Causal score percentile

C2 raw score percentile 只用此前同模型最多 504 个 score，当前排除，至少 126，mid-rank。
Percentile 不是 probability。

## 7. H6 Q−P

仅在 H20 variance P gate PASS 后判定：

```text
qp_variance_premium_h20 = q_variance_h20 - p_c2_variance_h20
qp_interval_low = q_variance_h20 - p_interval_high
qp_interval_high = q_variance_h20 - p_interval_low
ex_post_q_minus_realized = q_variance_h20 - rv_variance_h20
```

Q−P causal percentile 使用此前最多 504、至少 126 个有限 gap，当前排除。`sign_confident`
仅在 interval 全部大于 0 或全部小于 0 时为 true。

## 8. Development acceptance

### 8.1 统计协议

```text
bootstrap_kind = MOVING_DATE_BLOCK
repetitions = 2000
block_length_sessions = 20
confidence = 90%
seed_variance = 2026082301
seed_upside = 2026082302
seed_downside = 2026082303
seed_qp = 2026082304
QLIKE(y,f) = y/f - ln(y/f) - 1
```

coverage 分母为：target 已完成且在该日已有至少 252 个历史可训练 target 的 forecast
opportunities；分子为对应 C2 有限输出。

### 8.2 H20 variance gate

在 C2、B1、B2 与 outcome 全部有限的 paired rows 上：

```text
paired QLIKE skill = 1-mean(QLIKE_C2)/min(mean(QLIKE_B1),mean(QLIKE_B2)) >= 2%
90% block-bootstrap skill lower bound > 0
abs normalized bias <= 20%
80% interval empirical coverage in [65%,95%]
eligible forecast coverage >= 70%
all C2 forecasts finite and >0
```

单 carrier 本版不重复应用多 carrier 35% bias 条款。

### 8.3 H10 path gate

每侧分别满足：

```text
Spearman(raw_score, future_breach) > 0
causal top-10% alert capture lift > 1
90% block-bootstrap lower bound >0 for Spearman OR >1 for capture lift
eligible score coverage >= 70%
completed labels include >=20 positives and >=20 negatives
leave-one-positive-event-cluster-out Spearman >=0 in every fold with >=20 rows
```

正例 forecast 的 target windows 相交时合并为同一 event cluster。Top-10% alert 使用此前
至少 126、最多 504 个 C2 score 的 causal percentile。

### 8.4 Q−P gate

```text
Spearman(qp_gap, ex_post_q_minus_realized) > 0
causal top-minus-bottom quintile mean difference > 0
90% block-bootstrap lower bound > 0 for at least one primary statistic
sign-confident coverage >= 30%
eligible Q−P coverage >= 70%
```

### 8.5 裁决

每维只允许 `PASS / FAIL / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE`。工程、H20 P、
H10 up、H10 down、Q−P 全部 PASS 才可写 `DEVELOPMENT_PASS`。任一可评价门失败为
`DEVELOPMENT_FAIL`；样本不足为 `INSUFFICIENT_EVIDENCE`。

历史顶层最高为 `V2_2_LOCAL_RESEARCH_BUILT`，不得写 `FORWARD_ACCEPTED`。

## 9. 工程门

- Authority、plan、baseline 和父失败证据 hash 全部匹配；
- 输入列名和代码静态扫描均无 P&L、NAV、position、leg、exit 或策略收益；
- ledger 只含 `CSI300_510300`；
- Q 缺口保持原 status/空值；
- `market_breadth`、`primary_phase` 始终 `NOT_APPLICABLE`；
- future mutation invariance、up/down mirror 和 known-at purge tests 通过；
- 同一输入重放的规范化 Parquet/JSON hash 一致。

任一失败为 `V2_2_LOCAL_NOT_READY`，停止 `CSI300_LOCAL` 后续阶段。

## 10. 510500 settlement audit

审计只读 2025 数据，固定执行：

1. expiry/DTE 的 parity 隐含贴现与 rejection reason；
2. standard/non-standard、contract unit 与同族配对一致性；
3. settlement 与 14:56 minute close 的相同方法对照。

只允许：

- `DATA_FIELD_DEFECT`：可定位到原始字段、合约单位或错误 family pairing；
- `METHOD_MISMATCH`：字段一致，但 settlement 构造不满足当前 parity admissibility，而
  14:56 对照显著恢复；
- `INSUFFICIENT_EVIDENCE`：无法区分以上两者。

不得扫描或修改 discount range、配对距离、strike/expiry 容错。该支线结论不改变
`CSI300_LOCAL` 裁决。

## 11. 产物与停止边界

```text
data/processed/v2_2/csi300_local_ledger.parquet
outputs/v2_2_local/development_score.json
outputs/v2_2_local/failure_ledger.json
data/raw/v2_2_forward/quotes.jsonl
outputs/v2_2_forward/acceptance.json
outputs/v2_2_audit/settlement_parity_audit.json
outputs/v2_2_audit/settlement_parity_audit.md
```

禁止读取或修改 ShortVol 文件。任何核心门 FAIL/证据不足时停止受影响施工线；不得用
选腿、仓位、退出、概率降门或策略收益改变天气站结论。

## 12. 冻结声明

本文件独立提交后，era、targets、Q、H4 vector、P registry、Q−P 和 gates 全部冻结。
首次结果无论 PASS、FAIL 或不足，都按本文件裁决。任何语义修改必须先新建 Authority
版本并记录旧结果与 hash。
