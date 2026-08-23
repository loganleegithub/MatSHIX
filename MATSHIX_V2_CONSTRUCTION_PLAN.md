# MatSHIX V2 气象站升级、独立验收与外部探针施工合同

> 任务名：`MATSHIX_WEATHER_STATION_V2_UPGRADE_AND_VALIDATION`  
> 状态：`READY_FOR_HUMAN_FREEZE / NOT_EXECUTED`  
> 合同版本：`0.9.0`  
> 编排日期：`2026-08-23`  
> V1 代码基线：`27730805f972681a1b016eae4db958d2164ede3d`  
> 当前研究数据：`/Users/logan/OptiMatrix_DATA/AETF`，`2023-01-03` 至 `2026-06-05`  
> 核心顺序：目标与 outcome 冻结 → Q 双侧事实 → P 真实风险 → Q−P 补偿 → 气象站独立验收 → 候选冻结/前向影子 → 固定外部探针

---

## 0. 本合同解决什么

MatSHIX V1 的正式产品边界是：读取上交所四个 ETF 期权保险市场，发布当前保险价格叙事，并预测未来内部状态事件。V1 不是未来真实收益、真实路径风险或某个 Short-Vol 策略收益的预测器。

V1 的 510300 铁鹰回测与择时诊断已经足以揭示：继续调整选腿、仓位、退出或成本，不能回答气象站是否完整。V2 施工只回答以下五个问题：

1. 当前期权曲面在风险中性测度 `Q` 下正在为什么风险定价？
2. 在物理测度 `P` 下，未来真实方差、上行路径和下行路径风险是多少？
3. 同期限 `Q−P` 风险补偿是厚、薄还是无法判断？
4. MatSHIX 的双侧状态、P 预测和 Q−P 事实能否在不读取策略收益的条件下通过独立验收？
5. 气象站候选冻结后，事先固定的 510300 外部探针能否验证这些天气信息具有经济用途？

本合同是施工流程权威，不直接冻结最终金融公式。最终公式、标签、阈值、状态和输出 Schema 必须在阶段 B 的 `MATSHIX_V2_AUTHORITY.md` 中先于实现冻结。

### 0.1 参考文档边界

`/Users/logan/MatVIX/MATVIX_V2_CONSTRUCTION_PLAN.md` 仅作为以下文档工程形式的参考：

- 权威优先级；
- 开工协议；
- 证据隔离；
- 基线 manifest；
- 缺陷台账；
- 逐缺陷施工；
- 站内 harness；
- 固定外部 harness；
- 停止条件和交付顺序。

该文档中的 VIX/VX、F1–F7、SVXY、SGOV、VXZ、美元资产、日期切分、概率事件、阈值、提交结果和任何命令输出都不是 MatSHIX 指令，不得复制进实现。

### 0.2 权威优先级

发生冲突时按以下顺序处理：

1. 人类在本合同之后给出的明确决定；
2. 经人类冻结的 `MATSHIX_V2_AUTHORITY.md`；
3. 经人类冻结的本施工合同；
4. 未被 V2 明确修改的 `MATSHIX_PRE_DEVELOPMENT_REPORT.md` V1 定义；
5. 当前 V1 代码、配置、Schema 和测试；
6. 历史回测、报告和其他模型的审查意见。

回测结果只能提出缺陷假设，不能越过 Authority 改写天气含义。

### 0.3 金融边界

V2 必须保持以下三层互相独立：

```text
Q：option-implied insurance price / risk-neutral facts
P：physical forecast of future realized outcomes
Q−P：same-horizon insurance compensation
```

统一符号约定：

```text
variance_premium_q_minus_p(t, H)
    = q_variance(t, H) - p_expected_realized_variance(t, H)
```

- 正值：期权隐含方差相对 P 预测更贵；
- 负值：保险补偿偏薄；
- 区间跨零：方向未知；
- `future realized variance` 是事后 outcome，不是当日 P 预测；
- vanilla 期权曲面不能无模型地给出最大路径突破概率，路径 hazard 不得伪装成 Q probability；
- Q−P variance 不是铁鹰、卖 Call、卖 Put 或任何具体结构的预期收益。

### 0.4 版本边界

产品版本只允许：

```text
MATSHIX_SSE_ETF_OPTIONS_V1
→ MATSHIX_SSE_ETF_OPTIONS_V2
```

施工规则：

- V1 由 Git 基线、V1 baseline manifest 和只读研究产物保存；
- V2 实现采用就地升级，不保留 `_v1/_v2` 双运行代码、兼容开关或隐式 fallback；
- 含义改变的 `feature/state/probability/schema` 版本升为 `2.0.0`；
- 新增 `outcome_version/physical_forecast_version/premium_version`，首版均为 `2.0.0`；
- Python package 只在 V2 最终完成时升为 `2.0.0`；
- 旧 ShortVol 模块、策略 policy 和报告在站内施工阶段保持字节不变；
- 外部探针只读取冻结 V1 产物、冻结 V2 产物和冻结机会日账本。

### 0.5 明确不做

- 不修改铁鹰选腿、DTE、保护翼、仓位、退出、止损或成交情景；
- 不根据策略 P&L 调整气象站特征、阈值或模型；
- 不把 `up_tail` 简单加入旧五事件后称为 V2；
- 不把 `future_RV/current_IV` 这种期限或单位不清的比率作为主合同；
- 不把四个载体的同一天当成四个独立市场样本；
- 不回填尚未上市的 510300、510500 或 588000 历史；
- 不用 `UNKNOWN/ABSTAIN` 获得择时功劳；
- 不降低 V1 概率样本门、Brier/ECE 门来制造条件概率；
- 不引入深度学习、自动特征搜索、自动阈值搜索或通用研究平台；
- 不新增策略字段、交易许可、风险单位、仓位或订单到天气快照；
- 不把分钟 close 称为 bid/ask、可成交 mid 或正式 PIT；
- 不进入生产推广、自动交易或账户管理。

---

## 1. 新 session 开工协议

施工 session 必须先逐字阅读本文件、`MATSHIX_PRE_DEVELOPMENT_REPORT.md`、`ARCHITECTURE_DECISIONS.md`、`DATA_ACCESS_REPORT.md` 和 `MATSHIX_510300_SHORT_VOL_BACKTEST_DESIGN.md`，再运行：

```bash
cd /Users/logan/MatSHIX
git status --short --branch
git fetch --prune origin
git branch -avv --no-abbrev
git worktree list --porcelain
git rev-parse HEAD
git rev-parse refs/remotes/origin/main
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src/matshix
.venv/bin/python -m matshix doctor \
  --project-dir . \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF
```

开工条件：

- `main` 干净；
- 本地、tracking 和远端 `main` 指向同一基线；
- 基线至少包含本合同；
- `.venv` runtime、pytest、Ruff、Mypy 和 doctor 通过；
- AETF 路径可读取且数据边界与 `DATA_ACCESS_REPORT.md` 一致；
- 不存在另一个 session 正在修改同一工作树；
- 当前 ShortVol 代码和输出的 hash 已记录，站内施工阶段不得改变。

随后创建开发分支：

```bash
git switch -c codex/matshix-weather-v2
```

若任一基线条件不成立，先恢复可审计基线，不得边清理、边改语义、边运行 V2。

---

## 2. 证据隔离、上市时代与 harness 总图

### 2.1 五层证据必须分开

```text
AETF 原始/研究代理
→ Q 曲面事实
→ P 物理预测
→ Q−P 补偿事实
→ 当前天气叙事与站内验收
→ 冻结后的外部策略探针
```

站内审计和验收阶段禁止读取：

- `trade_ledger.csv`；
- 账户 NAV；
- 铁鹰收益；
- 选腿结果；
- 允许/禁做分类；
- 任何策略成本或成交情景结果。

