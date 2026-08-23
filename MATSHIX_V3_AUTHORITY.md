# MATSHIX V3 AUTHORITY

- 状态：`HUMAN_FROZEN / EXECUTION_AUTHORIZED`
- Authority 版本：`3.0.0`
- 冻结时间：`2026-08-23T18:14:36Z`
- 施工任务：`MATSHIX_WEATHER_STATION_V3_PHYSICAL_PRICING_DECOMPOSITION`
- 施工分支：`codex/matshix-weather-v3`
- 施工合同：`MATSHIX_V3_CONSTRUCTION_PLAN.md`
- 施工合同 SHA-256：`468197a6c6037ab050f0ff372190f86747361420483b93bb98d21e14af2d80bc`
- 合同提交与开工 main：`f69b3a25b70c667d4c8c1e0e5d0a21981e40e38d`
- 稳定父基线：`ca32d3bbe175c84ea16e3c9b265b679896d23c6e`
- V2 失败归档：`archive/matshix-v2.2.3-development-fail@93f883b063953525890430ae54731f23da354659`
- 首期载体：`CSI300_LOCAL / CSI300_510300 / 510300`

本 Authority 只把已经获得人类施工授权的 V3 合同翻译成可执行字段、公式、Schema 语义和
测试常量，不新增 target、feature、模型或验收门。任何超出本文的语义变化必须停止并取得新
的人类决定。

---

## 1. 证据边界与时代

### 1.1 冻结时代

```text
DEVELOPMENT_ERA = 2020-01-02..2026-06-05
carrier          = CSI300_510300
economic_index   = CSI300
underlying       = 510300
evidence_kind    = RETROSPECTIVE_DEVELOPMENT
evidence_tier    = RESEARCH_ONLY
q_price_kind     = RESEARCH_MINUTE_CLOSE
formal_pit       = false
```

本机已经被查看过或补齐的所有同日期 AETF 数据都属于回顾性研究。严格因果 walk-forward
只证明实现因果和回顾性性能，不把历史升级为未见样本。候选冻结后新到达、未参与设计的收据
才可标记 `PROSPECTIVE_FORWARD`。

### 1.2 允许输入

```text
/Users/logan/OptiMatrix_DATA/AETF/ETF/1m_etf
/Users/logan/OptiMatrix_DATA/AETF/ETF/1d_etf_price
/Users/logan/OptiMatrix_DATA/AETF/OPTION/1m_opt
/Users/logan/OptiMatrix_DATA/AETF/OPTION/1d_opt_price
/Users/logan/OptiMatrix_DATA/AETF/OPTION/opt_basic.parquet
冻结的 Authority、施工合同、代码、Schema 与测试
```

### 1.3 禁止输入

天气站施工、特征、模型、样本资格、门槛和裁决不得读取或使用：

```text
strategy daily return / P&L / NAV
position / sizing / risk unit
option leg / strike selection / entry / exit / roll
fill / slippage / commission / execution result
ShortVol backtest ledger or report values
任何具体策略的机会日筛选
```

`src/matshix/research/shortvol.py` 与 `shortvol_timing.py` 只校验冻结 hash，不导入 V3
运行时，也不读取其历史产物。

---

## 2. 时间轴、可得性与 censoring

```text
forecast_session t
historical feature cutoff       = completed exchange session t-1
historical Q observation        = t 14:56:00 Asia/Shanghai minute bar
historical Q known_at           = t 14:56:59 Asia/Shanghai
consumer decision as_of         = next exchange session 09:00 Asia/Shanghai
H20 outcome sessions            = t+1..t+20
outcome_available_at            = exchange session after target_end, 09:00 Asia/Shanghai
```

在 forecast `t` 拟合模型时，训练行 `s` 只有在
`outcome_available_at[s] <= known_at[t]` 时可用。当前行、尚未结束的重叠 outcome、未来分位、
全样本标准化和修订后的未来字段都不得进入训练。

日期必须来自 XSHG 交易日历。无交易日不得自行生成；历史末端没有完整 H20 的行保持
`CENSORED/INCOMPLETE_TARGET_WINDOW`，不得补零或删除后假装 coverage 更高。

---

## 3. Outcome Authority

### 3.1 复权坐标与日方差

每个分钟 mark 使用同日 ETF daily `adj_factor`：

```text
adjusted_mark = raw_close * adj_factor
```

一天的冻结 5 分钟网格为：

