# MATSHIX V2 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_EXECUTION`
- Authority 版本：`2.0.0`
- 冻结依据：人类已冻结的 `MATSHIX_V2_CONSTRUCTION_PLAN.md` 与阶段 A 缺陷裁决
- 冻结分支：`codex/matshix-weather-v2`
- Authority 父提交：`ca32d3bbe175c84ea16e3c9b265b679896d23c6e`（`audit: record MatSHIX V1 weather defects`）
- 施工合同 SHA-256：`785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f`
- 阶段 A 审计 SHA-256：`82cc910b9b1cb7c9b4b7f1faee7c008489ef219d0b30b335ee72b01891bc7251`
- V1 baseline manifest SHA-256：`d3432cf3a0401c4103fa16df6514250d22374a5749a21fe6b36e66f42c5edb63`

本文件是 MatSHIX V2 第一候选的唯一业务与验收 Authority。第一行语义代码修改只能发生在本文件独立提交之后。首次历史运行之后，target、feature、模型序列、阈值、样本门、校准门、failure 分类或外部探针接口均不得在本版本内修改。任何修改必须升级 Authority、definition/model version 与 candidate ID，重建完整因果历史，并保留旧候选证据。

---

## 1. 产品定义与不可跨越边界

MatSHIX V2 是一个研究级 ETF 期权市场气象站，不是策略、交易许可或仓位引擎。它分开发布：

1. `Q`：期权曲面在时点 t 隐含的方差、期限与双翼事实；
2. `P`：只使用时点 t 已知事实，对未来真实方差与上下路径风险作出的物理测度预测；
3. `Q_MINUS_P`：同载体、同目标窗口、同单位的隐含方差减物理预测方差；
4. `market_vector`：当前双侧天气事实；
5. `primary_phase`：仅供人类阅读的有损摘要；
6. `model_acceptance`：每项能力独立的工程、样本、score、概率与前向状态。

下列对象永远不属于 V2 weather snapshot：

```text
strategy_permission
allow_or_block
option_structure
selected_legs
position
risk_unit
order
fill_scenario
strategy_cost
strategy_pnl
account_nav
```

气象站施工与站内验收不得读取交易账本、ShortVol 逐日收益、选腿、仓位、退出、成本或 NAV。历史策略结果不得成为特征、阈值、模型选择、failure 标签或 gate 输入。

当前 AETF 历史只具备：

```text
evidence_tier = RESEARCH_ONLY
vintage_kind = PROVIDER_RECONSTRUCTED
history_evidence_kind = RETROSPECTIVE_WALK_FORWARD
formal_publication_status = NOT_ELIGIBLE
```

分钟 close 不得称为 bid/ask、可成交 mid、正式 PIT 或 production evidence。

---

## 2. 时间、因果与可用性合同

对 `forecast_session=t`：

```text
input_cutoff                 = t 14:56:59 Asia/Shanghai
input_known_at               = t 14:56:59 Asia/Shanghai
consumer_decision_as_of      = next_exchange_session(t) 09:00:00 Asia/Shanghai
target_start_session         = next_exchange_session(t)
target_end_session(H)        = add_exchange_sessions(t, H)
outcome_available_at(H)      = exchange_decision_as_of(target_end_session(H))
```

约束：

- 预测值、transform、causal percentile 和模型系数只能使用 `input_known_at` 已知的输入；
- outcome 标签只使用 `target_start_session` 至 `target_end_session` 的观察；
- 模型训练行必须满足该行 `outcome_available_at <= current consumer_decision_as_of`；
- 同时还必须满足 `target_end_position <= current prediction_position`，purge 至少等于目标 horizon；
- 当前日不得进入自身 percentile、scale、imputer、climatology 或 calibration reference；
- 缺日、停牌、复权冲突、末端不完整或必需 bar 缺失为 `CENSORED`/`UNKNOWN`，绝不记 0；
- future input mutation 不得改变过去 input、Q、P forecast、score、OOF 或已发布 revision；
- `known_at`、`consumer_decision_as_of` 与 `outcome_available_at` 必须同时保存，不能互相替代。

---

## 3. 上市时代 Authority

以下 YAML 块是 V2 era registry 的机器真值：

```yaml
era_definition_version: "2.0.0"
eras:
  - coverage_regime: ERA_A_50_ONLY
    start_session: 2015-02-09
    end_session: 2019-12-22
    available_carriers: [SSE50_510050]
    available_carrier_count: 1
    market_breadth_allowed: false
  - coverage_regime: ERA_B_50_300
    start_session: 2019-12-23
    end_session: 2022-09-18
    available_carriers: [SSE50_510050, CSI300_510300]
    available_carrier_count: 2
    market_breadth_allowed: false
  - coverage_regime: ERA_C_50_300_500
    start_session: 2022-09-19
    end_session: 2023-06-04
    available_carriers: [SSE50_510050, CSI300_510300, CSI500_510500]
    available_carrier_count: 3
    market_breadth_allowed: false
  - coverage_regime: ERA_D_FOUR_CARRIERS
    start_session: 2023-06-05
    end_session: null
    available_carriers: [SSE50_510050, CSI300_510300, CSI500_510500, STAR50_588000]
    available_carrier_count: 4
    market_breadth_allowed: true
```

首个上市日必须由 AETF `opt_basic.parquet` 独立复核为：

