# MatSHIX V3 物理风险、期权定价与方差补偿解耦施工合同

> 任务名：`MATSHIX_WEATHER_STATION_V3_PHYSICAL_PRICING_DECOMPOSITION`
> 状态：`HUMAN_FROZEN / EXECUTION_AUTHORIZED`
> 合同版本：`1.0.0`
> 冻结日期：`2026-08-24`
> 人类授权：`按照正确架构来写 V3 的施工合同，写好后到新 session 开始 V3 施工`
> 稳定父基线：`main@ca32d3bbe175c84ea16e3c9b265b679896d23c6e`
> V2 失败归档：`archive/matshix-v2.2.3-development-fail@93f883b063953525890430ae54731f23da354659`
> 施工分支：`codex/matshix-weather-v3`
> 首期载体：`CSI300_LOCAL / 510300`
> 核心顺序：`Outcome → P_PRIMARY_HAR → Q_WEATHER → Q−P → 可选 HAR+Q Challenger → 前向证据`

---

## 0. 合同裁决

V2.2.3 不是可合并到主线的产品版本。它是一次有价值但失败的回顾性研究：修复 H10/H20
强制绑定后，H20 模型出勤率达到 100%，但冻结的 P 核心 QLIKE、bootstrap 和区间覆盖门
仍失败；H10 样本不足；Q−P 因 P 未通过而未执行。

V3 不沿用 V2 的完整 `HAR + Q + H4` 作为 P 主模型。V3 冻结以下最小架构：

```text
已实现波动历史 ───────────────→ P_PRIMARY_HAR ───────┐
                                                    ├─→ Q_MINUS_P_H20
期权横截面 ───────────────────→ Q_WEATHER ──────────┘
                                  │
                                  └─→ P_HAR_Q_CHALLENGER（隔离、非阻断）
```

冻结语义：

1. `P` 回答未来 20 个交易日真实年化方差的条件期望；
2. `Q` 回答同一时点、同一期限的风险中性隐含方差和双侧定价事实；
3. `Q−P` 回答同期限隐含方差相对物理期望的补偿厚度；
4. `Q` 可能包含对未来 P 的增量信息，因此允许一个预先固定的 Challenger；
5. Challenger 失败只说明本次增量模型不成立，不能使 P 或 Q 停发；
6. `Q−P` 不是可交易利润、错误定价、卖方许可或任何具体期权结构的预期收益。

### 0.1 V2 中保留与拒绝的部分

允许在 V3 分支逐项审计后复用：

- 已实现方差 outcome 的复权、隔夜、5 分钟与交易日历处理；
- exact H20 bracket、parity forward、model-free Q variance 和 UNKNOWN 原因码；
- 因果 walk-forward、moving-date-block bootstrap、确定性 replay 与 provenance 工具；
- V1 业务缺陷审计工具和测试。

明确拒绝直接继承：

- V2 的完整 C2 `HAR + Q + H4` 模型；
- 当前行或训练行同时要求 H10 与 H20 的资格绑定；
- 让 H4 缺失决定 P 主模型是否出勤；
- 以 Q expected move 定义后再声称为纯 P 的 H10 二元标签；
- 使用同一训练窗的拟合残差构造“前向”区间；
- 把历史分钟收盘价称为正式 PIT bid/ask；
- 任何策略收益、选腿、仓位、退出或成本输入。

V3 不得执行 `git merge archive/matshix-v2.2.3-development-fail`。复用必须是函数级或
提交级的显式移植，并由 V3 测试证明语义仍符合本合同。

### 0.2 已见样本中的设计证据

以下是对 V2.2.3 同一批 528 行的后验诊断，只解释 V3 为什么这样分层，不得作为 V3
验收结果重复使用：

```text
frozen HAR all-outcome QLIKE          0.159126
raw Q QLIKE                           0.209106
same-cohort HAR QLIKE                 0.165846
HAR + Q QLIKE                         0.164840
HAR + H4 QLIKE                        0.155478
frozen HAR + Q + H4 QLIKE             0.162696
raw Q > realized variance             92.2% of rows
full 15-feature design matrix rank    14
```