```text
09:30, 09:35, ..., 11:30       25 marks / 24 returns
11:30 -> 13:05                 1 lunch-boundary return
13:05, 13:10, ..., 15:00       24 marks / 23 returns
total                          49 marks / 48 returns
```

午休只记录一次 `11:30 -> 13:05` adjusted log return；不 forward-fill、不制造零收益。隔夜项
是上一 XSHG 交易日复权 15:00 到当日复权 09:30 的 log return。复权因子变化被记录为
`ADJUSTED_FACTOR_CHANGE`，但只要复权坐标和其他输入完整，不因此删除该日。

```text
daily_intraday_variance[d] = sum(48 adjusted five-minute log returns squared)
daily_overnight_variance[d] = adjusted close(d-1) to open(d) log return squared
daily_total_variance[d] = daily_intraday_variance[d] + daily_overnight_variance[d]
```

缺任一冻结 endpoint、相邻交易日隔夜输入、有效复权因子或 15:00 mark 时，整日
`daily_total_variance` 为 null，状态为 `CENSORED`，原因码必须保留。

### 3.2 V3 Primary outcome

```text
rv_variance_h20[t]
  = (252 / 20) * sum(daily_total_variance[d], d=t+1..t+20)
unit = ANNUALIZED_VARIANCE
```

20 个目标交易日必须全部完整；否则 outcome 为 null。目标开始日、结束日、可得时间、有效/预期
bar 数、日内/隔夜分量、复权状态和 issue 必须进入 outcome ledger。

### 3.3 非核心路径事实

可记录 `max_up_log_move_h10` 和 `max_down_log_move_h10` 连续事实，但不得进入 V3 核心接受门，
也不得发布以 `move > q_expected_move` 定义的“纯 P”概率。新增路径概率需要另立 Authority。

---

## 4. P_PRIMARY_HAR Authority

### 4.1 模型注册表

V3 只允许三个 P 候选：

```yaml
B0_ROLLING_CLIMATOLOGY:
  target: log(max(rv_variance_h20, 1e-12))
  minimum_history: 252 outcome-complete rows
  maximum_history: 504 outcome-complete rows
  output: exp(mean(log_target))

B1_EWMA94:
  daily_input: daily_total_variance
  recurrence: variance_d = 0.94 * variance_d_minus_1 + 0.06 * daily_input_d
  initialization: first prior finite positive daily_input
  forecast_cutoff: t-1
  output: 252 * variance_t_minus_1

P_PRIMARY_HAR:
  kind: ridge_log_variance
  alpha: 1.0
  target: log(max(rv_variance_h20, 1e-12))
  minimum_training_rows: 252
  maximum_training_rows: 1260
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
```

EWMA 只用依次到达的有限正 daily input 更新；更早的数据缺口不以零更新。若 `t-1` 当日输入
缺失，当前 B1 发布 `UNOBSERVABLE` 并保存原因，不能静默 carry-forward 为一个“新观测”。

冻结 HAR 特征：

```text
log_rv_d1_lag1       = log(252 * daily_total_variance[t-1])
log_mean_rv_d5_lag1  = log(252 * mean(daily_total_variance[t-5..t-1]))
log_mean_rv_d22_lag1 = log(252 * mean(daily_total_variance[t-22..t-1]))
```

5 日或 22 日窗口任一交易日缺值时，相应当前特征为 null。每次拟合只在当次训练窗计算 feature
median、mean 和 population standard deviation；先用训练窗 median impute，再标准化训练行和
当前行。训练 median 缺失、标准差为零、非有限设计或非正 target 均发布 `UNOBSERVABLE`。

P 的当前资格、训练资格和 opportunity 分母不得依赖 Q、H4、期权月份、wing、合约数量、
策略机会或策略结果。

### 4.2 因果 OOF 区间

每个已发布 P forecast `s` 在 H20 outcome 成熟后形成：

```text
error_s = log(rv_variance_h20[s]) - log(p_primary_variance_h20[s])
```

forecast `t` 只可读取 `outcome_available_at[s] <= known_at[t]` 的先前已发布 OOF error，取最近
最多 504 个；至少 126 个时：

```text
low  = forecast_t * exp(empirical_quantile(errors, 10%))
high = forecast_t * exp(empirical_quantile(errors, 90%))
```

少于 126 个时 point estimate 可发布，区间状态为 `INSUFFICIENT_INTERVAL_HISTORY`。禁止使用
当前拟合训练窗的 fitted residual。

