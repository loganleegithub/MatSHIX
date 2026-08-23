# MATSHIX V2.2.3 AUTHORITY

- 状态：`FROZEN_FOR_FIRST_RERUN`
- 冻结时间：`2026-08-23T16:59:56Z`
- 冻结分支：`codex/matshix-weather-v2-2-local`
- Authority 版本：`2.2.3`
- 父 Authority SHA-256：`5f21d1f2842ae91a0a845324b3823302f33da54a39efa9ae847b7d40b20d056b`
- 父开发裁决 SHA-256：`3b834c22871a935690cca2481302d45b3809ee7f3791490c374e85ff354dc10a`
- 父失败台账 SHA-256：`9e3db4b51c5db2b013b61c6eb0633ad232c5ed87fbe799b394bad08a822824d8`
- 人类授权：`按照以上分析直接在本分支上修改了后施工重跑`

本补充只修复 H10/H20 C2 的跨期限强制绑定及其 coverage 分母。V2.2.2 的
`DEVELOPMENT_ERA = 2020-01-02..2026-06-05`、`MINUTE_CLOSE_1456 / RESEARCH_ONLY`、
targets、Q、H4、Q−P、252/126/70% 数值门、bootstrap、skill gates、UNKNOWN 语义和禁止
事项全部继承，不得在看到本次结果后修改。

## 1. 缺陷裁决

V2.2.2 要求每个 C2 当前行和训练行同时存在 exact H10、exact H20 与完整 H4，且两个
C2 都使用 `q_term_log_ratio_h10_h20`。这是 `CONFIRMED_CONTRACT_DEFECT`：H20 variance
只需要 H20 Q，H10 path 只需要 H10 Q，另一期限不是相应 target 的必要信息。

V2.2.2 的 1,263 个 H20 calendar opportunities 中，H10/H20/H4 同时可用 284 行
（22.49%）。该数值是本地历史样本的经验联合可用率，不称为交易所到期月份的理论定理。

## 2. Horizon-local C2 registry

### 2.1 H20 variance C2

```yaml
target: rv_variance_h20
required_current_q: exact H20 only
eligible_training_rows: prior outcome-complete rows with exact H20 and complete H4
features:
  - log_rv_d1_lag1
  - log_mean_rv_d5_lag1
  - log_mean_rv_d22_lag1
  - log_q_variance_h20
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

仍要求至少 252 个 eligible training rows，最多使用此前 1,260 行。H10 Q 不得决定 H20
C2 的训练资格、当前资格或输出。

### 2.2 H10 upside/downside C2

每侧继续独立拟合；B1 特征不变。

```yaml
target: corresponding side_path_breach_h10
required_current_q: exact H10 only
eligible_training_rows: prior outcome-complete rows with exact H10 and complete H4
features:
  - B1_REALIZED_PATH features
  - log_q_variance_h10
  - side_tail
  - side_raw_wing_skew
  - side_tail_persistence
  - side_repair
```

仍要求至少 252 个 eligible training rows、至少 20 positives 和 20 negatives，最多使用此前
1,260 行。H20 Q 不得决定 H10 C2 的训练资格、当前资格或输出。

### 2.3 Term diagnostic

`q_term_log_ratio_h10_h20` 继续保存在 ledger，身份降为 `DIAGNOSTIC_ONLY`。它不得进入
任一 primary C2、训练资格或当前发布资格；未来若要恢复，只能作为新 Challenger 另立
Authority，不能回写本次 primary 结果。

## 3. Coverage 合同

70% 阈值不变，但 coverage 必须衡量“模型在因果上已具备其自身冻结输入和训练样本时是否
稳定出勤”，不能把交易所期限结构造成的另一 horizon 缺失算作该模型缺勤。

每个 target 分别记录三层数量：

```text
calendar_opportunity:
  当前 target 已完成，且已有至少 252 个通用 outcome-complete 历史 target；
  H10 path 另要求通用历史标签至少 20 positive / 20 negative。

horizon_input_ready:
  calendar_opportunity 且当前 target 自身期限 Q exact、H4 complete。

model_opportunity:
  horizon_input_ready 且此前该期限的 eligible training rows >=252；
  H10 path 另要求该期限训练 cohort 至少 20 positive / 20 negative。
```

冻结计算：

```text
raw horizon input availability = horizon_input_ready / calendar_opportunity
eligible model coverage = finite C2 output / model_opportunity
```

前者必须披露，但在本 `RESEARCH_ONLY` 历史 cohort 中不是 70% 模型出勤门；后者继续必须
`>=70%`。分母为零或 paired rows 少于 126 仍是 `INSUFFICIENT_EVIDENCE`，不得据此降门。
H10 每侧的 20/20 评价样本门继续在 model opportunities 上执行。

## 4. 首次重跑与停止边界

Authority 独立提交后才可改代码。实现与测试独立提交后只执行一次完整真实重跑。结果只允许
`DEVELOPMENT_PASS / DEVELOPMENT_FAIL / INSUFFICIENT_EVIDENCE`；任一核心门 FAIL 或
证据不足时停止受影响施工线。不得读取选腿、仓位、退出、概率降门或策略收益，不得用 nearest
expiry、填 Q 或其他 horizon 给气象站补洞。所有 V2.2.0–V2.2.2 历史产物与 hash 保持不变。