```text
SSE50_510050   2015-02-09
CSI300_510300  2019-12-23
CSI500_510500  2022-09-19
STAR50_588000  2023-06-05
```

每条 Q/P/Q−P/state 记录必带：

```text
coverage_regime
available_carrier_count
carrier_id
economic_index_id
listing_date
listing_age_sessions
data_status
```

`NOT_LISTED` 是独立状态，不是 `MISSING`、`UNKNOWN` 或 0。ERA A/B/C 只允许 carrier-local 事实；不得对可用载体重新归一化后称为“四市场 Breadth”。市场层 Breadth 只允许在 ERA D 且四载体必需事实全部可观察时发布，否则为 `NOT_APPLICABLE` 或 `UNKNOWN`。

---

## 4. 单位与数学定义

### 4.1 基础单位

```text
log_return                 = ln(adjusted_mark_t / adjusted_mark_t-1)
variance                   = dimensionless squared log return
annualized_variance        = variance per 252 exchange sessions
volatility                 = sqrt(annualized_variance)
iv_decimal                 = iv_percent / 100
total_variance(T)          = annualized_q_variance(T) * ACT/365F_year_fraction(T)
```

所有机器值必须显式保存 `measure_id` 与 `unit`。冻结单位枚举：

```text
ANNUALIZED_VARIANCE_252
TOTAL_VARIANCE_ACT365F
DECIMAL_VOLATILITY_SQRT_ANNUALIZED_VARIANCE
LOG_RETURN
BOOLEAN
PERCENTILE_0_1
SCORE_0_100
```

V1 golden 恒等式保留但不作为 V2 主 Q−P：

```text
vrp_ewma94 = (iv30_mf / 100)^2 - rv_forecast30
```

### 4.2 日内与隔夜真实方差

复权 ETF mark 固定为 `close * adj_factor`。每个目标 session 的 5 分钟网格为：

```text
morning endpoints    = 09:30, 09:35, ..., 11:30
afternoon endpoints  = 13:05, 13:10, ..., 15:00
```

每个 endpoint 使用对应五分钟桶内最后一个有效分钟 close；禁止跨桶 forward fill。日内收益包括：

1. 上午相邻 endpoint；
2. `11:30 -> 13:05` 一次性午间/重开收益；
3. 下午相邻 endpoint。

因此 `expected_bar_count=48` 个日内收益。午休不能被展开成多个 0 或伪 bar。隔夜收益为前一 exchange session 15:00 复权 mark 到当前 session 09:30 复权 mark。公司行动日只有复权因子存在、有限且 adjusted mark 连续性手检通过时可用。

```text
daily_intraday_variance = sum(48 valid intraday_5m_log_return^2)
daily_overnight_variance = overnight_log_return^2
daily_total_variance = daily_intraday_variance + daily_overnight_variance

rv_variance_h = (252 / H) * sum(daily_total_variance over target sessions)
rv_volatility_h = sqrt(rv_variance_h)
rv_intraday_h = (252 / H) * sum(daily_intraday_variance)
rv_overnight_h = (252 / H) * sum(daily_overnight_variance)
```

一个目标 session 少于 48 个有效日内收益、缺 overnight、停牌、复权冲突或目标窗口缺任一 exchange session，则整个 H outcome 为 `CENSORED`；不插值、不缩放剩余 bar。

### 4.3 上下路径 outcome

路径基准为 t 日 14:56 的复权 ETF mark。未来窗口使用每个目标 session 的有效 5 分钟 endpoint 与 15:00 close：

```text
max_up_log_move_h        = max(ln(future_mark / frozen_mark_t_1456), 0)
max_down_log_move_h      = max(-ln(future_mark / frozen_mark_t_1456), 0)
close_to_close_return_h  = ln(target_end_1500 / frozen_mark_t_1456)
overnight_gap_max_h      = max(abs(overnight_log_return))
```

up/down 是正交的非负幅度，不相减、不用单一绝对值替代。缺失规则与 RV 相同。

### 4.4 同期限 Q

目标年分数：

```text
target_year_fraction_h = ACT/365F(input_cutoff, target_end_session 15:00)
```

主 cohort 只能使用两个有效期权 expiry 的 model-free total variance 严格夹逼该目标年分数：

```text
T_lower <= target_year_fraction_h <= T_upper
q_total_variance_h = linear interpolation of total variance between T_lower and T_upper
q_variance_h = q_total_variance_h / target_year_fraction_h
q_expected_move_h = sqrt(q_total_variance_h)
q_term_log_ratio_h10_h20 = ln(q_variance_h20 / q_variance_h10)
```

`T_lower == target == T_upper` 允许 exact maturity。没有严格夹逼时 `horizon_status=NO_EXACT_BRACKET`，主 cohort Q 为空；`NEAREST_EXPIRY_PROXY` 只能进入 robustness/coverage，不得进入 primary target、P 主验收或 Q−P。

路径标签：

```text
upside_path_breach_h = max_up_log_move_h > q_expected_move_h
downside_path_breach_h = max_down_log_move_h > q_expected_move_h
```

仅在对应 H 的 exact Q 与完整 raw path outcome 同时存在时为 0/1；否则 `UNKNOWN`，不是 0。

### 4.5 Q−P

```text
qp_variance_premium_h20 = q_variance_h20 - p_expected_realized_variance_h20
qp_interval_low = q_variance_h20 - p_forecast_interval_high
qp_interval_high = q_variance_h20 - p_forecast_interval_low
```