`HAR + Q` 的点估计仅略好于同 cohort HAR，bootstrap 区间跨零；完整模型虽然多数日期略胜，
却在高方差尾部集中亏损均值。H4 完整组与缺失组的未来风险分布明显不同，且特征矩阵精确
降秩。因此合理结论不是“Q 没信息”，而是：P 主站先由纯 HAR 承担，Q 增量单独验证，H4
不得靠选择性完整样本进入核心。

---

## 1. 权威、分支与证据边界

### 1.1 权威优先级

发生冲突时依次服从：

1. 本合同之后的人类明确决定；
2. 经人类冻结的 `MATSHIX_V3_AUTHORITY.md`；
3. 本施工合同；
4. 未被 V3 修改的 V1 产品与数据边界；
5. V2 失败归档中的 Authority、代码和裁决；
6. 外部模型建议、论文解读、回测与报告。

外部意见和历史结果只能提出假设，不能自动改变 target、features、门槛或证据等级。

本合同已经得到施工授权。阶段 B 的 Authority 只能把本合同翻译成可执行字段、Schema 和
测试常量；完全一致的 Authority 首次提交视为本次授权下的冻结，不需要再次请求批准。任何
新增 target、feature、模型、门槛或语义偏移都超出授权，必须停止并请求人类决定。

### 1.2 新 session 开工顺序

新 session 必须从干净、已同步且包含本合同的 `main` 开始：

```bash
cd /Users/logan/MatSHIX
git fetch --prune origin
git status --short --branch
git branch -avv --no-abbrev
git worktree list --porcelain
git rev-parse main
git rev-parse origin/main
git tag -n99 archive/matshix-v2.2.3-development-fail
```

必须先验证：

- 本地 `main`、tracking `main` 与远端 `main` 完全一致；
- 工作树干净；
- 只存在主线和当前 V3 施工所需分支，不恢复 V2 开发分支；
- V2 失败归档 commit 为
  `93f883b063953525890430ae54731f23da354659`；
- ShortVol 文件与本合同第 2 节 hash 一致。

然后创建分支：

```bash
git switch -c codex/matshix-weather-v3
```

阶段 A 只做业务、数据和代码审计。阶段 B 必须先提交纯文档
`MATSHIX_V3_AUTHORITY.md`；Authority 提交前不得修改 V3 模型语义代码。

### 1.3 历史、回顾性与前向证据

`2020-01-02..2026-06-05` 及当前本机所有已经查看过的 AETF 历史，统一标记为：

```text
RETROSPECTIVE_DEVELOPMENT / RESEARCH_ONLY
```

即使使用严格 walk-forward OOF，它仍然只能验收因果实现和回顾性研究性能，不能被描述为
未见样本确认。V3 候选冻结之后新到达且未参与设计的数据，才可进入：

```text
PROSPECTIVE_FORWARD
```

历史补齐、重新下载或扩大 era 不会把旧日期升级成前向证据。分钟 close 的历史 Q 永远是
`RESEARCH_MINUTE_CLOSE`；正式 Q 只来自候选冻结后按时保存的 PIT 双边盘口收据。

---

## 2. 开工基线与不可变输入

新 session 在 `MATSHIX_V3_BASELINE_MANIFEST.json` 中记录实际 contract commit、运行时、
AETF 目录、数据覆盖和以下 hash：

```text
stable parent main
  ca32d3bbe175c84ea16e3c9b265b679896d23c6e

V2 failed archive commit
  93f883b063953525890430ae54731f23da354659

V2.2.3 Authority from archive
  d47dc66aac34061d0b7287d6caa7877f3077d7f7aca1cd158b5d3805315de665

V2.2.3 adjudication from archive
  31d4b2721f5faf3fb41141bf89f1a6381d6a0955ab48cb26d7aa5bd0bebdc522

V2.2.3 failure ledger from archive
  eaef94437687b4a854c3e7b4f386819cc904105b1e7ed1e392798512671d0a5e

src/matshix/research/shortvol.py
  8ff1e988937229abf591dde95b0d0b796fb756e9b2dd988ec11da4260c6641c8

src/matshix/research/shortvol_timing.py
  1034a0d942491ab084ee2ac20e7a172ea678927d829907aa0fccd5fd69bd0cd6
```

