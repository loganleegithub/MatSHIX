# MatSHIX 工程接管裁决

日期：2026-08-21

## 最小最终系统

最终系统必须让交易员从同一份可重建数据中看清：

1. 哪个经济指数的保险价格先变化；
2. 尾部偏下行、上行还是双向；
3. 压力是否跨大盘、中盘、科创扩散；
4. 压力停留在近端还是进入 30–90 日；
5. 市场仍在恶化还是开始修复；
6. 五个明确未来状态事件相对历史基准的概率判断。

必须同时具备真实历史回放、JSON/Parquet、Dashboard、测试与可见的数据证据层。必要的 PIT、版本和输入摘要只服务于复现这条业务链，不建设独立治理平台。

## 对交付 ZIP 的取舍

不整包导入。经隔离审查后只复用并重新验证以下思想或小模块：

- Black forward 定价、隐含波动率 root；
- 总方差固定期限插值与 forward variance；
- 三值逻辑、mid-rank 百分位；
- 顺序 BaseRate、Logistic OOF、Platt 与 Brier/ECE 公式；
- 四指数权重、三风险段和确定性叙事模板。

交付包的 pipeline、replay、输出、Dashboard 和 release runner 不进入本项目，因为它们未把 PIT/许可接入正式计算，聚合分位、交易日连续性、概率 artifact 和不可变重放也存在已证实缺陷。

## 真实数据模式

本机 `/Users/logan/OptiMatrix_DATA/AETF` 覆盖 2023-01-03 至 2026-06-05 的真实分钟/日线数据。四个正式载体均可找到，且 14:56 分钟行完整；但数据只有 OHLCV/OI，没有 bid/ask。

因此冻结两个方法版本：

- `MATSHIX_STRICT_SURFACE_V1`：正式双边盘口方法，输入不满足时返回 UNKNOWN。
- `MATSHIX_RESEARCH_MINUTE_CLOSE_V2`：以 14:56 分钟 `close` 作为研究价格；使用同执行价 call-put parity、模型自由方差、总方差期限插值，以及下述有距离上限并显式标记 method 的研究代理。输出固定 `evidence_tier=RESEARCH_ONLY`。

研究层纳入条款字段可识别、call/put 可按相同 strike 配对的标准与调整合约；contract unit 只保留为名义条款，不缩放每份 ETF 报价。模型自由积分最小网格冻结为 4 个 OTM put、K0、4 个 OTM call（共 9 点）。这是为真实分钟收盘研究数据单独验证的口径；正式 `MATSHIX_STRICT_SURFACE_V1` 仍保留 12 点候选门槛，并须在授权 bid/ask 上独立验收。

`MATSHIX_RESEARCH_MINUTE_CLOSE_V2` 在固定期限无法上下夹逼时，只允许选取距离 30/60/90 日分别不超过 18/35/45 日的最近真实到期，并标记 `NEAREST_EXPIRY_PROXY`；25D 无法夹逼时，只允许使用距离目标 Delta 不超过 0.12 的最近真实 OTM 腿，并标记 `NEAREST_DELTA_PROXY`；ATM 最近腿的 `abs(log(K/F))` 不得超过 0.08。代理值不称为 strict bracket，不做期限或翼部外推，并与 exact interpolation 覆盖率分开报告。

研究分位至少使用 126 个历史有效样本；20 日 IV vol-of-vol 使用最近 80 个交易日窗口内最后 20 个有效逐日 IV 变化，不插值缺失 IV，并保存实际 observation span。正式层仍要求 252 个历史样本，并在正式连续曲面上重新验收。这些研究门槛必须在覆盖报告中显式出现，不能与正式状态混称。

研究方法不伪造 bid/ask 或 relative spread。其折现因子优先从多执行价 put-call parity 的稳健斜率估计；估计不可用时该到期无效，不使用静默固定利率。

## 验收定义

研究级真实数据验收通过要求：

- 原始输入只来自 AETF Parquet，验收运行不读取合成 fixture；
- 四载体和四指数完整，STAR50 仅由 588000 形成；
- 报告 carrier × year 的 IV30/IV90/25D 覆盖率；
- 七分数、六答案、唯一 phase 与证据叙事可顺序重放；
- 五事件标签不把缺口/末端当 0，概率至少诚实落到 BaseRate 或 INSUFFICIENT_HISTORY；
- JSON、Parquet 与 Dashboard 对最后一个共同真实交易日一致；
- pytest、Ruff、Mypy、build 全部通过。

正式验收另需：授权双边快照、PIT availability、每日合约条款/公司行动、正式折现曲线与许可凭证。缺少任一项时正式状态保持 UNKNOWN。