状态：

```text
RICH_CONFIDENT   if qp_interval_low > 0
THIN_CONFIDENT   if qp_interval_high < 0
SIGN_UNCERTAIN   if qp_interval_low <= 0 <= qp_interval_high
UNOBSERVABLE     if exact Q or accepted P is unavailable
```

机器字段固定为 `qp_variance_premium_state_h20`。事后验证量只在 outcome 可用后追加：

```text
ex_post_q_minus_realized_h20 = q_variance_h20 - realized_variance_h20
p_forecast_error_h20 = p_expected_realized_variance_h20 - realized_variance_h20
```

二者不得回流到当日 snapshot 或 feature。

---

## 5. Capability 与 target registry

以下 YAML 块是首批 capability 的机器真值：

```yaml
capability_definition_version: "2.0.0"
capabilities:
  - capability_id: variance_hazard_h20
    target_id: realized_variance_h20
    target_definition: annualized realized variance over next 20 exchange sessions
    measure: P
    status: PRIMARY
    target_type: CONTINUOUS
    horizon_sessions: 20
  - capability_id: upside_path_hazard_h10
    target_id: upside_path_breach_h10
    target_definition: future H10 max upside log move exceeds frozen exact-Q H10 expected move
    measure: P
    status: PRIMARY
    target_type: BINARY
    horizon_sessions: 10
  - capability_id: downside_path_hazard_h10
    target_id: downside_path_breach_h10
    target_definition: future H10 max downside log move exceeds frozen exact-Q H10 expected move
    measure: P
    status: PRIMARY
    target_type: BINARY
    horizon_sessions: 10
  - capability_id: qp_variance_premium_h20
    target_id: q_variance_h20_minus_p_expected_realized_variance_h20
    target_definition: same-carrier same-H20 annualized Q variance minus accepted P forecast
    measure: Q_MINUS_P
    status: PRIMARY
    target_type: CONTINUOUS_DERIVED
    horizon_sessions: 20
  - capability_id: variance_hazard_h5
    target_id: realized_variance_h5
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: variance_hazard_h10
    target_id: realized_variance_h10
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 10
  - capability_id: upside_path_hazard_h5
    target_id: upside_path_breach_h5
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: downside_path_hazard_h5
    target_id: downside_path_breach_h5
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: jump_hazard_1d
    target_id: next_session_overnight_gap
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 1
  - capability_id: q_surface_persistence_h5
    target_id: future_q_surface_persistence_h5
    measure: Q
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: q_surface_persistence_h20
    target_id: future_q_surface_persistence_h20
    measure: Q
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 20
  - capability_id: p_realized_hazard_persistence_h5
    target_id: future_realized_hazard_persistence_h5
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: p_realized_hazard_persistence_h20
    target_id: future_realized_hazard_persistence_h20
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 20
  - capability_id: q_surface_repair_h5
    target_id: future_q_surface_repair_h5
    measure: Q
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
  - capability_id: p_hazard_repair_h5
    target_id: future_realized_hazard_repair_h5
    measure: P
    status: SCORE_ONLY_RESEARCH_SHADOW
    horizon_sessions: 5
```

所有 shadow capability 只允许 score，`conditional_probability=null`，不阻断首批核心施工，也不得在 Dashboard 中伪装成正式概率。

V1 五事件裁决：

```text
cross_market_iv_jump_1d             -> q_surface_transitions/v1_reference_only
broad_pressure_onset_5d             -> q_surface_transitions/v1_reference_only
systemic_acute_stress_5d            -> q_surface_transitions/v1_reference_only
persistent_cross_market_stress_20d  -> q_surface_transitions/v1_reference_only
fast_repair_5d                       -> q_surface_transitions/v1_reference_only
```

它们不在 V2 runtime 平行执行，没有 executable alias，不作为 V2 primary outcome 或 probability target。

---

## 6. Outcome ledger 合同

粒度：`carrier_id × forecast_session × horizon_sessions`。首版计算 H5/H10/H20 全部连续 outcome，并保存：

```text
forecast_session
input_known_at
consumer_decision_as_of
target_start_session
target_end_session
outcome_available_at
carrier_id / economic_index_id
coverage_regime / available_carrier_count / listing_age_sessions
date_cluster_id
overlap_cluster_id
rv_variance_h / rv_volatility_h
rv_intraday_h / rv_overnight_h
max_up_log_move_h / max_down_log_move_h
close_to_close_return_h / overnight_gap_max_h
q_variance_h / q_expected_move_h / q_horizon_status
upside_path_breach_h / downside_path_breach_h
valid_bar_count / expected_bar_count
sampling_grid_version
corporate_action_status
label_status / data_status / issues
outcome_definition_version
```

`date_cluster_id=forecast_session`，用于四载体同日 block。`overlap_cluster_id` 对同 carrier、同 H 且 target window 相交的连续 forecast 使用同一确定性 cluster ID。Outcome builder 的 import、参数、输入 schema 与运行日志中均不得出现 phase、weather score、probability、strategy 或 P&L 字段。

---

## 7. Q Authority 与价格代理稳健性

主研究价格：`MINUTE_CLOSE_1456`。复用 V1 已通过数学测试的 parity forward/discount、model-free variance、25D put/call、total-variance interpolation，不重写定价核心。

每条 Q fact 至少保存：