唯一例外是阶段 A 可以读取既有 ShortVol 报告的静态结论，用于登记缺陷假设；不得把逐日策略结果连接到天气特征表。

### 2.2 上市时代

V2 必须把载体上市历史写入机器可读 era registry：

| Era | 日期 | 可用期权载体 | 允许结论 |
|---|---|---|---|
| `ERA_A_50_ONLY` | 2015-02-09 至 2019-12-22 | 510050 | 仅 SSE50 局部 Q/P；不得生成四市场 Breadth |
| `ERA_B_50_300` | 2019-12-23 至 2022-09-18 | 510050、510300 | 两载体局部事实；不得伪装四市场状态 |
| `ERA_C_50_300_500` | 2022-09-19 至 2023-06-04 | 增加 510500 | 三载体事实；STAR50 为 `NOT_LISTED` |
| `ERA_D_FOUR_CARRIERS` | 2023-06-05 起 | 增加 588000 | 才允许当前四载体横截面 |

每条 Q/P/Q−P 记录必须携带：

```text
coverage_regime
available_carrier_count
carrier_id
listing_age_sessions
data_status
```

不得对缺失载体重新归一化后仍称为四市场 Breadth。新增更早数据时，只能扩展当时已上市载体的局部历史。

### 2.3 历史与前向证据边界

当前 `2023-01-03` 至 `2026-06-05` 已被多轮回测和审查查看，整个区间只能标记：

```text
RETROSPECTIVE_WALK_FORWARD
```

不能把 2025 或 2026 子区间重新命名为纯净 OOS。V2 使用两次冻结：

```text
Authority + target contract freeze
→ retrospective rolling reconstruction
→ candidate artifact freeze
→ first unseen future data forward shadow
→ release adjudication
```

历史外部探针即使在候选冻结后运行，也只能证明历史集成用途，不能替代前向气象站验收。

### 2.4 Harness 总表

| Harness | 层 | 输入 | 主要回答 | 禁止输入 |
|---|---|---|---|---|
| `H0_V1_BASELINE` | 基线 | V1 代码、配置、AETF | V1 字节状态和历史产物能否重建 | V2 代码 |
| `H1_ERA_DATA` | 数据 | contract master、ETF/期权原始数据 | 上市、可用性、PIT/代理边界是否诚实 | 策略收益 |
| `H2_OUTCOME` | P 真值 | 复权 ETF 分钟/日线 | 未来 RV、上下路径、gap 标签是否正确 | 天气 phase、策略结果 |
| `H3_Q_SURFACE` | Q | 期权分钟、条款、ETF mark | Q 方差、双侧尾部和期限事实是否稳定 | future outcome、P&L |
| `H4_TWO_SIDED_STATE` | 当前天气 | Q facts | 上下行冲击、Breadth、持续、修复是否对称 | future label、策略结果 |
| `H5_PHYSICAL_FORECAST` | P | 截止 t 的 ETF/Q/state facts | 是否优于 climatology/EWMA/HAR | future feature、策略结果 |
| `H6_QP_PREMIUM` | Q−P | 同期限 Q 与已验收 P | 补偿方向和不确定性是否可解释 | 具体期权结构收益 |
| `H7_PROBABILITY` | 概率 | 冻结目标、rolling OOF | 是否存在已校准条件概率 | 收益筛选、阈值搜索 |
| `H8_STATION_ACCEPTANCE` | 站内 | H1–H7 账本 | 哪些能力 PASS/FAIL/不足 | NAV、选腿 |
| `H9_FORWARD_SHADOW` | 前向 | 冻结 candidate、新数据 | 未见数据上是否保持 | 重新拟合、改阈值 |
| `H10_EXTERNAL_PROBE` | 外部 | 冻结天气、冻结机会日 | 信息是否有历史经济用途 | 修改气象站或策略规则 |

---

## 3. 阶段 0：冻结 V1 基线与失败证据

任何语义修改前，顺序重建 V1 并生成：

```text
outputs/v2_baseline/v1_carrier_surface.parquet
outputs/v2_baseline/v1_index_features.parquet
outputs/v2_baseline/v1_market_states.parquet
outputs/v2_baseline/v1_targets.parquet
outputs/v2_baseline/v1_probabilities.parquet
outputs/v2_baseline/v1_shortvol_timing_report.json
outputs/v2_baseline/v1_shortvol_timing_panel.parquet
outputs/v2_baseline/v1_manifest.json
```

`v1_manifest.json` 至少记录：

```text
git_sha
python/package/dependency versions
config and schema digests
AETF source manifest and source date range
command lines
row counts and date ranges
file SHA-256
current probability acceptance by event
ShortVol source file hashes
UTC build time
```

这些均为本地忽略产物，不提交大体积数据。V1 可执行代码不复制到 V2 分支；历史重放依赖 Git SHA 和 baseline artifacts。

`H0_V1_BASELINE` 必须证明：

- 同一代码、配置和输入得到相同 table hash；
- 当前五个概率模型的零 calibrated OOF 状态被原样保存；
- 当前 ShortVol timing 结论和 opportunity panel hash 被原样保存；
- baseline 构建不读取任何 V2 文件。

---

## 4. 阶段 A：业务审计与缺陷台账

阶段 A 不改运行语义、不重写 Dashboard、不运行新策略。只允许增加一个最小审计入口，优先直接读取现有 Parquet 与代码输出。

唯一输出：

```text
outputs/v2_audit/business_audit_daily.parquet
outputs/v2_audit/business_audit_summary.json
MATSHIX_V2_AUDIT.md
```

### 4.1 必查缺陷假设

以下是待审计假设，不是预先保证实施的功能：

| Defect lead | 层 | 待核事实 |
|---|---|---|
| `ERA-001` | DATA | 四载体上市时代是否被当前共同状态隐式压平 |
| `OUTCOME-001` | TARGET | 当前没有策略无关的未来真实风险 outcome ledger |
| `HORIZON-001` | Q/P | 30/60/90 日 Q 与 5/10/20 交易日 outcome 是否被错配 |
| `UNIT-001` | Q/P | volatility、variance、total variance 和 annualized variance 是否混用 |
| `UPSIDE-001` | STATE | `up_tail` 未进入旧概率 predictors |
| `UPSIDE-002` | STATE | Shock、Breadth、hard acute 和 repair 是否系统性偏向 DownTail |
| `TIMING-001` | STATE | 上行 phase 是否因要求过去已上涨而迟报 |
| `PHASE-001` | STATE | `primary_phase` 是否被下游错误当成完整机器接口 |
| `P-001` | FORECAST | P 层只有未经独立验收的 EWMA94 |
| `QP-001` | PREMIUM | 现有 VRP 是否期限单一、模型单一且没有区间/符号置信 |
| `PROB-001` | PROBABILITY | 旧目标预测内部状态，而非未来真实风险 |
| `SAMPLE-001` | PROBABILITY | 504 训练 + 252 校准是否在当前可用历史上结构性不可达 |
| `ACCEPT-001` | ACCEPTANCE | 顶层 research PASS 是否与预测能力 PASS 混淆 |

### 4.2 审计维度

#### 数据与 era

- 从 `opt_basic.parquet` 独立重建各载体首个 list date；
- 核对当前 raw、surface、state、target 的起止日和可用载体数；
- 按 era、carrier、year 报告曲面和 outcome 覆盖；
- 核对 `available_at/decision_as_of/vintage_kind` 与研究代理边界；
- 检查未来追加数据是否会改变历史输入、feature 或 OOF。

#### Q 曲面