开工基线必须运行：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src/matshix
.venv/bin/python -m build
.venv/bin/python -m matshix doctor \
  --project-dir . \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF
```

任一基础检查失败时，先登记 `BASELINE_FAIL` 并停止语义施工。不得把既存失败混入 V3
结果，也不得修改 ShortVol 代码来使 V3 通过。

---

## 3. 冻结时间轴、Outcome 与单位

### 3.1 时间轴

```text
forecast_session              = t
historical feature cutoff     = completed exchange session t-1
historical Q known_at         = t 14:56:59 Asia/Shanghai
consumer decision as_of       = next exchange session 09:00 Asia/Shanghai
H20 outcome sessions          = t+1 .. t+20
```

任何训练 target 只有在其完整 H20 outcome 已于当前 `known_at` 之前结束时才可进入训练。
当前行、重叠但未完成的 outcome、未来分位和全样本标准化均禁止。

### 3.2 Primary outcome

V3 唯一核心预测 target：

```text
daily_total_variance[d]
  = adjusted five-minute intraday squared-log-return sum
  + adjusted close-to-next-open squared-log-return

rv_variance_h20[t]
  = (252 / 20) * sum(daily_total_variance[d], d=t+1..t+20)
```

单位固定为 `annualized variance`，不是 volatility、百分比波动或 option P&L。

Authority 必须逐项冻结复权坐标、午休、停牌、缺 bar、隔夜、目标结束日、censoring 和
`outcome_available_at`。V2 outcome 代码只能作为候选实现；未来数据变异测试不通过就不得复用。

### 3.3 非核心物理事实

V3 ledger 可以继续记录：

```text
max_up_log_move_h10
max_down_log_move_h10
```

它们是连续 outcome 事实，不进入 V3 核心接受门。V3 不发布由
`move > q_expected_move` 定义的“纯 P”二元概率。若以后需要路径概率模型，必须另立 Authority，
冻结不依赖 Q 的经济阈值、样本功效和独立验收。

---

## 4. P_PRIMARY_HAR：物理风险主站

### 4.1 模型注册表

V3 只允许以下三个 P 候选：

```yaml
B0_ROLLING_CLIMATOLOGY:
  target: log(max(rv_variance_h20, 1e-12))
  history: prior 252..504 outcome-complete rows
  output: exp(mean(log_target))

B1_EWMA94:
  recurrence: variance_t = 0.94 * variance_t_minus_1 + 0.06 * return_t_squared
  output: 252 * variance_t

P_PRIMARY_HAR:
  kind: ridge_log_variance
  alpha: 1.0
  target: log(max(rv_variance_h20, 1e-12))
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
```

冻结特征：

```text
log_rv_d1_lag1       = log(252 * daily_total_variance[t-1])
log_mean_rv_d5_lag1  = log(252 * mean(daily_total_variance[t-5..t-1]))
log_mean_rv_d22_lag1 = log(252 * mean(daily_total_variance[t-22..t-1]))
```

每次训练最少 252、最多此前 1,260 个 outcome-complete rows。median imputation、mean/std
标准化与 Ridge 拟合只能使用当次训练窗；当前行使用同一变换。零标准差、非有限值或训练不足
均发布明确 `UNOBSERVABLE`，不得静默替代。

P 主站的当前资格和历史训练资格不得依赖：

- H10 Q、H20 Q 或 Q−P；
- H4 完整性；
- 期权上市月份、wing 或合约数量；
- 策略机会日、交易结果或收益。

### 4.2 因果预测区间

80% 区间使用此前已经发布的 OOF log error：

```text
error_s = log(outcome_s) - log(published_forecast_s)
history = prior 126..504 matured OOF errors
low/high = current forecast * exp(empirical_quantile(error_history, 10%/90%))
```

禁止用当前拟合训练窗的 in-sample residual 伪装 OOF 区间。少于 126 个 matured OOF error
时只发布 point estimate，区间状态为 `INSUFFICIENT_INTERVAL_HISTORY`。

### 4.3 回顾性 P 接受门

统计协议冻结为：

```text
QLIKE(y,f) = y/f - ln(y/f) - 1
bootstrap = MOVING_DATE_BLOCK
repetitions = 2000
block_length_sessions = 20
confidence = 90%
seed = 2026082401
```

coverage 分母仅为：H20 target 已完成、并且当天已有至少 252 个因果可训练 target 的日历机会。
Q 或 H4 不得进入分母。P 主站必须全部满足：

```text
paired finite point rows >= 252
point forecast coverage >= 70%
paired QLIKE skill vs min(B0, B1) >= 2%
90% moving-block bootstrap skill lower bound > 0
absolute normalized bias <= 20%
finite positive forecasts = 100% of published forecasts