```text
price_proxy
exact_or_proxy
target_calendar_days / target_year_fraction
q_total_variance / q_annualized_variance
valid_strikes
put_count / call_count
parity_pair_count
liquidity_status
surface_status
method
sensitivity_delta
unit
known_at
definition_version
```

冻结 robustness proxy：`NEAR_CLOSE_PRINT_VWAP_1452_1456`。

- 只使用 14:52:00 至 14:56:59 的正成交分钟；
- 每合约 `vwap=sum(amount)/sum(volume*contract_unit)`；
- `volume>0`、`amount>0`、contract unit 有效；
- VWAP 必须落在窗口原始分钟 `min(low)` 与 `max(high)` 内，否则该合约不可用；
- 不使用日结算、future outcome 或策略结果；
- robustness 只重建同日 Q，不择优、不替换主 proxy。

Q robustness gate 预冻结为：

```text
paired eligible coverage >= 70%
median absolute relative delta of q_variance_h20 <= 5%
90th percentile absolute relative delta <= 15%
exact-bracket availability agreement >= 95%
DownTail-vs-UpTail dominant-side agreement >= 90%
```

任一阈值不满足为 `Q=FAIL`；因 paired coverage 或数据不足无法评价为 `Q=INSUFFICIENT_EVIDENCE`。缺 bid/ask 只限制 evidence tier，不允许伪造 spread/mid。

---

## 8. 双侧 state vector 与 phase Authority

### 8.1 Causal percentile

所有 raw-to-score percentile：同 carrier、同 definition、同 coverage regime；只用此前最多 504 个有限值，当前日排除；至少 126 个 reference 才发布。值域为 0–100。缺任一必需分量严格为 `UNKNOWN`，不重新归一化、不复制另一侧、不填 0。

### 8.2 Carrier-local vector

```text
common_iv_shock
  = 100 * (0.45*p_d1_log_iv30 + 0.30*p_d5_log_iv30 + 0.25*p_iv_vol_of_vol20)

downside_price_shock
  = 0.60*common_iv_shock + 40*p_negative_etf_return_1d

upside_price_shock
  = 0.60*common_iv_shock + 40*p_positive_etf_return_1d

down_tail
  = 100 * (0.65*p_down_skew25 + 0.35*p_d5_down_skew25)

up_tail
  = 100 * (0.65*p_up_skew25 + 0.35*p_d5_up_skew25)

down_tail_persistence
  = 100 * count(down_tail >= 60 over current/prior 5 sessions) / 5

up_tail_persistence
  = 100 * count(up_tail >= 60 over current/prior 5 sessions) / 5

variance_repair
  = 100 * (0.50*p_negative_d5_log_iv30
           + 0.30*p_negative_d5_iv_vol_of_vol20
           + 0.20*p_negative_d5_fvol_30_90)

downside_repair
  = 100 * (0.50*p_negative_d5_down_skew25
           + 0.30*p_positive_etf_return_5d
           + 0.20*p_negative_d5_iv_vol_of_vol20)

upside_repair
  = 100 * (0.50*p_negative_d5_up_skew25
           + 0.30*p_negative_etf_return_5d
           + 0.20*p_negative_d5_iv_vol_of_vol20)

term_repair = 100 * p_negative_d5_fvol_30_90
```

正/负 return percentile 分别从 `return` 与 `-return` 的独立 causal distribution 计算；一侧高分不强制另一侧低分。过去五日上涨只能进入 `downside_repair` 的确认或 narrative counter-evidence，不是 `up_tail` 或上行 phase 的必要条件。

### 8.3 Market breadth

仅 ERA D 发布。沿用固定经济权重：SSE50 0.20、CSI300 0.20、CSI500 0.30、STAR50 0.30；segment 为 large=(SSE50+CSI300)/2、mid=CSI500、tech=STAR50。

对每一 side：

```text
index_side_active = side_price_shock >= 65 or side_tail >= 70
segment_side_active = segment(side_price_shock) >= 65 or segment(side_tail) >= 70
side_tail_breadth = 100 * active_segment_count / 3
side_systemic = all 3 segments active
side_broad = at least 2 of 3 segments active
```

同时发布 `down_tail_breadth`、`up_tail_breadth`、各 index/segment tri-state 与有效计数。部分载体不重新归一化；任一 segment 必需值缺失则 market breadth 为 `UNKNOWN`。

### 8.4 Human phase

机器消费者不得以 phase 代替 vector。`primary_phase` 只按下列顺序产生一个摘要：

```text
UNKNOWN
  if required ERA-D market vector is incomplete
TWO_SIDED_CONVEXITY_BUILDING
  if down_tail >= 75 and up_tail >= 75
     and down_tail_breadth >= 33.3333 and up_tail_breadth >= 33.3333
UPTAIL_BUILDING
  if (upside_price_shock >= 65 or up_tail >= 75)
     and up_tail_breadth >= 33.3333
SYSTEMIC_ACUTE_STRESS
  if downside_price_shock >= 85 and down_tail_breadth == 100
LOCALIZED_ACUTE_STRESS
  if downside_price_shock >= 85 or down_tail >= 85
BROAD_PERSISTENT_PRESSURE
  if down_tail_persistence >= 60 and down_tail_breadth >= 66.6667
BROAD_PRESSURE
  if downside_price_shock >= 65 and down_tail_breadth >= 66.6667
REPAIR_IN_PROGRESS
  if max(variance_repair, downside_repair, upside_repair, term_repair) >= 75
     and max(downside_price_shock, upside_price_shock) < 85
BALANCED_MARKET
  otherwise
```