- 核对 parity forward/discount、model-free variance、25D 双翼和期限插值；
- 分开 exact bracket 与 nearest-expiry/delta proxy；
- 检查低成交或陈旧 close 对翼部和 Q variance 的敏感性；
- 验证 Put/Call、DownTail/UpTail 和单位方向；
- 不以缺失 bid/ask 阻断研究，但必须保留 `RESEARCH_ONLY`。

#### 双侧状态

- 列出 DownTail 与 UpTail 从 raw fact 到 score、Breadth、phase、predictor、target、narrative 的完整血缘；
- 检查 `shock` 中负收益项对上涨冲击的系统性抑制；
- 检查 `repair` 是否只表达下行修复；
- 检查 `hard_acute` 是否无法表达上行急性凸性；
- 检查过去五日上涨是否只是确认事实，却被用成进入上行 phase 的必要条件。

#### P、Q−P 与概率

- 审计 EWMA94 对未来 H5/H10/H20 RV 的 QLIKE、偏差与覆盖；
- 与 climatology、rolling RV、HAR-RV 进行同一 cohort 比较；
- 核对旧五事件的业务目标、正例、eligibility、purge、OOF 和校准可达性；
- 把 `INSUFFICIENT_HISTORY` 与预测失败分开；
- 不根据 2025 Call-side loss 选择特征或阈值。

### 4.3 缺陷记录合同

`MATSHIX_V2_AUDIT.md` 中每个正式缺陷必须包含：

```text
defect_id
status = CONFIRMED | REJECTED_LEAD | INSUFFICIENT_EVIDENCE
severity = P0 | P1 | P2
layer = DATA | OUTCOME | Q | STATE | P | QP | PROBABILITY | ACCEPTANCE
observed symptom
reproduction command
causal evidence
financial consequence
minimal repair
affected files
semantic/version impact
station acceptance criterion
```

优先级：

- `P0`：lookahead、错误上市时代、单位/期限错误、错误 OK、标签污染；
- `P1`：双侧能力、P 预测、Q−P、时效和概率业务缺陷；
- `P2`：叙事、展示或非核心便利性问题。

没有 `CONFIRMED` defect ID 不得修改对应语义。审查意见、回测亏损或单一历史事件不能代替 causal evidence。

---

## 5. 阶段 B：冻结 V2 Authority、目标与输出合同

第一行语义代码修改前，提交只包含文档的 `MATSHIX_V2_AUTHORITY.md`。它必须冻结：

- V2 产品定义与 Q/P/Q−P 边界；
- era registry；
- decision timestamp、target start/end 和 outcome availability；
- variance、path、gap 的单位和公式；
- 首批 primary/secondary 目标；
- 每个目标固定 predictor registry；
- 双侧 state vector、phase 和 UNKNOWN 语义；
- P baseline、Challenger、训练/OOF/校准路径；
- Q−P 符号、区间与状态；
- station acceptance gate；
- Schema 和所有版本号；
- 外部探针稳定输入接口。

配置和代码不得先于 Authority。Authority 冻结后修改 target、feature registry、阈值或 gate，必须升级 challenger/version，并重新生成完整历史，不得覆盖原 candidate。

### 5.1 首批目标族

V2 outcome ledger 可以计算全部 H5/H10/H20 连续结果，但首批正式 target/capability 只允许：

```text
PRIMARY-1  target=realized_variance_h20       capability=variance_hazard_h20
PRIMARY-2  target=upside_path_breach_h10      capability=upside_path_hazard_h10
PRIMARY-3  target=downside_path_breach_h10    capability=downside_path_hazard_h10
PRIMARY-4  derived=qp_variance_premium_h20
```

以下只允许 `SCORE_ONLY_RESEARCH_SHADOW`，不能阻断核心施工，也不能发布条件概率：

```text
variance_hazard_h5/h10
upside_path_hazard_h5
downside_path_hazard_h5
jump_hazard_1d
q_surface_persistence_h5/h20
p_realized_hazard_persistence_h5/h20
q_surface_repair_h5
p_hazard_repair_h5
```

任何 secondary 输出晋升 primary 都必须先证明独立标签、足够样本和新增业务问题，不能一次性把十一项 hazard 全部建模。

### 5.2 V2 输出最小合同

每个 carrier × horizon × measure 至少发布：

```text
measure_id
measure = Q | P | Q_MINUS_P
carrier_id
horizon_sessions / target_calendar_days
value / score
unit
model_status
conditional_probability
base_rate
forecast_interval / quantiles
confidence
known_at
target_start_session
target_end_session
outcome_available_at
coverage_regime
drivers
counter_evidence
definition_version
model_version
evidence_tier
```

约束：

- `conditional_probability` 仅在校准门通过时非空；
- `BASE_RATE_ONLY` 时 `conditional_probability=null`，历史率只写 `base_rate`；
- 连续预测没有 base rate，使用 benchmark forecast/loss；
- 单一 `confidence` 不得遮蔽数据、模型和期限状态，机器字段必须另有 `data_status/model_status/horizon_status`；
- `primary_phase` 只做人类摘要，机器消费者使用 versioned vector facts；
- weather snapshot 不含策略、结构、仓位和交易许可。

### 5.3 已讨论 hazard 能力的处置

此前提出的前瞻输出不能在施工中静默丢失，也不能因名字相似而混为一个对象。Authority 必须建立 machine-readable capability registry，并逐项冻结以下处置：

| 讨论中的能力 | V2 首批处置 | 正式对象 |
|---|---|---|
| `variance_hazard_h5/h10` | `SCORE_ONLY_RESEARCH_SHADOW` | 未来 H5/H10 realized variance |
| `variance_hazard_h20` | `PRIMARY` | 未来 H20 realized variance |
| `upside_path_hazard_h5` | `SCORE_ONLY_RESEARCH_SHADOW` | H5 上行路径突破当前 Q 尺度 |
| `upside_path_hazard_h10` | `PRIMARY` | H10 上行路径突破当前 Q 尺度 |
| `downside_path_hazard_h5` | `SCORE_ONLY_RESEARCH_SHADOW` | H5 下行路径突破当前 Q 尺度 |
| `downside_path_hazard_h10` | `PRIMARY` | H10 下行路径突破当前 Q 尺度 |
| `jump_hazard_1d` | `SCORE_ONLY_RESEARCH_SHADOW` | 下一交易日隔夜跳空 |
| `persistence_hazard_h5/h20` | 必须拆分后 shadow | `q_surface_persistence_*` 与 `p_realized_hazard_persistence_*` |
| `repair_probability_h5` | 必须拆分且先叫 score | `q_surface_repair_score_h5` 与 `p_hazard_repair_score_h5`；仅校准通过后才可发布各自 probability |

每个 registry 条目都必须标明：

```text
capability_id
target_definition
measure
status = PRIMARY | SCORE_ONLY_RESEARCH_SHADOW | REJECTED
score
model_status
conditional_probability
base_rate
confidence components
known_at
target_window
drivers
counter_evidence
```

`SCORE_ONLY_RESEARCH_SHADOW` 表示能力被建设和记录，但没有越过首批核心验收范围；`REJECTED` 必须写明不可识别、样本不足或金融含义不成立的理由。不得用一个未指明对象的 persistence/repair 总分重新混合 Q 与 P。

---

## 6. 阶段 C：H1/H2 数据时代与真实 outcome harness

先实现 outcome，再修天气特征。这样可以避免根据新特征表现重新定义真值。

### 6.1 决策与窗口

对 `forecast_session=t`：

```text
input cutoff           = t session 14:56 bar completed
consumer decision_as_of = existing exchange_decision_as_of(t)
target starts          = next exchange session after t
target ends            = add_exchange_sessions(t, H)
outcome_available_at   = exchange_decision_as_of(target_end)
```

`PROVIDER_RECONSTRUCTED` 只证明研究回放；它不升级为正式历史 available_at。目标窗口缺日、停牌、复权冲突或末端未完成时为 `CENSORED/UNKNOWN`，绝不能记为 0。