paired causal interval rows >= 126
80% interval empirical coverage in [65%, 95%]

causal extreme cohort rows >= 20
P_PRIMARY_HAR extreme-cohort QLIKE <= best baseline extreme-cohort QLIKE
```

extreme cohort 在每个 forecast 日只用此前最多 504 个 matured outcomes 的 90th percentile
定义，当前 outcome 不得参与阈值。P 任一核心门 FAIL 或样本不足时：

- `P_CORE_H20 = FAIL` 或 `INSUFFICIENT_EVIDENCE`；
- 停止 Q−P 与候选冻结；
- Q 独立工程与研究事实可以继续；
- 不得在看结果后改模型、删尾部日期或降低门槛再称为同一次验收。

---

## 5. Q_WEATHER：期权定价站

### 5.1 Q 的职责

Q 只发布期权定价事实：

```text
q_variance_h20
q_total_variance_h20
parity_forward
exact_target_bracket
wing_coverage / dominant_side
up_tail / down_tail
surface_status / issues
known_at / evidence_tier
```

H20 Q 必须使用 exact target bracket 与 total-variance interpolation；不得用 nearest expiry
或 H10 是否存在决定 H20 可用性。`q_variance_h20` 固定为 252 日年化方差：

```text
q_total_variance_h20 = q_variance_h20 * target_year_fraction
```

缺 bracket、wing、parity 对或合法价格时保持 `UNKNOWN` 并保存原因。不得补腿、外推假盘口、
用模型价格替代真实 observation，或把分钟 close 称为成交 mid。

### 5.2 历史研究 Q

历史价格源固定为 AETF `14:56 minute close`：

```text
evidence_tier = RESEARCH_MINUTE_CLOSE
formal_pit_claimed = false
```

研究 Q 的接受只证明公式、期限、单位、因果性、可用率披露与确定性 replay 正确。历史研究
coverage 没有 70% 硬门；缺失就是观测事实，不能阻断 P。

### 5.3 正式前向 Q

候选冻结后，primary=`14:56 as-of last`，comparator=`14:56 bid/ask midpoint`。正式 Q 必须：

```text
paired exact H20 rows >= 126
paired exact H20 coverage >= 70%
median absolute relative q_variance delta <= 5%
p90 absolute relative q_variance delta <= 15%
exact-bracket availability agreement >= 95%
wing dominant-side agreement >= 90%
90% moving-date-block CI of median signed delta within [-5%, +5%]
```

bootstrap 固定 2,000 次、20-session block、seed `2026082402`。样本或 coverage 不足为
`INSUFFICIENT_EVIDENCE`，不是 FAIL，也不得用历史分钟 close 顶替。

---

## 6. P_HAR_Q_CHALLENGER：隔离的增量检验

外部论断“Q 必然污染 P”不作为合同事实。V3 允许且只允许一个预先固定的增量模型：

```yaml
P_HAR_Q_CHALLENGER:
  kind: ridge_log_variance
  alpha: 1.0
  target: log(max(rv_variance_h20, 1e-12))
  features:
    - log_rv_d1_lag1
    - log_mean_rv_d5_lag1
    - log_mean_rv_d22_lag1
    - log_q_variance_h20
  required_current_q: exact H20 only