Hysteresis：风险 phase 下降为更低风险 phase 需连续两次 `consumer_decision_as_of` 满足新 phase；风险升级即时。`UNKNOWN` 即时传播且不参与 hysteresis。`UPTAIL_BUILDING` 不要求过去 ETF 已上涨。

---

## 9. P 模型与 predictor registry

### 9.1 通用训练规则

- carrier-specific 为正式模型；跨 carrier panel 只可另立 Challenger，本版本不使用；
- 所有连续 predictor 在训练窗内 median impute、mean/std 标准化；当前及未来行不参与；
- 标准差为 0 的 predictor 使该模型 `UNOBSERVABLE`，不得自动删除；
- 连续 ridge 固定 `alpha=1.0`，target=`log(max(rv_variance_h20, 1e-12))`；
- 二元 Logistic 固定 L2、`C=1.0`、`solver=lbfgs`、`class_weight=None`、`max_iter=2000`；
- 不做 stepwise、L1 筛选、树模型、自动 feature search、自动 threshold search 或收益筛选；
- 训练最多使用此前 1,260 个 outcome-complete rows；score 最少 252 rows；
- B0 rolling climatology 使用此前最多 504、至少 252 个完整 target 的 log mean；
- B0 path base rate 使用此前最多 504、至少 252 个完整 target，并固定为 `(positive+1)/(n+2)`；
- Path Logistic 训练还要求至少 20 个正例与 20 个负例，否则 `INSUFFICIENT_HISTORY`；
- 80% 连续预测区间使用训练 residual 的 causal 10%/90% empirical quantile，在 log scale 相加后 exponentiate；少于 252 residual 不发布；
- 所有随机重采样使用固定 seed，按日期整体 block，不把四载体当四倍独立样本。

### 9.2 连续 H20 variance 模型

输入均相对 forecast t，`rv_*` lag 窗口最多到 t−1 完整 outcome：

```yaml
variance_models:
  B0_ROLLING_CLIMATOLOGY:
    kind: mean_log_target
    features: []
  B1_EWMA94:
    kind: frozen_ewma94
    features: [ewma94_variance_at_t]
  B2_HAR_RV:
    kind: ridge_log_variance
    features: [log_rv_d1_lag1, log_mean_rv_d5_lag1, log_mean_rv_d22_lag1]
  C1_HAR_Q:
    kind: ridge_log_variance
    features:
      - log_rv_d1_lag1
      - log_mean_rv_d5_lag1
      - log_mean_rv_d22_lag1
      - log_q_variance_h20
      - q_term_log_ratio_h10_h20
  C2_HAR_Q_WEATHER:
    kind: ridge_log_variance
    status: PRIMARY_CHALLENGER
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

`C2_HAR_Q_WEATHER` 是唯一可晋升的首版 variance Challenger；C1 只作 Q 增量归因。C2 不通过时不得事后改选 C1、删 vector 字段或调 alpha 来取得 PASS。

`B1_EWMA94` 完全沿用 V1：按 carrier 的 14:56 复权 close-to-close log return，以 252 个连续 return 的样本方差初始化，随后 `variance_t=0.94*variance_t-1+0.06*return_t^2`，并发布 `252*variance_t`。缺失 return 会清空递推并重新等待 252 个连续值。

### 9.3 H10 上下路径模型

`side` 分别替换为 `up`/`down`，两侧独立验收：

```yaml
path_models:
  B0_ROLLING_BASE_RATE:
    kind: causal_beta_smoothed_base_rate
    features: []
  B1_REALIZED_PATH:
    kind: logistic_score
    features:
      - log_rv_d1_lag1
      - log_mean_rv_d5_lag1
      - log_mean_rv_d22_lag1
      - past_side_max_move_d5_lag1
      - past_side_max_move_d20_lag1
      - past_side_overnight_gap_d20_lag1
  C1_Q_SIDE:
    kind: logistic_score
    features:
      - log_rv_d1_lag1
      - log_mean_rv_d5_lag1
      - log_mean_rv_d22_lag1
      - past_side_max_move_d5_lag1
      - past_side_max_move_d20_lag1
      - past_side_overnight_gap_d20_lag1
      - log_q_variance_h10
      - q_term_log_ratio_h10_h20
      - side_tail
      - side_raw_wing_skew
  C2_Q_SIDE_WEATHER:
    kind: logistic_score
    status: PRIMARY_CHALLENGER
    features:
      - log_rv_d1_lag1
      - log_mean_rv_d5_lag1
      - log_mean_rv_d22_lag1
      - past_side_max_move_d5_lag1
      - past_side_max_move_d20_lag1
      - past_side_overnight_gap_d20_lag1
      - log_q_variance_h10
      - q_term_log_ratio_h10_h20
      - side_tail
      - side_raw_wing_skew
      - side_tail_breadth
      - side_tail_persistence
      - side_repair