### 6.2 实现方差 outcome

主 realized-variance 口径使用复权 ETF 的 5 分钟收益，并把 overnight 独立加入：

```text
daily_total_variance
    = overnight_log_return^2
    + sum(valid 5-minute intraday log_return^2)

rv_variance_h
    = (252 / H) * sum(daily_total_variance over target sessions)

rv_volatility_h
    = sqrt(rv_variance_h)
```

同时保存：

```text
rv_intraday_h
rv_overnight_h
valid_bar_count
expected_bar_count
sampling_grid_version
corporate_action_status
```

1 分钟与 10 分钟口径只做敏感性，不择优。午休不得产生伪收益；复权因子变化必须有手算例。

### 6.3 上下路径 outcome

以 t 日冻结的复权 ETF mark 为起点，对未来目标窗口保存：

```text
max_up_log_move_h
max_down_log_move_h          # 正数表示下行幅度绝对值
close_to_close_return_h
overnight_gap_max_h
```

若存在严格同期限 Q variance：

```text
q_expected_move_h = sqrt(q_variance_h * year_fraction_to_target)
upside_path_breach_h   = max_up_log_move_h   > q_expected_move_h
downside_path_breach_h = max_down_log_move_h > q_expected_move_h
```

这些是“超过当时隐含尺度的真实路径事件”，不是 Q 路径概率。Q horizon 不可严格夹逼时，raw path outcome 仍可用，但 `*_breach_h=UNKNOWN`。

### 6.4 同期限 Q outcome 对照

H20 主目标必须用 target end 的实际 calendar year fraction，从有效到期总方差中严格夹逼。主 Q/P cohort 禁止 `NEAREST_EXPIRY_PROXY`：

```text
q_variance_h20
realized_minus_q_h20 = rv_variance_h20 - q_variance_h20
q_minus_realized_h20 = q_variance_h20 - rv_variance_h20
rv_to_q_ratio_h20    = rv_variance_h20 / q_variance_h20
```

`rv_to_q_ratio` 只作为描述，主经济量是同单位 variance difference。

### 6.5 H1/H2 输出

```text
data/processed/v2/era_registry.parquet
data/processed/v2/realized_outcome_ledger.parquet
data/processed/v2/outcome_issue_ledger.parquet
outputs/v2_outcomes/coverage.json
outputs/v2_outcomes/handcheck.md
```

### 6.6 H1/H2 必过测试

1. list date 与 contract master 手算一致；
2. 未上市载体为 `NOT_LISTED`，不是 missing/zero；
3. t 日输入只能生成 t+1 起的 outcome；
4. H5/H10/H20 使用上交所交易日而非自然日计数；
5. 午休、隔夜、停牌、缺 bar 和公司行动行为确定；
6. variance/volatility/total variance 单位不混用；
7. Q target maturity 必须严格夹逼，禁止主 cohort 外推；
8. 修改未来 H 窗口之后的数据不改变该 forecast/outcome；
9. 末端不完整窗口为 CENSORED；
10. 上下路径镜像 fixture 会交换 up/down outcome；
11. 四载体同日共享 `date_cluster_id`；
12. H20 重叠窗口共享可重放的 `overlap_cluster_id`。

---

## 7. 阶段 D：H3 Q 曲面与 H4 双侧天气施工

### 7.1 Q 层复用边界

优先复用现有：

- `surface/research.py` 的 parity forward/discount；
- model-free variance；
- total-variance tenor interpolation；
- ATM/25D put/call measures；
- coverage/issue ledger 和方法标记。

V2 只新增当前缺失的 horizon-matched Q fact、研究价格敏感性和双侧状态，不重写已通过数学测试的定价核心。

### 7.2 研究价格敏感性

主研究价格仍为：

```text
MINUTE_CLOSE_1456
```

另建一个 outcome-blind robustness scenario：

```text
NEAR_CLOSE_PRINT_VWAP_1452_1456
```

只有当窗口内存在正成交且 `amount/(volume*contract_unit)` 与 OHLC 一致时才生成。日结算只能作为事后 surface sensitivity，不能进入同日 14:56 决策。

每个 Q fact 保存：

```text
price_proxy
exact_or_proxy
valid_strikes
put_count / call_count
parity_pair_count
liquidity_status
sensitivity_delta
```

缺 bid/ask 不阻断研究预测；若核心 Q 分类对近收盘价格代理不稳定，则 Q gate 为 `INSUFFICIENT_EVIDENCE`。

### 7.3 双侧状态最小修复方向

审计确认后，V2 至少应分别表达：

```text
common_iv_shock
downside_price_shock
upside_price_shock
down_tail
up_tail
down_tail_breadth
up_tail_breadth
down_tail_persistence
up_tail_persistence
variance_repair
downside_repair
upside_repair
term_repair
```

规则：

- DownTail 与 UpTail 不重新混成单一压力分数；
- V1 `pressure_score` 若继续表示下行压力，V2 Schema 必须显式命名 `downside_pressure_score`；
- 上行急性事件必须能由 call-wing/UpTail 重定价、速度和 Breadth 形成；
- 过去五日 ETF 已上涨只能是 confirmation/counter-evidence，不能作为领先上行风险进入门；
- Repair 必须说明修复的是 variance、downside、upside 还是 term，不能用一个总 repair 隐藏方向；
- `primary_phase` 仍是唯一人类摘要，但不得吞掉正交 vector；
- phase precedence、hysteresis 和 UNKNOWN 必须在 Authority 中逐项冻结。

允许审计后新增但不预先强制的 phase：

```text
UPTAIL_BUILDING
TWO_SIDED_CONVEXITY_BUILDING
```

它们只有在消除已确认缺陷且不依赖 future outcome 时才进入正式集合。

### 7.4 H3/H4 验收

必须同时满足：

- Q measure 的公式、单位、期限、method 和缺失行为可重放；
- exact bracket 与 proxy 永不混称；
- Put/Call 镜像 fixture 会交换 DownTail/UpTail、down/up Breadth 和 repair；
- 上涨冲击不再因负收益项被系统性压成 calm；
- `data_status=OK` 的必需双侧事实完整；
- 缺一侧时严格降级，不复制另一侧或填 0；
- 新 phase 的进入不要求目标窗口内或事后实现的结果；
- V2 narrative 可以同时陈述 down/up 风险与 counter-evidence；
- 未来数据变更不改变过去 Q/state；
- 与 V1 未修改的定价数学 golden 一致。

---

## 8. 阶段 E：H5 物理测度 P 预测

### 8.1 预测对象与粒度

P 预测按 `carrier_id × forecast_session × horizon` 发布。不得把四个 ETF 的 variance 加权平均后称为“市场组合方差”；市场层只可聚合标准化 hazard rank 和 Breadth。

首批主对象：

```text
每个载体的 rv_variance_h20 连续预测
每个载体的 upside_path_breach_h10 score/probability
每个载体的 downside_path_breach_h10 score/probability
```

市场层发布：

```text
upside_hazard_breadth
downside_hazard_breadth
variance_hazard_breadth
```

### 8.2 预注册模型序列

不增加依赖，按以下顺序竞争：

#### 连续 variance

```text
B0  rolling climatology of log RV
B1  EWMA94
B2  HAR-RV using daily/weekly/monthly realized variance
C1  HAR-RV + Q level/term facts
C2  C1 + frozen two-sided MatSHIX vector
```

#### 上下路径二元事件

```text
B0  rolling event base rate
B1  past realized-vol/path logistic baseline
C1  B1 + Q level/term and matching side tail facts
C2  C1 + matching side Breadth/persistence/repair
```