```

它不得使用 H4、H10 Q、term ratio、tail bundle、自动特征搜索或策略结果。训练、变换、区间
和因果规则与 P 主站相同。

比较必须在主站与 Challenger 同时可评价的完全相同日期上进行；主站仍可合法使用全部此前
outcome-complete 历史训练，不得人为降到 Q/H4 子样本。晋级为未来 P 主模型的研究资格必须：

```text
paired rows >= 252
eligible-Q opportunity coverage >= 70%
QLIKE skill vs P_PRIMARY_HAR >= 2%
90% moving-block bootstrap skill lower bound > 0
absolute normalized bias <= 20%
causal interval empirical coverage in [65%, 95%]
extreme-cohort QLIKE <= P_PRIMARY_HAR extreme-cohort QLIKE
```

Challenger 未通过时记录 `REJECTED_CHALLENGER`，不改变 P 主站、Q 站或 Q−P 定义。通过也
只能成为 `PROMOTION_CANDIDATE`；没有新的 Authority 和前向证据，不得自动替换主站。

---

## 7. H4 裁决

V2 本地证据显示：

- H4 完整样本不是随机子样本，高风险未来窗口在 H4 缺失组更常见；
- 完整 15 特征矩阵存在精确仿射依赖：

```text
downside_price_shock + upside_price_shock
  - 1.2 * common_iv_shock == 40
```

因此 V3 核心模型和固定 Challenger 都不得读取 H4。Q 站仍可把 H4 的双侧状态作为当前
市场描述发布，但必须：

- 明确 `DESCRIPTIVE_Q_WEATHER`，不称为 P 预测；
- 缺失时保留 UNKNOWN，不删除对应 P 机会日；
- 保留原始事实，禁止把精确冗余三元组同时送入线性模型；
- 未来任何 H4 predictor 另立 Authority，并先通过矩阵秩、缺失选择和固定特征验收。

---

## 8. Q_MINUS_P_H20：同期限方差补偿

只在 `P_CORE_H20 = PASS` 且当日 Q 有效时计算：

```text
qp_variance_premium_h20 = q_variance_h20 - p_primary_variance_h20
qp_interval_low         = q_variance_h20 - p_interval_high
qp_interval_high        = q_variance_h20 - p_interval_low
ex_post_q_minus_realized = q_variance_h20 - rv_variance_h20
```

状态语义：

```text
THICK_COMPENSATION  interval_low > 0
THIN_COMPENSATION   interval_high < 0
UNCERTAIN           interval crosses 0
UNOBSERVABLE        Q or P/interval unavailable
```

历史分钟 close 只能发布 `RESEARCH_QP_ESTIMATE`。正式 Q−P 必须等待正式前向 Q。任何输出
必须同时保存 Q/P 版本、hash、known_at、horizon、单位与 evidence tier。

回顾性方向研究门：

```text
paired rows >= 126
Spearman(qp_gap, ex_post_q_minus_realized) > 0
causal top-minus-bottom quintile mean difference > 0
90% moving-block bootstrap lower bound > 0 for at least one statistic
sign-confident coverage >= 30%
Q availability coverage separately disclosed
```

门未通过只表示 `QP_DIRECTION_NOT_VALIDATED`；公式正确的 Q−P 事实仍可研究发布，但不得称为
已证明的择时器。不得把 Q−P 正值直接翻译成卖波动许可。

---

## 9. 接受矩阵与停止语义

每一维独立裁决：

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

只允许：`PASS / FAIL / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE`。顶层状态：

```text
V3_BUILD_VALID
  ENGINEERING + OUTCOME_INTEGRITY PASS

V3_RESEARCH_CORE_ACCEPTED
  V3_BUILD_VALID + P_CORE_H20 + Q_RESEARCH_INTEGRITY
  + QP_CONSTRUCTION_INTEGRITY PASS

V3_CANDIDATE_FROZEN
  V3_RESEARCH_CORE_ACCEPTED 后冻结代码、模型、Schema、hash 与前向协议