### 4.3 P 回顾性接受门

统计协议：

```text
loss = QLIKE(y,f) = y/f - ln(y/f) - 1
bootstrap = MOVING_DATE_BLOCK
repetitions = 2000
block_length_sessions = 20
confidence = 90%
seed = 2026082401
```

P opportunity 是：当前 H20 target 已完成，且当日已有至少 252 个因果可训练 target。Q/H4 不
进入分母。paired 评价行要求 actual、P、B0、B1 均为有限正值。必须全部满足：

```text
paired finite point rows >= 252
point forecast coverage >= 70%
QLIKE skill vs min(B0, B1) >= 2%
90% moving-date-block bootstrap skill lower bound > 0
absolute normalized bias <= 20%
finite positive forecasts = 100% of published forecasts

paired causal interval rows >= 126
80% interval empirical coverage in [65%, 95%]

causal extreme cohort rows >= 20
P_PRIMARY_HAR extreme-cohort QLIKE <= best baseline extreme-cohort QLIKE
```

extreme threshold 在每个 forecast 日只用此前最多 504 个已经成熟的 outcome 的 90th percentile，
当前 outcome 不参与阈值。任一门 FAIL 为 `P_CORE_H20=FAIL`；样本门不足为
`P_CORE_H20=INSUFFICIENT_EVIDENCE`，并停止 Q−P 和候选冻结。

---

## 5. Q_WEATHER Authority

### 5.1 历史 Q

```text
observation = AETF 14:56 minute close
known_at = 14:56:59 Asia/Shanghai
evidence_tier = RESEARCH_MINUTE_CLOSE
formal_pit_claimed = false
carrier = CSI300_510300 only
horizon = exact H20 target end
```

每个 expiry 先用同 strike put/call parity 推断 forward/discount，再以真实、有限、正价格构建
model-free OTM variance。合法 expiry 必须 `dte > 7`。目标期限从 `t 14:56:59` 到 H20
`target_end 15:00` 使用 `ACT/365F`：

```text
target_year_fraction = seconds(target_end 15:00 - t 14:56:59) / seconds(365 days)
q_total_variance_h20 = linear interpolation of expiry total variance
q_variance_h20 = q_total_variance_h20 / target_year_fraction
unit = ANNUALIZED_VARIANCE
```

必须由目标期限上下两个合法 expiry 精确夹逼；若目标恰等于一个 expiry，可用该 maturity。
不得使用 nearest expiry、期限外推或模型价格。`q_total_variance_h20` 必须恒等于
`q_variance_h20 * target_year_fraction`（浮点容差 `1e-12`）。

Q ledger 必须发布或明确 UNKNOWN：

```text
q_variance_h20 / q_total_variance_h20
parity_forward and parity_pair_count
lower_expiry / upper_expiry / exact_target_bracket / method
valid_strikes / put_count / call_count
atm_iv / down_tail / up_tail / wing_coverage / dominant_side
surface_status / issues
observation_time / known_at / evidence_tier / unit
```

`down_tail = put25_iv - atm_iv`，`up_tail = call25_iv - atm_iv`；它们是
`DESCRIPTIVE_Q_WEATHER`，不是 P 特征或交易许可。任一必要 bracket、parity 或合法价格缺失
时，Q variance 保留具体 UNKNOWN 原因；wing 缺失只使对应 wing/tail 字段 UNKNOWN，不反向
抹掉已经合法构造的 Q variance。Q 缺失不得阻断 P。

历史 Q 只验收公式、期限、单位、因果性、缺失披露和 deterministic replay；不设历史 coverage
硬门，不声称正式 PIT。

### 5.2 正式前向 Q

候选冻结后，primary 为 `14:56 as-of last`，comparator 为 `14:56 bid/ask midpoint`。正式门：

```text
paired exact H20 rows >= 126
paired exact H20 coverage >= 70%
median absolute relative q_variance delta <= 5%
p90 absolute relative q_variance delta <= 15%
exact-bracket availability agreement >= 95%
wing dominant-side agreement >= 90%
90% moving-date-block CI of median signed delta within [-5%, +5%]
bootstrap repetitions = 2000
block length = 20 sessions
seed = 2026082402
```

样本或 coverage 不足为 `INSUFFICIENT_EVIDENCE`，不能用历史 minute close 顶替。

---

## 6. P_HAR_Q_CHALLENGER Authority

唯一 Challenger：