每个模型的 feature list 固定写入 Authority 和 artifact。禁止 stepwise selection、L1 自动筛选、树模型 importance 反选、收益筛选或看完确认结果后删特征。

### 8.3 Causal walk-forward

对每个 forecast：

```text
training row target_end_position <= current prediction_position
purge >= target horizon
training ordered by prediction_date
all transforms fitted only on training rows
carrier-specific model by default
```

跨 carrier panel 只能作为 Challenger：必须包含 carrier fixed effect/scale normalization，并按日期整体 block bootstrap；四个载体不得增加四倍名义独立样本。

连续 score 模型可在 252 条 outcome-complete training rows 后进入 `RETROSPECTIVE_SCORE`。条件概率继续服从 V1 的更严格门：504 training、类别门、252 顺序校准，不得因当前样本不足而降低。

### 8.4 P 模型状态

```text
NOT_RUN
UNOBSERVABLE
INSUFFICIENT_HISTORY
RETROSPECTIVE_SCORE
BASE_RATE_ONLY
CALIBRATED_MODEL
FORWARD_SHADOW_ACCEPTED
```

`RETROSPECTIVE_SCORE` 不是概率。若模型未通过校准，`conditional_probability=null`。

### 8.5 Causal score 标准化

为站内分位检验和冻结外部 probe 提供稳定接口，原始 forecast/decision score 只允许用此前已发布的同 carrier、同 definition、同 coverage regime score 做 mid-rank：

```text
p_realized_variance_hazard_percentile_h20
    = causal percentile of p_expected_realized_variance_h20

p_upside_path_breach_score_percentile_h10
    = causal percentile of upside raw decision score

p_downside_path_breach_score_percentile_h10
    = causal percentile of downside raw decision score
```

规则：

- 当前日不得进入自身 reference distribution；
- 至少 126 个此前 eligible score 才发布 percentile；
- carrier、definition、model 和 coverage regime 变化时不得拼接 reference；
- percentile 是排名，不是 probability；
- raw score、reference count 和 percentile 必须同时保存。

### 8.6 P 站内指标

#### 连续 variance

- QLIKE；
- log-RV MSE；
- mean forecast bias；
- 80% interval empirical coverage；
- Challenger 相对 `min(loss_EWMA, loss_HAR)` 的 paired skill；
- 按 year、carrier、era 和压力分层；
- 按日期、block length ≥20 的 bootstrap interval。

首版 score gate 在 Authority 中预冻结为：

```text
paired QLIKE skill >= 2%
90% block-bootstrap skill lower bound > 0
forecast bias finite and directionally stable
eligible coverage >= 70%
```

#### 上下路径 score

- Brier/LogLoss 仅用于概率；
- score Spearman 与 future breach；
- causal quintile monotonicity；
- 固定 top-10% alarm budget 的 capture lift；
- false-alarm rate；
- lead-time distribution；
- leave-one-event-cluster-out 方向。

首版 score gate 在 Authority 中预冻结为：

```text
Spearman > 0
top-10% capture lift > 1
90% block-bootstrap lower bound > 0 for Spearman
    or > 1 for top-10% capture lift
eligible coverage >= 70%
up/down 两侧分别通过，不得互相抵消
```

若 Authority 审计认为阈值缺少可辩护性，只能在第一次模型运行前修改并记录理由；运行后不得为通过而放宽。

### 8.7 H5 输出

```text
data/processed/v2/physical_forecast_ledger.parquet
data/processed/v2/physical_oof_ledger.parquet
outputs/v2_physical_forecast/summary.json
outputs/v2_physical_forecast/failure_ledger.parquet
outputs/v2_physical_forecast/report.md
```

报告不得出现期权组合、NAV 或策略收益。

---

## 9. 阶段 F：H6 Q−P 风险补偿

### 9.1 主合同

首版只正式建设 variance Q−P，避免在 vanilla 曲面上制造路径概率：

```text
qp_variance_premium_h20
    = q_variance_h20 - p_expected_realized_variance_h20

qp_interval_low
    = q_variance_h20 - p_forecast_interval_high

qp_interval_high
    = q_variance_h20 - p_forecast_interval_low
```

方向状态：

```text
RICH_CONFIDENT      if qp_interval_low > 0
THIN_CONFIDENT      if qp_interval_high < 0
SIGN_UNCERTAIN      if interval crosses 0
UNOBSERVABLE        if Q or accepted P unavailable
```

方向状态的机器字段固定命名为：

```text
qp_variance_premium_state_h20
```

每条记录必须继承 Q 和 P 两边更弱的：

```text
evidence_tier
data_status
horizon_status
model_status
known_at
```

不能因为 Q 可观察而在 P 未验收时发布 confident Q−P。

### 9.2 事后验证量

同一 ledger 保存但不进入当日 signal：

```text
ex_post_q_minus_realized_h20
    = q_variance_h20 - realized_variance_h20

p_forecast_error_h20
    = p_expected_realized_variance_h20 - realized_variance_h20
```

H6 检查：

- Q−P 分位与未来 `q_minus_realized` 是否方向单调；
- `RICH_CONFIDENT` 是否对应更高的 ex-post compensation；
- `THIN_CONFIDENT` 是否更容易出现 `RV > QVar`；
- 结论是否只由少数 2025 日期或单一 carrier 驱动；
- 在 `MINUTE_CLOSE_1456` 与近收盘成交代理下方向是否稳定；
- P baseline 不通过时 Q−P 自动为 `INSUFFICIENT_EVIDENCE`。

### 9.3 H6 score gate

Authority 在首次运行前冻结：

```text
Spearman(qp_gap, future_q_minus_realized) > 0
top-vs-bottom causal quintile difference > 0
90% date-block bootstrap lower bound > 0 for at least one primary statistic
sign-confident coverage is reported and >= 30%
no carrier exhibits a statistically material opposite sign without explanation
```

若样本不足，允许诚实发布 Q 与 P 两层，但 `Q_MINUS_P` 状态为 `INSUFFICIENT_EVIDENCE`，不得由策略收益替它通过。

### 9.4 H6 输出

```text
data/processed/v2/qp_premium_ledger.parquet
outputs/v2_qp_acceptance/summary.json
outputs/v2_qp_acceptance/report.md
```

---

## 10. 阶段 G：H7 概率、Schema 与发布真值

### 10.1 旧五事件处理

V1 五个内部状态事件不得静默改名为真实市场 hazard。阶段 A/B 必须逐项裁决：

- 若仍是有用的 Q surface transition fact，重命名到 `q_surface_transitions`，并独立版本；
- 若与 V2 primary 目标重复或没有业务增量，从 V2 正式事件集合删除；
- 不保留旧 executable aliases；
- V1 事件仍可从冻结 baseline 查看，但不在 V2 runtime 平行执行。

### 10.2 条件概率门

V2 复用现有顺序 OOF、Platt、Brier/ECE 和 moving-block bootstrap 实现，除非审计确认代码错误。首版正式 probability gate 保持 V1 Authority：

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

当前历史极可能无法达到该门。正确结果是：

```text
INSUFFICIENT_HISTORY
BASE_RATE_ONLY
conditional_probability = null
```

而不是降低门、用 uncalibrated Logistic probability、或把 base rate 填进 conditional probability。

### 10.3 V2 Schema

Schema 必须明确分区：

```text
q_weather
physical_forecasts
qp_premia
market_vector
narrative
model_acceptance
data_quality
```

机器接口至少保证：

- `additionalProperties=false`；
- 版本和 measure identity 必填；
- probability 与 base_rate 分字段；
- every forecast 有 known/target/outcome times；
- carrier/era/horizon/units 必填；
- Unknown、Censored、Not Listed 和 Insufficient History 不混用；
- research minute proxy 永远不能生成 formal publication status；
- V2 不提供 strategy permission。