V3_FORWARD_ACCEPTED
  候选冻结后 FORWARD_Q + FORWARD_P 达到冻结样本门并 PASS

V3_NOT_READY
  任一必需核心门 FAIL、证据不足或 provenance 不完整
```

`P_HAR_Q_CHALLENGER` 和 `QP_DIRECTION_RESEARCH` 都不是核心发布的必需门。这样既不允许
Challenger 劫持主站，也不靠删除有价值的研究维度制造绿色状态。

---

## 10. 施工阶段

### 阶段 A：只读审计

必须完成：

1. 验证 main、origin、runtime、AETF、V1 确定性与 ShortVol hash；
2. 读取 V2 归档 Authority、裁决和失败台账，核对归档 hash；
3. 建立 V3 confirmed-defect ledger；
4. 审计 V2 outcome/Q/provenance 哪些函数可独立复用；
5. 确认策略收益、策略 ledger 和 P&L 未被读取。

阶段 A 不修改模型，不跑逐日策略收益，不用策略表现决定天气特征。

### 阶段 B：Authority 冻结

创建 `MATSHIX_V3_AUTHORITY.md`，逐项冻结：

- era 与证据层；
- forecast/known_at/outcome 时间轴；
- outcome、P、Q、Q−P 公式和单位；
- 模型注册表、训练窗、变换、区间；
- opportunity/coverage 分母；
- bootstrap seeds 与所有 acceptance gates；
- Schema、状态、UNKNOWN 和停止语义；
- 禁止输入与候选前向协议。

Authority 必须先作为纯文档提交。其 SHA-256 写入后续所有产物。

### 阶段 C：最小实现

只建设一条 `CSI300_LOCAL` 链：

```text
outcome ledger
→ P primary ledger
→ Q research ledger
→ Q−P ledger
→ optional HAR+Q comparison
→ score/adjudication/failure ledger
```

优先就地复用通过审计的小函数；不得复制成第二套通用研究平台。CLI 只增加一个明确入口，
建议为 `matshix build-v3-research`。运行时、Schema 和版本变更保持最小。

### 阶段 D：测试

至少覆盖：

- target 结束日、隔夜、复权、缺 bar 与 censoring；
- 当前或未来 outcome 变异不改变过去预测；
- P 在 Q/H4 全缺时仍正常出勤；
- H20 Q 不依赖 H10；
- exact bracket、单位与 total variance identity；
- OOF interval 只读先前 matured forecast errors；
- Challenger 只含四个冻结特征；
- H4 精确共线事实被拒绝进入模型；
- Q−P 同期限、同单位和区间恒等式；
- deterministic replay；
- 禁止导入策略 ledger、P&L、position、leg、exit 或 return。

### 阶段 E：一次完整历史施工

Authority、实现和测试分别提交后，才允许对冻结历史执行第一次完整构建。第一次结果就是
裁决结果；FAIL/INSUFFICIENT 不得通过修改门槛、删除日期、改 seed 或增加特征“重跑冲关”。

若发现的是 confirmed implementation defect：

1. 保存失败产物与 hash；
2. 写明 defect、影响范围和为何不是统计失败；
3. 先冻结补充 Authority；
4. 修复后以新版本重新完整裁决，不覆盖旧证据。

### 阶段 F：候选与前向

仅 `V3_RESEARCH_CORE_ACCEPTED` 后可生成 `MATSHIX_V3_CANDIDATE_FREEZE.json`。冻结后：

- append-only 保存预测、Q 收据、known_at、输入 hash 与 maturity receipt；
- 目标未成熟保持 `PENDING`；
- 数据缺口保持 `UNKNOWN/GAP`；
- 不回填、不重算旧预测、不移动窗口；
- 前向样本不足保持 `INSUFFICIENT_EVIDENCE`。

冻结后的 `FORWARD_P` 使用与第 4.3 节相同的 QLIKE、bias、coverage、interval、extreme
cohort 和 bootstrap 定义，并额外固定：

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

如果前向样本达到 126 但 extreme cohort 仍少于 12，`FORWARD_P` 保持
`INSUFFICIENT_EVIDENCE`；不得取消尾部门。正式 `FORWARD_Q` 继续服从第 5.3 节的 126
paired exact H20 与其他全部 robustness 门。

本合同不授权任何交易策略外部探针；先把气象站建好并独立验收。

---

## 11. 产物合同

V3 分支至少产生：

```text
MATSHIX_V3_AUTHORITY.md
MATSHIX_V3_BASELINE_MANIFEST.json
MATSHIX_V3_DEVELOPMENT_ADJUDICATION.md
MATSHIX_V3_FAILURE_LEDGER.json