```yaml
P_HAR_Q_CHALLENGER:
  kind: ridge_log_variance
  alpha: 1.0
  target: log(max(rv_variance_h20, 1e-12))
  minimum_training_rows: 252
  maximum_training_rows: 1260
  required_current_q: exact H20 only
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
    - log_q_variance_h20
```

训练、变换、target 可得性和 OOF 区间规则与主站相同。Challenger 训练行需要自身 exact H20 Q；
主站仍使用全部合法历史，不降到 Q/H4 子样本。比较只在两者同时可评价的完全相同日期上：

```text
paired rows >= 252
eligible-Q opportunity coverage >= 70%
QLIKE skill vs P_PRIMARY_HAR >= 2%
90% moving-block bootstrap skill lower bound > 0
absolute normalized bias <= 20%
causal interval empirical coverage in [65%, 95%]
extreme-cohort QLIKE <= P_PRIMARY_HAR extreme-cohort QLIKE
```

Challenger 不得读取 H4、H10 Q、term ratio、tail bundle、自动特征搜索或策略结果。失败为
`REJECTED_CHALLENGER`，不改变 P、Q 或 Q−P；通过也仅为 `PROMOTION_CANDIDATE`，不得自动
替换主站。Challenger 的 moving-date-block comparison 使用 `2000` 次、`20` session block、
`90%` confidence 和 seed `2026082401`。

---

## 7. H4 裁决

H4 不进入 P 主模型或固定 Challenger。Q 可保留双侧描述，但必须标记
`DESCRIPTIVE_Q_WEATHER`；H4 缺失保持 UNKNOWN，不能删除 P opportunity。精确冗余关系：

```text
downside_price_shock + upside_price_shock
  - 1.2 * common_iv_shock == 40
```

该冗余三元组不得同时进入线性设计矩阵。任何未来 H4 predictor 必须另立 Authority，并先验收
矩阵秩、缺失选择和固定特征。

---

## 8. Q_MINUS_P_H20 Authority

只在 `P_CORE_H20=PASS` 且当日 P、因果 P interval 与 exact H20 Q 均有效时计算：

```text
qp_variance_premium_h20  = q_variance_h20 - p_primary_variance_h20
qp_interval_low          = q_variance_h20 - p_interval_high
qp_interval_high         = q_variance_h20 - p_interval_low
ex_post_q_minus_realized = q_variance_h20 - rv_variance_h20
```

```text
THICK_COMPENSATION  qp_interval_low > 0
THIN_COMPENSATION   qp_interval_high < 0
UNCERTAIN           interval crosses or touches 0
UNOBSERVABLE        Q, P or P interval unavailable
NOT_APPLICABLE      P_CORE_H20 is not PASS
```

历史输出标记 `RESEARCH_QP_ESTIMATE`。公式正确不等于择时有效，更不等于卖波动许可。方向研究门：

```text
paired rows >= 126
Spearman(qp_gap, ex_post_q_minus_realized) > 0
causal top-minus-bottom quintile mean difference > 0
90% moving-date-block bootstrap lower bound > 0 for at least one statistic
sign-confident coverage >= 30%
Q availability coverage separately disclosed
bootstrap repetitions = 2000
block length = 20 sessions
seed = 2026082403
```

方向门未通过为 `QP_DIRECTION_NOT_VALIDATED`；不回写 P/Q，不改变公式事实。

---

## 9. Schema、状态与 UNKNOWN

V3 ledger 的关键公共字段必须包括：

```text
forecast_session / target_start_session / target_end_session
observation_time / known_at / consumer_decision_as_of / outcome_available_at
carrier_id / economic_index_id / horizon_sessions
authority_version / authority_sha256 / implementation_git_sha
input_manifest_sha256 / evidence_tier / unit / status / issues
```

允许裁决值仅为：

```text
PASS / FAIL / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE
```

可观测性状态包括 `OK / UNOBSERVABLE / CENSORED / UNKNOWN / GAP`；null 不得编码为零。
每个 forecast、Q observation、outcome 和 maturity 必须保持一行身份，不得因缺失而静默删样本。

---

## 10. 接受矩阵与停止语义

独立裁决：

```text
ENGINEERING
OUTCOME_INTEGRITY
P_CORE_H20
Q_RESEARCH_INTEGRITY
P_HAR_Q_CHALLENGER
QP_CONSTRUCTION_INTEGRITY
QP_DIRECTION_RESEARCH
FORWARD_Q
FORWARD_P
```