### 10.4 输出一致性 harness

同一日 JSON、normalized Parquet、Dashboard data 和 acceptance ledger 必须对以下字段逐项一致：

```text
Q value/method/status
P score/status/probability/base rate
Q−P value/interval/sign
two-sided vector
primary phase/narrative evidence
version/hash/known_at
```

Dashboard 只做必要兼容：同时展示 Q、P、Q−P 和双侧 vector。视觉重设计不属于 V2 核心。

---

## 11. 阶段 H：H8 气象站自身验收

站内验收禁止读取账户、订单、选腿或策略 P&L。唯一输出：

```text
outputs/v2_station_acceptance/daily_ledger.parquet
outputs/v2_station_acceptance/failure_ledger.parquet
outputs/v2_station_acceptance/summary.json
outputs/v2_station_acceptance/report.md
```

不生成可以互相抵消的总分。每个维度独立给出：

```text
PASS
FAIL
INSUFFICIENT_EVIDENCE
NOT_APPLICABLE
```

### 11.1 DATA/ERA 门

必须同时满足：

- 上市时代、载体、listing age 和可用数量可重放；
- `NOT_LISTED` 不被填充或当成缺失；
- 研究 minute proxy、PIT 和许可边界诚实；
- `data_status=OK` 行的 V2 必需字段完整；
- future input mutation 不改变过去输入、Q、P prediction 或 OOF；
- 所有 P0 DATA 缺陷关闭。

### 11.2 OUTCOME 门

必须同时满足：

- RV、overnight、up/down path 和 Q scale 公式有 handcheck；
- 交易日、午休、停牌、公司行动和缺 bar 处理确定；
- target window 和 outcome available time 无未来函数；
- CENSORED/UNKNOWN 不记 0；
- 单位和期限严格匹配；
- outcome builder 不读取天气或策略结果。

### 11.3 Q 门

必须同时满足：

- parity、model-free variance、tenor 和 wings 通过 golden；
- exact/proxy 和 price proxy 可区分；
- H20 主 cohort 只使用 exact matched Q；
- 双侧事实对研究价格代理不过度敏感，或明确 `INSUFFICIENT_EVIDENCE`；
- 缺 bid/ask 只限制证据层，不伪造 spread/mid。

### 11.4 TWO-SIDED STATE/TIMING 门

必须同时满足：

- up/down shock、tail、Breadth、persistence 和 repair 各自有清晰含义；
- 镜像 fixture 交换 up/down 结果；
- 上行 leading state 不要求过去已经上涨；
- `primary_phase` 不隐藏相反方向的独立高 hazard；
- UNKNOWN 严格传播；
- 相对 V1，已冻结真实 up/down event cluster 的漏报不增加、首次识别不更晚；
- 提前识别不能以误报簇无限增加换取。

### 11.5 P FORECAST 门

分别裁决：

```text
P_VARIANCE_H20
P_UP_PATH_H10
P_DOWN_PATH_H10
```

三者不得用综合平均互相抵消。每个 primary 必须达到 Authority 冻结的 score gate；否则 V2 只能是 `BUILD_VALID`，不能是 `RETROSPECTIVE_SCORE_ACCEPTED`。

### 11.6 Q−P 门

必须满足：

- Q 和 P 同期限同单位；
- P 已通过相应 forecast gate；
- gap interval 和 sign 状态可重放；
- Q−P 与 ex-post Q−RV 的方向性通过冻结 gate；
- 不能用某个铁鹰盈利证明 Q−P 正确。

### 11.7 PROBABILITY 门

分成两个结论：

```text
PROBABILITY_INTEGRITY
PROBABILITY_MODEL
```

- 标签、eligibility、purge、OOF、calibration、publication 正确可使 INTEGRITY PASS；
- 没有足够 calibrated OOF 时 MODEL=`INSUFFICIENT_EVIDENCE`；
- MODEL 不通过不允许条件概率，但不自动否定已经通过的连续/ranking score；
- `BASE_RATE_ONLY` 不计预测增量。

### 11.8 failure ledger

每个 primary outcome cluster 固定分类：

```text
DETECTED_EARLY
DETECTED_LATE
MISSED
FALSE_ALARM
ABSTAIN_DATA
```

事件簇和告警预算必须在 Authority 中先于模型运行冻结：

- variance extreme 使用仅由此前已完成 outcome 构成的 causal 90% 分位；reference 少于 126 条时不形成可计分事件；
- path event 使用冻结的 `*_path_breach_h10` 标签；
- 同一 carrier 上目标窗口重叠、方向相同的连续正例合并为一个事件簇，不能按每日重叠窗口重复计功；
- alarm 使用同一 causal top-10% score budget；
- `DETECTED_EARLY/LATE` 的分界 session、alert persistence 和 cluster start 均写入 Authority；
- threshold 不得由全样本分位、铁鹰损益或被评价事件本身反推。

每行至少记录：

```text
event_id / carrier / event_cluster_id
event start/end/severity
first alert date
lead_or_lag_sessions
score/probability/base rate
Q/P/Q−P facts
data/model status
drivers/counter_evidence
classification reason
```

`ABSTAIN_DATA` 不计命中，同时报告覆盖率和最差事件中的 abstention share，防止通过弃权规避失败。

### 11.9 顶层发布状态

顶层不得再使用一个含混的 `PASS_RESEARCH_ONLY_FORMAL_BLOCKED`。固定状态阶梯：

```text
V2_BUILD_VALID
V2_RETROSPECTIVE_SCORE_ACCEPTED
V2_CANDIDATE_FROZEN
V2_FORWARD_SCORE_ACCEPTED
V2_CALIBRATED_PROBABILITY_ACCEPTED
V2_STATION_NOT_READY
```

规则：

- DATA、OUTCOME、Q、TWO_SIDED_STATE、三个 P primary 和 Q−P 全部 PASS，才可成为 `V2_RETROSPECTIVE_SCORE_ACCEPTED`；
- probability model 可诚实不足，但不得被描述为 probability-ready；
- 任一核心维度 FAIL/不足则 `V2_STATION_NOT_READY`；
- build/test PASS 只证明工程完整，不证明预测能力；
- retrospective acceptance 不等于 formal PIT 或 production acceptance。

---

## 12. 阶段 I：候选冻结与 H9 前向影子

### 12.1 Candidate freeze

站内 retrospective gate 通过后，生成不可变 candidate：

```text
outputs/v2_candidate/manifest.json
outputs/v2_candidate/model_artifacts/
outputs/v2_candidate/schema.json
outputs/v2_candidate/authority_digest.txt
```

manifest 至少记录：

```text
git SHA
Authority/plan/config/schema digests
feature/target/model registries
training and OOF ledgers hashes
all acceptance verdicts
dependency/runtime versions
candidate_id
freeze timestamp
```

candidate freeze 后不得修改：

- target；
- feature list；
- transforms；
- thresholds；
- calibration；
- model coefficients；
- failure classification；
- external probe mapping。

任何变更必须产生新 candidate_id，并保留旧 candidate 的前向记录。

### 12.2 Forward shadow

第一批未被设计、审计和回测查看的新 session 才进入 `FORWARD_SHADOW`。逐日只追加：

```text
forecast facts at known_at
candidate/model hashes
later outcome and available_at
failure classification
```

禁止 retrospective rewrite。数据 revision 只追加新 revision，并保留旧发布值。

### 12.3 Forward gate

首版最低可裁决样本：

```text
continuous H20: >= 60 completed eligible forecasts
each H10 path side: >= 20 positive and >= 20 negative outcomes
coverage >= 70%
```

样本未满足时为 `INSUFFICIENT_EVIDENCE`，不是失败。满足后用与 retrospective 相同的冻结指标和阈值判定；不得训练或重校准 candidate。