```

`up` 使用 up_tail/up_skew25/up breadth/up persistence/up repair；`down` 使用 down_tail/down_skew25/down breadth/down persistence/down repair。C2 是唯一可晋升首版 Challenger；C1 只作 Q-side 增量归因。

Path lag feature 定义固定为：

```text
past_up_max_move_d5_lag1       = max positive daily log move over t-5..t-1
past_down_max_move_d5_lag1     = max negative daily log-move magnitude over t-5..t-1
past_up_max_move_d20_lag1      = same over t-20..t-1
past_down_max_move_d20_lag1    = same over t-20..t-1
past_up_overnight_gap_d20_lag1 = max positive overnight log gap over t-20..t-1
past_down_overnight_gap_d20_lag1 = max negative overnight gap magnitude over t-20..t-1
```

所有窗口只使用 t−1 及更早的完整日 outcome；缺任一必需日则 feature 为空，不按剩余天数缩放。

### 9.4 模型状态与 score percentile

```text
NOT_RUN
UNOBSERVABLE
INSUFFICIENT_HISTORY
RETROSPECTIVE_SCORE
BASE_RATE_ONLY
CALIBRATED_MODEL
FORWARD_SHADOW_ACCEPTED
```

三项稳定 score interface：

```text
p_realized_variance_hazard_percentile_h20
p_upside_path_breach_score_percentile_h10
p_downside_path_breach_score_percentile_h10
```

只使用此前同 carrier、definition、model、coverage regime 的 score 作 mid-rank；当前排除；最多 504、至少 126。必须同时保存 raw score、reference count 和 percentile。Percentile 不是 probability。

---

## 10. P、Q−P 与概率 acceptance gates

### 10.1 通用统计协议

```text
bootstrap_kind = MOVING_DATE_BLOCK
bootstrap_repetitions = 2000
bootstrap_block_length_sessions = max(20, target_horizon)
bootstrap_confidence = 90%
bootstrap_seed_variance = 2026082301
bootstrap_seed_upside = 2026082302
bootstrap_seed_downside = 2026082303
bootstrap_seed_qp = 2026082304
```

四载体同日整体进入同一 resample block。重叠窗口不视为独立样本。

指标公式冻结为：

```text
QLIKE(y, f) = y/f - ln(y/f) - 1
paired_qlike_skill = 1 - mean(QLIKE_C2) /
                         min(mean(QLIKE_B1), mean(QLIKE_B2))
capture_rate = positive event clusters with at least one top-10% alert /
               all positive event clusters
capture_lift = capture_rate / 0.10
qp_top_bottom_difference = mean(ex_post_q_minus_realized | causal_percentile>=0.80)
                           - mean(ex_post_q_minus_realized | causal_percentile<=0.20)
```

### 10.2 P variance H20 gate

以 C2 对 `min(B1_EWMA94 loss, B2_HAR_RV loss)` 的 paired row/date 比较：

```text
paired QLIKE skill >= 2%
90% moving-date-block bootstrap skill lower bound > 0
aggregate normalized bias abs((mean_forecast-mean_actual)/mean_actual) <= 20%
each carrier with >=60 eligible rows normalized bias absolute value <= 35%
80% interval empirical coverage in [65%, 95%]
eligible forecast coverage >= 70%
all forecasts finite and strictly positive
```

任一可评价阈值不满足为 `FAIL`；因样本/coverage 无法评价为 `INSUFFICIENT_EVIDENCE`。

### 10.3 P up/down path H10 score gate

每侧 C2 独立满足：

```text
Spearman(raw_score, future_breach) > 0
causal top-10% alarm capture lift > 1
90% block-bootstrap lower bound > 0 for Spearman
    OR > 1 for capture lift