顶层：

```text
V3_BUILD_VALID
  ENGINEERING + OUTCOME_INTEGRITY PASS

V3_RESEARCH_CORE_ACCEPTED
  V3_BUILD_VALID + P_CORE_H20 + Q_RESEARCH_INTEGRITY
  + QP_CONSTRUCTION_INTEGRITY PASS

V3_CANDIDATE_FROZEN
  only after V3_RESEARCH_CORE_ACCEPTED

V3_FORWARD_ACCEPTED
  only after frozen FORWARD_Q and FORWARD_P PASS

V3_NOT_READY
  any required core FAIL, insufficient evidence or incomplete provenance
```

若 P FAIL 或证据不足，Q 的独立研究工程可以完成，但 Q−P、候选冻结和前向阶段停止。任何
实现泄漏、单位/期限错配、Q/H4 阻断 P、基线失败或 provenance 不完整，立即停在相应层并
保存失败产物 hash。

---

## 11. 前向候选协议

只有 `V3_RESEARCH_CORE_ACCEPTED` 后才可生成候选冻结。冻结后 append-only 保存 prediction、
Q receipt、known_at、input hash 和 maturity receipt；未成熟为 `PENDING`，缺口为
`UNKNOWN/GAP`，不回填、不重算旧预测、不移动窗口。

FORWARD_P 除沿用 P 的 QLIKE、bias、coverage、interval、extreme 和 bootstrap 定义外，固定：

```text
matured forward H20 point rows >= 126
point forecast coverage >= 70%
QLIKE skill vs frozen best B0/B1 >= 2%
90% moving-block bootstrap skill lower bound > 0
absolute normalized bias <= 20%
matured causal interval rows >= 63
80% interval empirical coverage in [65%, 95%]
extreme-cohort rows >= 12 and QLIKE <= frozen best baseline
```

FORWARD_Q 服从第 5.2 节全部门。样本不足保持 `INSUFFICIENT_EVIDENCE`；本 Authority 不授权
交易策略外部探针。

---

## 12. 阶段 A confirmed-defect ledger

以下为 V3 合同已经确认、允许施工的缺陷；假说不在本表内：

| defect_id | confirmed defect | 最小修复 |
|---|---|---|
| `V3-P-001` | V2 P 主模型依赖 exact Q 与 H4，Q/H4 缺失会删 P 机会 | 纯 HAR 主站独立训练与出勤 |
| `V3-P-002` | V2 区间使用当前拟合窗 in-sample residual | 只用先前成熟 OOF forecast error |
| `V3-P-003` | V2 完整 `HAR+Q+H4` 设计精确降秩且 H4 缺失选择非随机 | H4 从核心和 Challenger 移除 |
| `V3-P-004` | V2 H10/H20/H4 资格曾跨期限耦合 | 每个 horizon 独立；V3 核心只使用 H20 outcome |
| `V3-TARGET-001` | 以 `move > q_expected_move` 定义的 H10 标签不是纯 P target | 核心仅保留连续 H20 realized variance |
| `V3-Q-001` | V1 tenor 可使用 nearest-expiry proxy，不满足 exact H20 Q | V3 Q 只用 exact bracket total-variance interpolation |
| `V3-ARCH-001` | V2 把物理风险、期权定价和补偿混在单一主模型/资格链 | 拆成 P、Q、Q−P 与隔离 Challenger |

经审计可函数级移植但必须重新测试的部分：

```text
V2 outcome: adjusted 5-minute grid, overnight, exchange-session H20 window, censoring
V2 Q: parity forward, model-free expiry variance, exact bracket total-variance interpolation
V2 provenance: repository/runtime identity and deterministic replay comparison
V2 scoring: QLIKE and moving-date-block bootstrap primitives
```

禁止合并整条 V2 归档；禁止移植 V2 完整 C2、H4 feature bundle、Q-defined H10 labels、
in-sample interval 或策略链。

---

## 13. 一次冻结历史裁决

Authority 必须先纯文档提交；实现和测试分别提交后，才运行第一次完整历史构建。该次结果就是
本 Authority 的回顾性裁决。结果出现后不得改 era、feature、model、seed、门槛或删除日期重跑
冲关。

若发现 confirmed implementation defect，先保存原失败产物与 hash，说明影响范围并冻结补充
Authority，之后才允许新版本重跑。统计 FAIL 或证据不足不是实现缺陷，也不是降门授权。