data/processed/v3/csi300_outcome_ledger.parquet
data/processed/v3/csi300_p_ledger.parquet
data/processed/v3/csi300_q_ledger.parquet
data/processed/v3/csi300_qp_ledger.parquet

outputs/v3/development_score.json
outputs/v3/failure_ledger.json
```

候选通过后才允许：

```text
MATSHIX_V3_CANDIDATE_FREEZE.json
data/processed/v3/csi300_forward_ledger.parquet
outputs/v3/forward_score.json
```

大数据产物继续由 `.gitignore` 管理；裁决文档和小型 failure ledger 进入 Git。所有裁决必须
记录 Authority hash、实现 commit、输入 manifest、命令、起止时间、输出 hash 和 dirty-tree
状态。

---

## 12. 核心停止条件

以下任一发生，立即停在相应层：

- main/origin、Authority、ShortVol 或基线 hash 不一致；
- runtime、测试、lint、mypy、build、doctor 或 AETF 基线失败；
- outcome 存在未来泄漏、单位错误或不可解释的日期缺口；
- P 核心门 FAIL 或证据不足；
- 需要 Q/H4 才能让 P 出勤；
- Q 缺失被最近期限、模型价格或策略信息填补；
- Q−P 两边 horizon、单位、known_at 或 evidence tier 不一致；
- 区间使用 in-sample residual 或 bootstrap 改 seed；
- 结果出现后试图改门槛、特征、era 或删尾部样本；
- 读取选腿、仓位、退出、策略收益或 P&L 修补天气站；
- 证据不足却准备生成候选冻结或正式发布声明。

停止时必须保存失败产物 hash，发布真实裁决。不得通过概率降门、模型堆叠、机会日筛选或
策略收益把气象站补成绿色。

---

## 13. 完工定义

V3 回顾性施工完成必须同时具备：

```text
clean worktree
frozen Authority hash
baseline manifest
full tests / Ruff / Mypy / build / doctor PASS
deterministic real-data replay
outcome/Q/P/Q−P ledgers and hashes
independent acceptance matrix
development adjudication
failure ledger, including zero failures when applicable
strategy_inputs_used = false
formal_pit_claimed = false unless forward Q actually passes
```

V3 回顾性通过不等于正式前向通过，更不等于策略可交易。正确交付是可复现的天气事实与明确
证据边界，不是一个绿色标签。

---

## 14. 新 session 第一条施工指令

新 session 必须收到以下完整指令：

```text
逐字阅读 MATSHIX_V3_CONSTRUCTION_PLAN.md，把 HUMAN_FROZEN / EXECUTION_AUTHORIZED
版本作为施工流程合同。先验证 main/origin、runtime、AETF、V1 确定性基线和 ShortVol
hash，并验证 archive/matshix-v2.2.3-development-fail 的 commit 与三份证据 hash。
从已同步 main 创建 codex/matshix-weather-v3。阶段 A 只做业务、数据和代码审计，不读取
逐日策略收益；不得 merge 整条 V2 失败归档。先提交纯文档 MATSHIX_V3_AUTHORITY.md，
冻结 era、outcome、P_PRIMARY_HAR、Q_WEATHER、Q−P、HAR+Q Challenger、targets 和
acceptance gates，再按 confirmed defect 逐项施工。P 主站不得依赖 Q/H4；H4 不进入核心
模型；Q 缺失不得阻断 P。任何核心门 FAIL 或证据不足时停止，保存失败产物 hash，不得通过
选腿、仓位、退出、概率降门、删样本或策略收益给气象站补洞。
```