eligible score coverage >= 70%
at least 20 positive and 20 negative completed outcomes for descriptive score gate
leave-one-event-cluster-out direction is non-negative in every fold with >=20 rows
```

up/down 不平均、不互相抵消。一个侧失败或不足即该 primary 失败或不足。

### 10.4 Q−P H20 gate

```text
Spearman(qp_gap, future_q_minus_realized) > 0
top-minus-bottom causal quintile mean difference > 0
90% date-block bootstrap lower bound > 0 for at least one primary statistic
sign-confident coverage >= 30%
eligible Q−P coverage >= 70%
no carrier with >=60 rows has a 90% upper bound below 0 for both primary statistics
```

P variance gate 未通过时 Q−P 自动为 `INSUFFICIENT_EVIDENCE`，不能由策略收益替代。

### 10.5 条件概率门

沿用 V1 顺序 OOF、Platt、Brier/ECE 与 moving-block 实现，不降低：

```text
minimum training samples = 504
minimum positives = 25
minimum negatives = 25
calibration samples = 252
calibration positives >= 20
calibration negatives >= 20
Brier Skill >= 2%
model LogLoss <= rolling-base LogLoss
ECE <= 8%
90% block-bootstrap Brier Skill lower bound > -2%
```

`BASE_RATE_ONLY` 时：

```text
model_status = BASE_RATE_ONLY
conditional_probability = null
base_rate = causal historical rate
```

未经校准的 Logistic 输出是 `raw_decision_score`，不得写入 probability。样本门不可达时为 `INSUFFICIENT_HISTORY`，不是降低门的理由。

---

## 11. DATA、OUTCOME、Q 与 STATE integrity gates

### 11.1 DATA/ERA

必须全部满足：

- contract-master 上市日与 Authority 四日一致；
- `NOT_LISTED`、`MISSING`、`UNKNOWN`、`CENSORED` 分开；
- carrier count、listing age、era 可逐行重放；
- partial era 不发布四市场 Breadth；
- `data_status=OK` 的必需字段完整；
- research proxy/PIT/许可边界诚实；
- future mutation invariance 通过；
- `ERA-001` 关闭。

### 11.2 OUTCOME

必须全部满足：

- 5 分钟、午休、隔夜、复权、H5/H10/H20 exchange-session handcheck；
- t 输入只生成 t+1 起目标；
- outcome availability 与 purge 无未来函数；
- 缺 bar/停牌/末端不完整严格 CENSORED；
- variance、volatility、total variance 单位手算通过；
- up/down 镜像 fixture 交换两侧；
- date/overlap cluster 可重放；
- outcome builder 静态与运行输入均没有 weather/strategy 字段；
- `OUTCOME-001` 关闭。

### 11.3 Q

必须全部满足：

- V1 parity/model-free variance/tenor/wing golden 不回归；
- H10/H20 exact bracket、target year fraction 与单位 handcheck；
- exact/proxy 永不混称；
- primary cohort 无 nearest-expiry；
- near-close robustness 达到第 7 节冻结门；
- 缺 bid/ask 不伪造 spread/mid；
- `HORIZON-001` 关闭，`UNIT-001` 保持 rejected golden。

### 11.4 TWO-SIDED STATE/TIMING

必须全部满足：

- carrier 与 market 的 up/down shock、tail、Breadth、persistence、repair 语义完整；
- 镜像 fixture 交换 up/down 结果；
- 上涨冲击不能仅因 return 符号被压为 calm；
- `UPTAIL_BUILDING` 不要求过去已上涨；
- phase 不遮蔽相反方向高 hazard；
- UNKNOWN 严格传播；
- 对冻结 up/down outcome clusters，V2 missed count 不高于 V1，median first-alert lag 不晚于 V1；
- 固定 causal top-10% alarm budget 下，V2 false-alarm rate 不高于 V1 加 5 个百分点；
- `UPSIDE-001`、`UPSIDE-002`、`TIMING-001`、`PHASE-001` 关闭。

---

## 12. Failure ledger Authority

### 12.1 事件簇

- variance extreme：同 carrier 的 `realized_variance_h20` 超过仅由此前已完成 outcome 构成的 causal 90% percentile；reference 最多 504、至少 126；
- path event：冻结的 `upside_path_breach_h10` / `downside_path_breach_h10`；
- 同 carrier、同 event direction、目标窗口相交的连续正例合并为一个 cluster；
- `event_cluster_id` 由 `carrier|event_id|first_target_start|last_target_end|definition_version` 的 canonical SHA-256 生成；
- 被评价行自身及未来 outcome 不进入 threshold。

### 12.2 Alert

- alarm budget：同 carrier/definition/model/regime causal score percentile `>=0.90`；reference 最多 504、至少 126；
- `alert_persistence_sessions=1`，一次 eligible alarm 即成为 first alert；
- `DETECTED_EARLY`：first alert 的 `consumer_decision_as_of <= event_cluster_start 09:00`；
- `DETECTED_LATE`：first alert 晚于 cluster start 09:00，但不晚于 cluster end 15:00；
- `MISSED`：cluster 期间存在 eligible score 但无 alarm；
- `ABSTAIN_DATA`：cluster 期间没有可评价 score，或 data/model/horizon 状态不足；
- `FALSE_ALARM`：alarm 的目标窗口不与任何同 carrier、同 direction event cluster 相交。

`ABSTAIN_DATA` 不计命中，必须报告 coverage 与最差 cluster 的 abstention share。每行保存 event/alert 日期、lead/lag、raw score/percentile、probability/base rate、Q/P/Q−P、vector、data/model status、drivers/counter-evidence 与分类原因。

---

## 13. Station acceptance 与停止规则

每个维度只允许：

```text
PASS
FAIL
INSUFFICIENT_EVIDENCE
NOT_APPLICABLE
```

维度：

```text
DATA_ERA
OUTCOME
Q
TWO_SIDED_STATE_TIMING
P_VARIANCE_H20
P_UP_PATH_H10
P_DOWN_PATH_H10
Q_MINUS_P_H20
PROBABILITY_INTEGRITY
PROBABILITY_MODEL
```

顶层状态：

```text
V2_BUILD_VALID
V2_RETROSPECTIVE_SCORE_ACCEPTED
V2_CANDIDATE_FROZEN
V2_FORWARD_SCORE_ACCEPTED
V2_CALIBRATED_PROBABILITY_ACCEPTED
V2_STATION_NOT_READY
```

规则：

1. build/test PASS 只产生 `V2_BUILD_VALID`，不证明预测能力；
2. DATA、OUTCOME、Q、STATE、三个 P primary 与 Q−P 全部 PASS 才能发布 `V2_RETROSPECTIVE_SCORE_ACCEPTED`；
3. 上述任一核心维度 FAIL 或 `INSUFFICIENT_EVIDENCE`，顶层必须为 `V2_STATION_NOT_READY` 并停止后续 candidate、forward 与 external probe；
4. `PROBABILITY_INTEGRITY` 可在 model 样本不足时 PASS；`PROBABILITY_MODEL=INSUFFICIENT_EVIDENCE` 时所有 conditional probability 为空；
5. retrospective acceptance 不等于 formal PIT、production 或前向 acceptance；
6. 不生成维度加权总分，维度不得互相抵消；
7. 停止后不得通过选腿、仓位、退出、概率降门、策略收益或 UNKNOWN/ABSTAIN 补洞。

Forward gate 在 candidate 合法冻结后才适用：

```text
continuous H20 completed eligible forecasts >= 60
each H10 path side positives >= 20 and negatives >= 20
coverage >= 70%
same frozen metrics and thresholds
no refit / no recalibration / append only
```

三个 P primary、Q−P 与 data/state integrity 前向全部 PASS 才能发布 `V2_FORWARD_SCORE_ACCEPTED`。

---

## 14. V2 schema 与版本 registry

```yaml
versions:
  authority_version: "2.0.0"
  era_definition_version: "2.0.0"
  sampling_grid_version: "ETF_5M_GRID_XSHG_2.0.0"
  outcome_definition_version: "2.0.0"
  q_definition_version: "2.0.0"
  state_definition_version: "2.0.0"
  phase_definition_version: "2.0.0"
  capability_definition_version: "2.0.0"
  target_definition_version: "2.0.0"
  predictor_registry_version: "2.0.0"
  physical_model_version: "2.0.0"
  qp_definition_version: "2.0.0"
  probability_definition_version: "2.0.0"
  acceptance_definition_version: "2.0.0"
  failure_ledger_version: "2.0.0"
  weather_snapshot_schema_version: "2.0.0"