只有三个 P primary、Q−P 和 data/state integrity 在 forward 全部通过，才发布：

```text
V2_FORWARD_SCORE_ACCEPTED
```

条件概率另行要求其完整概率门，不随 score 自动晋级。

---

## 13. 阶段 J：H10 固定 510300 外部集成探针

### 13.1 进入门槛

正式外部探针只在：

```text
V2_FORWARD_SCORE_ACCEPTED
```

之后运行。若为了研发节奏在 candidate freeze 后运行历史探针，必须命名：

```text
RETROSPECTIVE_EXTERNAL_INTEGRATION_DIAGNOSTIC
```

它不能推动 station release，也不能反过来修改 candidate。

### 13.2 冻结机会日与期权结构

直接复用 `MATSHIX_510300_SHORT_VOL_BACKTEST_DESIGN.md` 已冻结的机会日结构：

- 510300 标准合约；
- 25–45 DTE，最接近 35 DTE；
- 绝对 Delta 最接近 0.20 的 OTM Put/Call；
- 两侧各买至少远两个挂牌档位保护翼；
- 持有至 7DTE 为主，H5/H10 为稳健性；
- 主归因使用日结算机会日 outcome；
- expiry-cluster bootstrap；
- `ABSTAIN_DATA` 不计择时成功；
- `ABSTAIN_QP` 不计定价成功；
- 分钟成交代理只作为二级执行压力测试。

不得修改当前 `shortvol.py`、`shortvol_timing.py` 的选腿、成交、退出或成本规则。V2 外部模块只能把冻结 station verdict 连接到冻结 opportunity panel。

### 13.3 固定双探针适配器

外部探针只读取已验收的四个稳定事实：

```text
p_realized_variance_hazard_percentile_h20
p_upside_path_breach_score_percentile_h10
p_downside_path_breach_score_percentile_h10
qp_variance_premium_state_h20
```

主探针 `V2_WEATHER_FIXED` 只回答天气择时是否能避开未来高风险，不允许 Q−P 替天气记功：

```text
if any of the three P hazard fields is unavailable or not station-accepted:
    ABSTAIN_DATA

elif max(
    p_realized_variance_hazard_percentile_h20,
    p_upside_path_breach_score_percentile_h10,
    p_downside_path_breach_score_percentile_h10,
) >= 0.90:
    KNOWN_BLOCK

else:
    ALLOW
```

次探针 `V2_PRICED_FIXED` 只在主探针已经 `ALLOW` 的机会中检验 Q−P 的增量定价用途：

```text
if V2_WEATHER_FIXED != ALLOW:
    inherit V2_WEATHER_FIXED verdict

elif Q−P field is unavailable or not station-accepted:
    ABSTAIN_QP

elif qp_variance_premium_state_h20 == RICH_CONFIDENT:
    ALLOW

elif qp_variance_premium_state_h20 == THIN_CONFIDENT:
    KNOWN_BLOCK

else:  # SIGN_UNCERTAIN / UNOBSERVABLE
    ABSTAIN_QP
```

`0.90` 只来自站内预注册的 top-10% alarm budget；它必须在外部收益不可见时随 Authority/candidate 一起冻结，不是通过策略 P&L 搜索得到的最优阈值。两个 verdict 必须同时保存，不得只留下最终交集。

限制：

- 没有风险单位和仓位梯度；
- `RICH_CONFIDENT` 不能覆盖或重新打开天气 hazard block；
- `SIGN_UNCERTAIN` 只能 `ABSTAIN_QP`，不能伪装成价格有利；
- 不读取 phase；
- 不因 Call/Put 单侧策略表现修改 0.90；
- 不在不同 carrier、年份或 regime 使用不同阈值；
- 不以 base-rate-only 概率代替 accepted score。

### 13.4 固定控制组

```text
STATIC_ALL:
    every complete eligible opportunity -> ALLOW

V1_FROZEN:
    use frozen V1 timing category from H0 baseline

V2_WEATHER_FIXED:
    use the three-hazard primary adapter above

V2_PRICED_FIXED:
    apply the Q−P secondary adapter only after V2_WEATHER_FIXED
```

四组必须使用同一 opportunity universe、同一腿、同一 mark 和同一 horizon。

### 13.5 唯一输出

```text
outputs/v2_external_probe/opportunity_ledger.parquet
outputs/v2_external_probe/failure_attribution.parquet
outputs/v2_external_probe/report.json
outputs/v2_external_probe/report.html
```

逐机会日记录：

```text
station/candidate version
signal session / known_at / target end
three P hazard scores
Q−P state
weather_timing_verdict
priced_shortvol_verdict
frozen four legs and expiry
H5/H10/TO_7DTE outcome
return_on_max_loss / MAE
loss side
expiry cluster
```

### 13.6 经济判定

`V2_WEATHER_FIXED` 相对 `STATIC_ALL` 和 `V1_FROZEN` 分别报告：

- ALLOW − BLOCK mean/median return-on-max-loss；
- 最差 10% 机会日捕获率与固定 alarm budget lift；
- Call-side 与 Put-side tail capture；
- ALLOW 的 MAE 和最坏结果；
- expiry-cluster bootstrap CI；
- leave-one-expiry-out 稳定性；
- coverage/abstention；
- 若运行分钟代理，再报告独立成本与成交敏感性。

`V2_PRICED_FIXED` 再相对 `V2_WEATHER_FIXED` 报告同一组指标，作为 Q−P 的增量归因；不得把两层改善相加后只发布一个收益数。

外部探针分别发布：

```text
weather_utility_verdict
qp_incremental_utility_verdict

each in:
    POSITIVE_EXTERNAL_UTILITY
    MIXED_EXTERNAL_UTILITY
    NEGATIVE_EXTERNAL_UTILITY
    NOT_ELIGIBLE
```

两者都不改变站内 verdict。

### 13.7 冻结归因规则

```text
真实危险高，P hazard 仍低
    → weather-station defect candidate

P hazard 正确报高，weather adapter 仍 ALLOW
    → integration contract defect

weather adapter 已 ALLOW、Q−P 显示保险薄，priced adapter 仍 ALLOW
    → integration defect

P hazard 正确、Q−P 显示保险厚，但具体铁鹰亏损
    → payoff/side/strike-specific edge，不反改天气事实

天气事实正确，策略因成交或成本亏损
    → execution/economic issue，不反改气象站

ABSTAIN_DATA 避开损失
    → 不记气象站命中，只记录安全弃权

ABSTAIN_QP 避开损失
    → 不记 Q−P 命中，只记录定价证据覆盖不足
```

任何外部失败若要返回气象站，必须创建新的 defect lead，经独立 outcome 证据确认后进入新 V2.x/V3 Authority；不得在同一 candidate 上调参重跑。

---

## 14. 实现边界与最小代码地图

### 14.1 优先复用

- 数据和 contract master：`src/matshix/data/aetf.py`；
- 交易日和 known-at：`src/matshix/calendar.py`；
- Q 曲面：`src/matshix/surface/`；
- 历史/百分位：`src/matshix/features/`；
- 双侧状态：`src/matshix/state/`；
- OOF/校准：`src/matshix/probability/`；
- hash/serialization/storage：现有模块；
- CLI：`src/matshix/cli.py`；
- 现有 ShortVol 引擎保持冻结。

### 14.2 允许的最小新增模块

建议边界，最终由 defect-to-file mapping 确认：

```text
src/matshix/outcomes/realized.py
src/matshix/forecast/physical.py
src/matshix/premium/variance.py
src/matshix/research/weather_v2_audit.py
src/matshix/research/weather_v2_acceptance.py
src/matshix/research/weather_v2_probe.py
```

不得新增 generic governance、renderer、plugin、feature store、model registry service 或并行 V1 engine。