```

Snapshot 顶层固定分区：

```text
q_weather
physical_forecasts
qp_premia
market_vector
narrative
model_acceptance
data_quality
```

Schema 要求：

- `additionalProperties=false`；
- version、measure identity、carrier、era、horizon、unit、known/target/outcome time 必填；
- `conditional_probability` 与 `base_rate` 分字段；
- 连续 forecast 的 base rate 为空，保存 benchmark/loss/interval；
- `UNKNOWN`、`CENSORED`、`NOT_LISTED`、`INSUFFICIENT_HISTORY` 不混用；
- minute proxy 永远不能产生 formal publication status；
- snapshot 无 strategy permission；
- 同日 JSON、normalized Parquet、Dashboard data 与 acceptance ledger 的 Q/P/Q−P/vector/version/hash/known_at 逐字段一致。

每个 `carrier × horizon × measure` 最小字段：

```text
measure_id / measure
carrier_id / economic_index_id
horizon_sessions / target_calendar_days
value / raw_score / percentile
unit
data_status / horizon_status / model_status
conditional_probability / base_rate
forecast_interval / quantiles
confidence components
known_at / consumer_decision_as_of
target_start_session / target_end_session / outcome_available_at
coverage_regime / available_carrier_count / listing_age_sessions
drivers / counter_evidence
definition_version / model_version / evidence_tier
```

---

## 15. Candidate 与外部探针接口

只有 `V2_RETROSPECTIVE_SCORE_ACCEPTED` 后才可冻结 candidate。Candidate manifest 必须包含 Git SHA、Authority/plan/config/schema digest、registry、训练/OOF/acceptance hashes、runtime versions 与不可变 candidate ID。

只有 `V2_FORWARD_SCORE_ACCEPTED` 后才允许运行冻结的 510300 历史外部探针。探针从气象站只读以下稳定接口：

```text
candidate_id
forecast_session
input_known_at
consumer_decision_as_of
carrier_id = CSI300_510300
coverage_regime
q_variance_h10 / q_variance_h20 / q_horizon_status
p_expected_realized_variance_h20
p_realized_variance_hazard_percentile_h20
p_upside_path_breach_score_percentile_h10
p_downside_path_breach_score_percentile_h10
qp_variance_premium_h20
qp_interval_low / qp_interval_high
qp_variance_premium_state_h20
market_vector
data_status / model_status / evidence_tier
definition/model/schema hashes
```

探针机会日、选腿、DTE、翼宽、仓位、退出、成本与成交情景继续由 `MATSHIX_510300_SHORT_VOL_BACKTEST_DESIGN.md` 冻结。探针输出只用于外部集成用途裁决，不得回写 station feature、threshold、model、phase、acceptance 或 candidate。

---

## 16. Confirmed defect 施工授权

本 Authority 只授权关闭阶段 A 的下列 confirmed defects：

```text
ERA-001
OUTCOME-001
HORIZON-001
UPSIDE-001
UPSIDE-002
TIMING-001
PHASE-001
P-001
QP-001
PROB-001
SAMPLE-001
ACCEPT-001
```

`UNIT-001=REJECTED_LEAD`：不得修改 V1 variance arithmetic，只增加 V2 明确单位与 golden。

`Q-ROBUSTNESS-001=INSUFFICIENT_EVIDENCE`：只授权执行本文件冻结的 outcome-blind robustness scenario；不得看结果后换 proxy 或阈值。

所有 V1 runtime、ShortVol 源码与失败产物保持冻结。若实现发现新的语义问题，先追加正式 defect 与因果证据；未确认前不得施工。

---

## 17. 冻结声明

从本文件独立提交开始：

- era、outcome、Q/P/Q−P、primary targets、predictor registry、state vector、phase、probability gate、score gate、failure ledger 与 probe interface 全部冻结；
- 第一轮结果无论 PASS、FAIL 或证据不足，都按原门报告；
- 任一核心门 FAIL 或证据不足时立即停止后续阶段；
- 不通过选腿、仓位、退出、概率降门或策略收益给气象站补洞。