### 14.3 计划新增的最小 CLI

以下是待实现合同，不是当前已存在命令：

```bash
.venv/bin/python -m matshix audit-weather-v2 \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .

.venv/bin/python -m matshix build-weather-v2 \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .

.venv/bin/python -m matshix accept-weather-v2 \
  --project-dir .

.venv/bin/python -m matshix probe-weather-v2-510300 \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .
```

不再拆出多个只包装一个函数的 CLI。Baseline freeze、outcome/Q/P/Q−P build 和 candidate manifest 由上述主流程内部按阶段生成。

### 14.4 测试地图

聚焦测试至少覆盖：

```text
tests/test_v2_era_and_outcomes.py
tests/test_v2_q_horizon_and_symmetry.py
tests/test_v2_physical_forecast.py
tests/test_v2_qp_premium.py
tests/test_v2_probability_publication.py
tests/test_v2_station_acceptance.py
tests/test_v2_external_probe.py
```

每个测试文件必须对应当前 defect 或 acceptance criterion；没有合同映射的 helper、abstraction 或 fixture 不增加。

### 14.5 反过度设计熔断

每次提交检查：

```text
new abstraction -> acceptance criterion
new config       -> frozen Authority field
new output       -> named harness consumer
new test         -> defect/gate
```

若出现以下任一情况，停止并重新做 scope mapping：

- 同时存在两套 V1/V2 engine；
- 新增依赖；
- 为尚不存在的第三方 consumer 设计扩展点；
- station 模块引用 `research.shortvol*`；
- 新增代码主要用于报告防御而非 Q/P/Q−P；
- 同一事实在多个模块重复计算；
- 为制造概率活动而放宽样本门。

---

## 15. 逐缺陷施工与提交顺序

唯一合法 loop：

```text
confirmed defect
→ frozen semantic delta
→ failing focused test
→ minimal implementation
→ focused test
→ full station regression
→ acceptance ledger update
→ one defect commit
```

建议提交边界：

1. `docs: add MatSHIX V2 construction contract`；
2. `audit: record MatSHIX V1 weather defects`；
3. `docs: freeze MatSHIX V2 Authority and targets`；
4. `feat(v2): close ERA/OUTCOME/HORIZON/UNIT defects`；
5. `fix(v2): close Q surface defects`；
6. `fix(v2): close UPSIDE/STATE/TIMING defects`；
7. `feat(v2): add accepted physical forecast layer`；
8. `feat(v2): add variance Q-minus-P facts`；
9. `fix(v2): close probability/publication defects`；
10. `test(v2): complete station-only acceptance`；
11. `build(v2): freeze candidate artifact`；
12. `test(v2): append forward-shadow verdict`；
13. `test(v2): run frozen 510300 external probe`；
14. `docs: record MatSHIX V2 final adjudication`。

每个功能提交必须包含对应配置、Schema、代码和聚焦测试，不提交半成品字段。文档 Authority 提交必须早于语义实现。

---

## 16. 停止条件

以下情况必须停止，不得继续堆代码：

- baseline 无法确定性重建；
- outcome 单位、目标窗口或公司行动无法冻结；
- Q H20 不能获得足够 exact matched cohort；
- P 模型不能优于最强简单 baseline；
- 上下路径结果只由单一事件簇驱动；
- 关键门为 `INSUFFICIENT_EVIDENCE`；
- 需要使用 future outcome 选择当日 feature；
- 需要从铁鹰 P&L 反推天气阈值；
- 需要把未校准概率发布为条件概率；
- 需要伪造 bid/ask、历史 available_at 或未上市载体；
- candidate freeze 后需要改模型或阈值；
- 第二次修复仍不能关闭同一 confirmed defect。

停止时保留：

```text
Authority/version
defect ledger
candidate manifest if present
daily forecast/outcome/failure ledgers
failed gate metrics
exact reproduction command
```

结论必须是 `FAIL` 或 `INSUFFICIENT_EVIDENCE`，不能美化为 ready。

---

## 17. 最终验证与 Definition of Done

### 17.1 每次功能提交

```bash
.venv/bin/python -m pytest -q <focused tests>
.venv/bin/ruff check <changed Python paths>
.venv/bin/mypy src/matshix
git diff --check
```

### 17.2 最终工程验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src/matshix
.venv/bin/python -m build
.venv/bin/python -m matshix doctor \
  --project-dir . \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF
.venv/bin/python -m matshix build-weather-v2 \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .
.venv/bin/python -m matshix accept-weather-v2 --project-dir .
git diff --check
git status --short --branch
```

只有外部探针 eligible 时才运行：

```bash
.venv/bin/python -m matshix probe-weather-v2-510300 \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .
```

### 17.3 V2 完成定义

V2 只有同时满足以下条件才算完成：

1. V1 baseline 与失败证据可重建；
2. Authority 在实现前冻结；
3. era、outcome、Q、双侧 state、P 和 Q−P 各有独立 ledger；
4. 三个 P primary 分别通过冻结 score gate；
5. Q−P H20 通过独立 gate；
6. probability integrity 通过，未校准概率保持 null；
7. failure ledger 完整，UNKNOWN/ABSTAIN 不记功；
8. JSON/Parquet/Dashboard/acceptance 一致；
9. candidate 可内容寻址并可确定性重放；
10. forward shadow 达到样本门并通过，或明确停在 `INSUFFICIENT_EVIDENCE`；
11. 测试、Ruff、Mypy、build、doctor 和 real-data harness 通过；
12. 没有策略逻辑进入 weather station；
13. 外部探针如运行，使用冻结规则且不改变站内 verdict；
14. 最终报告明确列出 PASS、FAIL、证据不足和未建设能力。

以下不构成完成：

- 只有新字段或漂亮 Dashboard；
- 历史分位看起来单调但没有 causal walk-forward；
- BaseRate 可用；
- 某个回测收益改善；
- 只避开 2025 Call-side loss；
- build/tests 绿色但 P/Q−P gate 不通过；
- retrospective success 被写成 forward 或 formal PIT acceptance。

---

## 18. 最终交付报告必须回答

1. V1 哪些问题是代码错误，哪些是原产品能力不足？
2. 每个 confirmed defect 改了什么、没有改什么？
3. Q、P、Q−P 三层分别能发布什么、不能发布什么？
4. 四个上市时代如何影响载体、Breadth、训练和结论？
5. 三个 primary forecast 的 retrospective 与 forward 结论是什么？
6. 哪些输出只有 score/base rate，哪些具有 calibrated probability？
7. `DETECTED_EARLY/LATE/MISSED/FALSE_ALARM/ABSTAIN` 分布是什么？
8. candidate/release 的代码、配置、Schema 和 ledger hash 是什么？
9. 固定 510300 外部探针中，天气择时与 Q−P 增量分别产生正、混合还是负的经济用途？
10. 外部探针失败属于天气、适配器、定价 Edge 还是执行问题？
11. 哪些能力因数据或样本不足仍被明确拒绝？

---

## 19. 下一施工 session 的第一条执行指令

```text
逐字阅读 /Users/logan/MatSHIX/MATSHIX_V2_CONSTRUCTION_PLAN.md，
把经人类冻结的版本作为施工流程合同。先验证 main、runtime、AETF
和 V1 确定性基线，记录 ShortVol 代码与失败产物 hash，再创建
codex/matshix-weather-v2 分支。阶段 A 只做业务审计和缺陷台账，
不得读取逐日策略收益调整天气。先冻结 MATSHIX_V2_AUTHORITY.md、
era、outcome、Q/P/Q−P、primary targets 和 acceptance gates，再按
confirmed defect 分别施工。任何核心门 FAIL 或证据不足时停止，
不得通过选腿、仓位、退出、概率降门或策略收益给气象站补洞。
```
