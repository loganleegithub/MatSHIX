# MatSHIX 上交所 ETF 期权保险市场叙事与概率引擎开发规格

> 文档状态：`A0_IMPLEMENTATION_READY_G0_NOT_PASSED`<br>
> 规格版本：`1.0.0`<br>
> 决策日期：2026-08-20<br>
> 产品频率：上交所期权交易日日频，固定收盘前曲面截面 + 盘后官方数据<br>
> 当前开工边界：允许开发数据合同、公式、合成测试与本地骨架；真实状态发布、概率发布和对外展示须依次通过本文数据与验证闸门<br>
> 本文角色：MatSHIX v1 的产品与技术规格；不是交易建议、数据采购授权、部署授权或 Sober 私有算法复刻声明

---

## 0. 开工结论

MatSHIX 要构建的不是一个“中国 VIX”单数字，也不是预测 A 股涨跌的预言机。它是一座读取**选定上交所 ETF 期权保险市场**的日频量化气象站：先分别重建四个正式 ETF 期权盘口，再将其解释为四个经济指数的保险价格，最后回答压力位于哪里、是否扩散、尾部偏向哪一侧、是否持续以及是否修复。

MatSHIX 每天必须完成两个核心任务：

1. **当前市场叙事**：解释保险价格水平、重定价速度、下行/上行尾部、期限持续性、横截面宽度与修复状态；
2. **未来状态判断**：对未来 1、5、20 个交易日内五类明确定义的状态事件给出历史基准率；只有经真正样本外验证和校准后，才给出特征条件概率。

本项目当前能够立即冻结的是：

- 产品边界、市场对象与证据语言；
- 原始数据和 point-in-time 合同；
- 曲面、期限、偏度、VRP、横截面和状态的透明基线公式；
- 状态枚举、事件标签、概率真值表、输出 schema 和测试边界；
- MatVIX 中可复用的软件骨架与必须重写的市场专属部分。

本项目当前**不能声称已经具备**的是：

- 已采购、获许可并成功读取的四盘口完整历史快照；
- 25 Delta 两翼、30/90 日期限在各品种全历史的有效覆盖率；
- 任何本文阈值或权重的经验最优性；
- 已训练、已校准或可发布的 MatSHIX 概率；
- 已运行、已回放或已验收的 MatSHIX 工程。

因此，本文的准确结论是：

> **MatSHIX 的业务、数学和工程基线已足以启动 A0 合同、骨架与合成公式开发；真实数据链仍处于 `DATA_ACCESS_NOT_VERIFIED`，G1 真实曲面开发须先通过 G0 数据闸门，且不得把合成结果、空壳 Dashboard 或示例概率称为完成。**

---

## 1. 输入材料、证据边界与权威顺序

### 1.1 本次完整阅读的材料

| 材料 | 本次读取版本 | 在 MatSHIX 中的角色 | 不能证明什么 |
|---|---|---|---|
| `/Users/logan/Downloads/晴雨表量化引擎.pdf` | SHA-256 `68bd8003072b9699d43f3b8b7cebc9bb4b9cb25aee65fce35b1bfa39a56439d7` | 产品理念、十五项指标名称与“多源数据 → 晴雨表”的概念来源 | 不能证明私有公式、权重、阈值、八年业绩或可复现交易规则 |
| `/Users/logan/Downloads/Sober VIX Barometer「Data Engine」量化晴雨表：指标拆解、VIX期限结构与双策略映射研究报告.md` | SHA-256 `d840397c9066e104485c546fea50a6628aa037ce33a6ebb24e7eca3f2e1256a9` | 对 PDF 的二手研究解释与候选复现公式；提供期限、尾部、VRP 与技术指标候选 | 其公式不是 Sober 私有公式或上海市场公式；当前副本中的内部引用令牌不可解析，事实必须回到一手官方来源 |
| `/Users/logan/MatVIX/MATVIX_PRE_DEVELOPMENT_REPORT.md` | SHA-256 `dd8ad48f16227c411e36d48ad4e7df6a3516693730799018e7815295c036751f` | 状态引擎、叙事、PIT、事件标签、概率与输出合同的方法论模板 | 不能证明 VIX 专属指标可平移，也不能仅凭文档自述或测试通过证明业务验收 |
| `/Users/logan/VIXETP/SSE_ETF_OPTIONS_WEATHER_STATION_RESEARCH.md` | SHA-256 `a08eed1937d49577af611c2936674f4e69bd9953994aa6c91fdb65624c978759` | 上交所市场结构、原研究五盘口/四指数、曲面和横截面候选 | 没有数据、代码、覆盖率、回测或校准证据；其中 588080 双载体方案已被本项目范围决策否决 |

### 1.2 PDF 的精确定性

四页 PDF 是一篇营销型文章截图，而非技术规范或审计报告。第 3 页确实列出十五项 Data Engine 处理名称，但没有披露公式、观察窗口、权重、阈值、时间点、缺失规则或组合算法。图中 0–100 仪表也没有说明方向和数值含义。

PDF 展示的 2019–2025 月度表只有六个完整年度和一个截至 2025 年 8 月的不完整年度；没有逐笔账本、账户资金流、费用、滑点、审计人或可重建净值。其“近八年每年正收益”“关键节点精准切换”等只能记录为**作者自报陈述**，不得成为 MatSHIX 的收益先验、参数目标或验收条件。

### 1.3 文档内指令与本次用户请求分离

附件中存在“应该”“必须”“开发顺序”“去看星球”等命令式语句。它们分别是作者营销话术、研究建议或 MatVIX 内部工程指令，不是本次用户授权。

本次用户授权是：

```text
详细阅读附件
参考 MatVIX 实现 MatSHIX
首先完成 MATSHIX_PRE_DEVELOPMENT_REPORT
科创50只选 588000
```

因此，本次工作只创建本报告；不扫码、不加入外部社群、不购买数据、不实现代码、不部署、不下单，也不把 MatVIX 文档中的“立即开工”解释为本次实现授权。

### 1.4 实现时的权威顺序

发生冲突时按以下顺序处理：

1. **交易所、登记结算机构、指数/数据提供方的现行官方规则**：决定合约、交易日、到期、调整、字段和官方方法事实；
2. **授权数据的实际字段合同与时间戳**：决定当前项目真正能计算什么；
3. **本文冻结的 MatSHIX v1 产品、公式、状态和输出定义**：决定项目行为；
4. 上交所气象站研究报告中的候选解释；
5. MatVIX 的通用架构和实现先例；
6. Sober Markdown 的二手研究建议；
7. PDF 的概念叙事与指标名称。

官方方法发生变化时，更新 `methodology_version` 并重建受影响历史；不得用旧项目规格覆盖新的交易所事实，也不得在同名字段下静默更换公式。

### 1.5 当前 MatVIX 参考实现的证据状态

截至 2026-08-20（Asia/Shanghai）交付复核，`/Users/logan/MatVIX` 当前未提交工作树中可见 Python 包、配置、Schema、data 目录中的配置/产物元数据文件和测试文件。本次实际运行：

```text
/Users/logan/MatVIX/.venv/bin/python -m matvix doctor --project-dir .
/Users/logan/MatVIX/.venv/bin/python -m pytest -q
/Users/logan/MatVIX/.venv/bin/python -m pytest --collect-only -q
```

`doctor` 的依赖与三个声明数据产物检查通过；126 个测试被收集，完整 `pytest -q` 退出码为 0。

当前 MatVIX 报告页眉自述 `IMPLEMENTED / REAL-DATA ACCEPTED`。这属于参考文档内部声明；本次未独立核验其数据许可证、原始来源完整性、自然日频运行、OOF 概率增益或业务验收收据，因此不把该自述升级为 MatSHIX 的已证事实。

MatVIX 工作树在本报告编写期间发生过外部变化；第 1.1 节哈希是本次最终完整阅读并锁定的快照。以后若该哈希变化，复用新增结论前必须重新阅读差异，不能静默把动态工作树当成同一证据版本。

因此：

- 可以参考其目录、PIT ledger、三值逻辑、概率状态和输出接口设计；
- 上述结果只证明当前本地依赖诊断和现有测试套件通过，不能扩张为数据授权、自然市场链、概率增益或端到端业务验收；
- MatSHIX 不依赖相邻 MatVIX 目录运行，也不直接复制 VIX 专属模块。

---

## 2. 产品定义与范围

### 2.1 一句话定义

**MatSHIX 是一个读取上交所四个选定 ETF 期权盘口、形成四个经济指数保险状态并估计未来状态转移概率的日频市场叙事引擎。**

`MatSHIX` 是项目名。本文不把 `SHIX` 声称为上海证券交易所、中证指数公司或其他机构发布的官方指数，也不把 headline score 对外称为“中国 VIX”。

### 2.2 正式市场对象

2026 年 7 月上交所官方行权交收公告列出五个 ETF 期权品种。MatSHIX v1 从中明确选择以下四个正式载体；科创50只选择 588000：

| `carrier_id` | 期权品种 | 标的 ETF | `economic_index_id` | 上市日期 |
|---|---|---:|---|---:|
| `SSE50_510050` | 50ETF 期权 | 510050 上证50ETF华夏 | `SSE50` | 2015-02-09 |
| `CSI300_510300` | 300ETF 期权 | 510300 沪深300ETF华泰柏瑞 | `CSI300` | 2019-12-23 |
| `CSI500_510500` | 500ETF 期权 | 510500 中证500ETF南方 | `CSI500` | 2022-09-19 |
| `STAR50_588000` | 科创50ETF 期权 | 588000 科创50ETF华夏 | `STAR50` | 2023-06-05 |

严格口径为：

```text
4 个正式期权载体
→ 4 个经济指数
→ 3 个不重复计票的风险段：大盘 / 中盘 / 科创成长
```

范围决策是产品合同，不是流动性回退规则：`588080` 不进入 `source_manifest`、采集适配器、曲面、备援、确认、分歧、横截面、概率特征、输出 Schema 或 Dashboard。即使 588000 当日不可用，也不得以 588080 静默替代；STAR50 应保持不可观察。未来若要纳入 588080，必须经新的用户授权和规格版本升级。

### 2.3 MatSHIX 能代表什么

MatSHIX 代表：

- 上交所 50、300、500、科创50 ETF 期权中可观察的保险价格结构；
- 大盘、中盘、科创成长之间的压力位置与扩散；
- 这些市场对象的期限、偏度、VRP、速度和修复。

MatSHIX 不代表：

- 全部 A 股；
- 深交所 ETF 期权、创业板 ETF 期权或其他未纳入品种；
- 中证1000、小盘股、行业期权或个股期权的完整风险；
- 已观察到的机构/散户净买卖方向；
- 任何资产下一日涨跌或策略盈利概率。

### 2.4 v1 必须交付

- 四个正式 ETF 期权载体的独立、可重建 EOD 曲面；
- 四个经济指数的 `IV30 / IV90 / ATM / RR25 / DownSkew25 / UpSkew25 / BF25 / VRP`；
- 科创50由 `STAR50_588000` 单一正式载体形成，且缺失时不使用 588080 回填；
- `InsuranceLevel / Shock / DownTail / UpTail / Persistence / Breadth / Repair` 七个透明分数；
- 六个当前市场答案、一个唯一 `primary_phase`、驱动、反证与改变条件；
- 五个未来状态事件的标签、基准率、样本外概率状态与校准证据；
- JSON/Parquet、历史重放和本地 Dashboard；
- 数据覆盖、曲面质量、模型状态和授权边界的可见说明。

### 2.5 v1 不负责

- 下单、券商连接、仓位、保证金、行权或交收；
- 给出认购/认沽、跨式、价差或 ETF 的目标持仓；
- 将状态概率翻译成交易成功率；
- 复现 Sober 的私有模型或 PDF 自报业绩；
- 盘中高频预警；
- 用 IH、IF、IC 冒充波动率期货；
- 在未取得数据权利时抓网页拼接生产曲面；
- 把示例 JSON 数值当成真实输出。

---

## 3. MatVIX 到 MatSHIX 的结构映射

| MatVIX/SPX-VIX 构件 | MatSHIX 处理 | 裁决 |
|---|---|---|
| VIX9D/VIX/VIX3M/VIX6M | 从每个 ETF 期权链独立重建期限方差 | 保留期限语言，重写全部数据和公式 |
| VX F1–F6、M1/M2、VXCM30 | 上交所没有等价波动率期货曲线 | 删除，不创建伪替代 |
| VVIX | `IV30` 自身的实现波动和变化速度 | 只是代理，字段不得叫 VVIX |
| SKEW/SDEX/TDEX | 25D 风险逆转、上下尾翼、蝶式凸度；10D 仅扩展 | 重建本土曲面指标 |
| Cboe Put/Call | 每个 ETF 的 volume/OI/premium PCR | 保留活动构成，不推断主动方向 |
| SPX/VIX VRP | 每个 ETF 的模型自由 IV 方差减事前 RV 预测 | 重新估计 |
| VIX technicals | 作用于各 ETF 的 `IV30` 和聚合压力 | 只做速度/诊断，不平权投票 |
| 时间维度扩散 | 30–90 日 forward volatility | 保留 |
| 单一 SPX 市场 | 四经济指数横截面；科创50固定由 588000 表达 | 新增核心 Breadth 维度 |
| CarryRisk | 无 VIX futures carry 等价物 | 不保留同名轴；VRP 只描述保险补偿 |
| 当前状态/Repair/概率/PIT | 上海原生指标上的同类架构 | 方法论复用 |

最重要的差异是：

> MatVIX 的独特信息来自 VIX 现货族与 VIX 期货沿时间轴的曲线；MatSHIX 没有波动率期货，必须依赖 ETF 期权自身的期限结构，并增加四个经济指数之间的横截面扩散。

---

## 4. 每天必须回答的七个业务问题

| 输出 | 业务问题 | 合法答案 |
|---|---|---|
| `level_answer` | 30 日保险价格相对各自历史处于什么水平？ | `CHEAP / NORMAL / RICH / EXTREME / UNKNOWN` |
| `shock_answer` | 多个盘口是否正在发生急性重定价？ | `CALM / BUILDING / HIGH / ACUTE / UNKNOWN` |
| `tail_answer` | 尾部定价偏向下行、上行还是双向事件？ | `NEUTRAL / DOWNSIDE_PRICED / UPSIDE_PRICED / TWO_SIDED_EVENT / MIXED / UNKNOWN` |
| `term_answer` | 压力局限在近端，还是进入 30–90 日持续层？ | `NORMAL / FRONT_LOCALIZED / DIFFUSING / PERSISTENT / MIXED / UNKNOWN` |
| `breadth_answer` | 压力是孤立、大盘、中盘/科创局部，还是广泛？ | `NONE / ISOLATED / BLUE_CHIP_LOCALIZED / LOCAL_STYLE / BROAD / SYSTEMIC / FRAGMENTED / UNKNOWN` |
| `repair_answer` | 此前高压之后是否出现可信边际修复？ | `INACTIVE / BUILDING / CONFIRMED / UNKNOWN` |
| `outlook_answer` | 哪个未来状态事件相对自身历史基准最值得关注？ | 事件 ID，或 `NO_STRONG_EDGE / BASE_RATE_ONLY / NOT_APPLICABLE / UNKNOWN` |

前六个答案描述当前市场；`outlook` 描述未来。分数是压缩坐标，不得取代多维解释。

### 4.1 三层语言

任何叙事都必须区分：

1. **直接观察 `OBSERVED`**：报价、成交、持仓、ETF 价格、期限、合约条款；
2. **模型派生 `DERIVED`**：隐含方差、Delta、分位、VRP 代理、分数和状态；
3. **经济解释 `INFERRED`**：保险价格与需求增强、供给环境占优、压力扩散或修复一致。

允许：

> 当前跨执行价价格结构与下行保险相对变贵一致。

禁止：

> 已确认机构正在净买入认沽期权。

公开成交量与 OI 没有主动买卖方向；Put 成交可来自买入保护或卖出 Put，Call 成交也可能来自追涨或备兑卖出。除非未来取得带方向且授权的数据，叙事不得跨越这条证据边界。

### 4.2 当前状态与未来概率分离

- `PressureScore=80` 表示当前输入按冻结规则处于高压力坐标，不表示未来事件有 80% 概率；
- `BASE_RATE_ONLY=18%` 是同类历史发生率，不是当前特征的增量预测；
- `NOT_APPLICABLE` 表示转移问题当前不成立，不等于 0%；
- `UNKNOWN` 与 `null` 表示证据不足，不得用 0 填充。

---

## 5. 日频时点、原始数据与 point-in-time 合同

### 5.1 冻结时点

`session_date=t` 表示被解释的上交所期权交易日。

v1 使用两个同日数据截点：

```text
surface_cutoff = 14:56:59 Asia/Shanghai
daily_close_cutoff = 当日官方盘后收盘/结算文件
decision_as_of = 下一上交所期权交易日 09:00 Asia/Shanghai
```

选择 14:56:59 是为了使用连续竞价结束前的同步双边报价，不把 14:57–15:00 收盘集合竞价的虚拟撮合状态混入核心曲面。每个合约选择 `surface_cutoff` 之前最后一幅合格快照；v1 初始要求每条入选期权腿及 ETF mark 均满足 `0 <= surface_cutoff-event_time <= 5秒`，因此入选集合的最大横截面时差也不超过 5 秒。该容差由 G0 样例验证后写入 `quote_sync_tolerance_seconds`。

进入 Shock/Repair 核心分数的 `etf_return_1d/5d` 使用同一 `surface_cutoff` 前、满足同步容差的 ETF 双边 mid，并按已知分红/公司行动构造总回报标记；不得用 15:00 收盘价反向解释 14:56:59 曲面。盘后总回报收盘序列只用于下一日 09:00 已可见的 VRP 递推和诊断。

如果官方历史产品对未变化快照使用不同时间语义，适配器必须依据真实字段重新冻结规则；不得假装 5 秒条件已经通过。

当日盘后成交、持仓、收盘和结算信息可以进入同一 `session_date` 的活动诊断，因为正式快照直到下一交易日 09:00 才发布。任何 `available_at > decision_as_of` 的数据不得进入当次状态。

### 5.2 每条原始观察必须保存

```text
series_id
carrier_id
economic_index_id
contract_id
session_date
event_time
value
unit
currency
source
source_field
observed_at
available_at
ingested_at
revision_id
methodology_version
vintage_kind
licence_scope
```

`revision_id` 必须由语义内容寻址，至少覆盖 value、unit、source、source_field、economic_index_id、event_time、available_at、contract terms、methodology_version、vintage_kind 与 licence_scope；不能只使用行号或下载时间。

### 5.3 数据 vintage

| `vintage_kind` | 正式当日状态 | 百分位/标签/训练/OOF/校准 | 研究用途 |
|---|---:|---:|---:|
| `OBSERVED_PIT` | 允许 | 允许 | 允许 |
| `ASSUMED_PIT` | 允许；按保守 `available_at` | 允许；产物标 `PIT_EVIDENCE=ASSUMED` | 允许 |
| `PROVIDER_RECONSTRUCTED` | 禁止 | 禁止 | 允许，标 `RESEARCH_ONLY` |

`ASSUMED_PIT` 只允许用于已有官方/提供方发布时限、不可变归档回执或等价证据，能够证明该文件最迟在某个保守时点已经可用、但无法恢复精确秒级时间的情况；此时取证据支持的最迟时点。若文件只证明“属于某交易日”，却没有任何当时可用性证据，不得默认次日 09:00 已知，必须标 `PROVIDER_RECONSTRUCTED + AVAILABILITY_UNPROVEN`，仅进入研究表。

派生值继承所有必需输入中最弱 vintage。任何一个必需输入为 `PROVIDER_RECONSTRUCTED`，该派生行不得进入正式分位、标签、BaseRate、训练、OOF、校准或验收。

### 5.4 核心数据

| 数据 | 最小字段 | 角色 | 当前取得状态 |
|---|---|---|---|
| 四盘口期权快照 | 合约、时间、Bid/Ask 五档、Last、成交量额、OI、昨/今结算 | 曲面与活动 | `NOT_VERIFIED` |
| 合约基础信息 | call/put、strike、expiry、unit、调整标志、标的 | 到期与公司行动 | `NOT_VERIFIED` |
| 四只 ETF 快照与日线 | 价格、成交、IOPV、开高低收、分红/调整 | 远期校验、RV 与辅助解释 | `NOT_VERIFIED` |
| 四经济指数/总回报序列 | 收盘、成分版本 | 市场解释与收益校验 | `NOT_VERIFIED` |
| 上交所交易日历 | session、提前休市、到期/行权日 | 时间边界 | 官方规则可查，项目适配未验证 |
| 折现曲线 | 各到期期限折现因子及可用时间 | 方差和 Black forward IV | 数据源待 G0 冻结 |
| 公司行动 | 分红、除权、合约调整、单位变化 | 连续回放 | 官方公告可查，历史链未验证 |

上证信息官方页面证明股票期权行情包含合约基础信息、五档买卖、成交、持仓和盘后收盘/结算；历史产品包含期权快照、日 K 和分钟 K。它只证明**产品能力存在**，不证明本项目已采购、获非展示许可或成功读取。

### 5.5 扩展解释数据

| 数据 | 用途 | 不可得时行为 |
|---|---|---|
| IH/IF/IC 与对应现货 | 方向性期货基差与期现风险偏好 | 不进入核心分数 |
| ETF IOPV/折溢价 | ETF 特有流动性和申赎偏离 | 不进入核心分数 |
| 融资、融券余额 | 杠杆与借券环境 | 仅诊断；不得命名为保证金变化 |
| 指数成分涨跌停宽度 | 交易约束和下行拥挤 | 仅解释/Challenger |
| 已知事件与长假日历 | 近端事件归因 | 未取得时不生成事件因果 |
| 10 Delta 两翼 | 极端尾部研究 | 25D 核心不受影响 |

IH、IF、IC 是股票指数期货，不是波动率期货。其基差只能解释权益方向性套保、融资和风险偏好，不得替代 VIX futures carry。

### 5.6 数据状态与质量状态

机器可读 `core_required_fields` 在 `state_v1.yaml` 中固定为每个经济指数均能形成：`InsuranceLevel / Shock / DownTail / UpTail / Persistence / Repair / IndexPressure`，且这些分数所需的 strict surface、同步 ETF return、历史 percentile 与方法版本均正式可用。仅有一个 IV 点或研究回算值不算“完整局部状态”。

顶层 `data_status`：

- `OK`：四个经济指数的全部核心轴可计算，且四个正式载体均满足各自核心曲面门槛；
- `PARTIAL`：至少一个、但不足四个经济指数可形成完整局部状态；完整市场分数、phase 和正式概率不可发布；
- `UNKNOWN`：没有任何经济指数可形成完整局部状态，或授权、交易日历、合约主数据、全局时点问题使整条正式核心链不可启动。

`economic_indices[*].data_status` 使用同一枚举，但按单一经济指数判定：

- `OK`：该指数的正式载体满足 strict surface 门槛，且 `core_required_fields` 中七个局部状态及其同步 return、历史 percentile、PIT 与方法版本全部可用；
- `PARTIAL`：尚不能形成上述完整局部状态，但至少一个核心轴或正式质量诊断可计算；它不计入顶层“完整局部状态”的数量；
- `UNKNOWN`：没有任何 PIT-eligible 的局部核心轴可计算，或该载体的授权、交易日历、合约主数据、availability 问题使局部核心链无法启动。

顶层状态只按局部 `OK` 的数量和全局阻断项推导：四个局部均 `OK` 才是顶层 `OK`，一至三个局部 `OK` 为顶层 `PARTIAL`，零个局部 `OK` 为顶层 `UNKNOWN`。局部 `PARTIAL` 只保留可解释观察，不得把顶层从 `UNKNOWN` 抬升为 `PARTIAL`。

`PROVIDER_RECONSTRUCTED` 计算结果只进入独立 `RESEARCH_ONLY` 产物，不让正式 `data_status` 变为 OK；正式状态仍按同时存在的 PIT-eligible 输入判定。

另设独立 `confidence`：

- `FULL`：四个正式载体均合格，且不存在降低解释可信度的非致命质量问题；
- `DEGRADED`：四个经济指数仍完整可覆盖，但存在非致命质量问题；
- `LOW`：只可显示局部观察，通常对应 `PARTIAL`；
- `NONE`：对应 `UNKNOWN`。

合法组合只有：`OK -> FULL|DEGRADED`、`PARTIAL -> LOW`、`UNKNOWN -> NONE`。不得输出其他组合。

问题码至少包括：

```text
NOT_LICENSED
AVAILABILITY_UNPROVEN
MISSING_CONTRACT_MASTER
STALE_QUOTE
CROSSED_QUOTE
INSUFFICIENT_STRIKES
UNBRACKETED_TENOR
DELTA_NOT_BRACKETED
DUPLICATE_STRIKE_CONFLICT
STATIC_ARBITRAGE_VIOLATION
NEGATIVE_FORWARD_VARIANCE
CORPORATE_ACTION_GAP
RATE_CURVE_MISSING
METHODOLOGY_BREAK
```

质量码属于诊断，不应自动变成风险信号。盘口变差可以是真实压力，也可以是数据缺陷；在无法区分时应降低置信度，而不是给 PressureScore 加分。

`PARTIAL` 时允许在 `economic_indices[*]` 展示可计算的局部曲面与局部状态，但顶层六个当前答案均为 `UNKNOWN`，且 `pressure_score=null`、`primary_phase=UNKNOWN`、五个事件全部 `UNOBSERVABLE + NOT_RUN`。`UNKNOWN` 时正式数值派生均为 `null`。不得删除缺失组件后重归一权重。

### 5.7 全局三值逻辑合同

布尔谓词只取 `TRUE / FALSE / UNKNOWN`。任何与 `null` 的数值或枚举比较均为 UNKNOWN；禁止用 Python/SQL 的真假值或 `!= TRUE` 猜测未知。

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | TRUE |
| UNKNOWN | FALSE | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

`NOT TRUE=FALSE`、`NOT FALSE=TRUE`、`NOT UNKNOWN=UNKNOWN`。

对 `n` 个三值谓词，已知 TRUE 数为 `T`、UNKNOWN 数为 `U`：

```text
at_least(k): T>=k -> TRUE; T+U<k -> FALSE; otherwise UNKNOWN
exactly_one: T>1 -> FALSE; T=1且U=0 -> TRUE; T+U<1 -> FALSE; otherwise UNKNOWN
any = at_least(1)
```

计数型字段只在全部成员已知时输出整数，否则为 null；需要阈值判断时直接调用 `at_least(k)`。所有状态、窗口、phase 和事件 eligibility 必须复用这一个逻辑库。

---

## 6. 期权曲面核心数学合同

除第 6.8 节明确标为官方中国波指兼容诊断的部分外，第 6–15 节的公式选择、权重、阈值、状态、事件和模型门槛均是 MatSHIX 新增的透明 baseline；它们不是 PDF/Sober 私有公式，也不是上交所官方 MatSHIX 方法，当前尚未获得真实覆盖或预测有效性验证。

### 6.1 合约与报价准入

每个 `carrier_id × expiry` 独立处理。合约必须满足：

- 属于当日基础信息文件且未到期；
- call/put、strike、expiry、contract unit 和调整版本可识别；
- Bid/Ask 非负、`bid <= ask`、Ask 大于 0；
- 快照满足冻结时点和同步容差；
- 调整合约的 strike/unit 与 call-put 配对一致；
- 价格单位为每份 ETF 的人民币报价，contract unit 只影响名义金额和成交额，不直接缩放 IV。

分红或除权后，不把调整前后合约当同一 `contract_id` 覆盖。若无法重建调整关系，标 `CORPORATE_ACTION_GAP`。

核心曲面只使用合格双边 mid：

\[
Q_{mid}(K,T)=\frac{Bid(K,T)+Ask(K,T)}{2}.
\]

质量字段 `relative_spread=(Ask-Bid)/Q_mid`，仅在 `Q_mid>0` 时定义。`bid=0` 的 OTM 腿不进入方差求和；向翼部扫描时单个零 bid 只跳过该 strike，连续两个零 bid 则同时触发该方向停止规则。报价有效性与“是否纳入积分”是两个独立判定。

Last、昨日结算或单边报价只进入 `SSE_IVX_COMPAT` 诊断，不进入 `MATSHIX_STRICT_SURFACE_V1`。这样会减少覆盖，但避免把陈旧成交伪装成当前保险价格。

### 6.2 时间与折现

到期时点固定为到期日 `15:00:00 Asia/Shanghai`：

\[
T=\frac{expiry\_timestamp-surface\_cutoff}{365\times24\times3600}.
\]

v1 使用 ACT/365F。折现因子 `D(T)` 来自 G0 冻结的官方或授权人民币零息曲线，按当时已知曲线在到期日插值：

\[
D(T)=e^{-r(T)T}.
\]

折现源变化必须升级 `surface_methodology_version`。不得在同一字段中一部分日期用 Shibor、另一部分用国债曲线而不标记。

### 6.3 远期价格

ETF 期权为欧式到期行权；对同 strike 的 call/put，使用 parity 推导远期。parity 候选要求 call 与 put 均为合格双边且 `bid>0`。先在候选 strike 中选择：

```text
K_star = argmin |C_mid(K,T) - P_mid(K,T)|
tie-break 1 = combined relative spread 更小
tie-break 2 = strike 更低
```

其中不得由实现自行选择 `sum/max/mean`；固定定义为两腿相对价差的算术平均，并使用未展示舍入的 canonical decimal 比较：

\[
combined\_relative\_spread(K,T)=\frac{1}{2}\left(
\frac{Ask_C-Bid_C}{C_{mid}}+
\frac{Ask_P-Bid_P}{P_{mid}}
\right).
\]

若 `|C_mid-P_mid|` 完全相等，先取 `combined_relative_spread` 较小者；仍完全相等时取较低执行价。parity 候选已要求两腿 `bid>0`，因此两个分母均为正。

然后：

\[
F(T)=K^*+\frac{C(K^*,T)-P(K^*,T)}{D(T)}.
\]

ETF 预期分红通过 option-implied forward 被吸收；仍需保存官方分红和合约调整用于校验。若没有合格 call-put 对，则该 expiry 不可计算，不使用 ETF 现货和猜测股息替代。

### 6.4 单一到期模型自由隐含方差

令 `K0` 为不高于 `F` 的最大合格执行价。OTM 价格：

```text
K < K0 -> Put mid
K > K0 -> Call mid
K = K0 -> (Call mid + Put mid) / 2
```

执行价间距：

\[
\Delta K_i=
\begin{cases}
K_2-K_1,&i=1\\
(K_{i+1}-K_{i-1})/2,&1<i<n\\
K_n-K_{n-1},&i=n.
\end{cases}
\]

方差：

\[
\sigma^2(T)=
\frac{2}{T}\sum_i
\frac{\Delta K_i}{K_i^2}\frac{Q(K_i)}{D(T)}
-\frac{1}{T}\left(\frac{F}{K_0}-1\right)^2.
\]

翼部从 `K0` 向外扫描；出现连续两个 `bid=0` 的执行价后，停止纳入该方向更远 strike，两个零买价本身也不纳入。这里允许按上一节规则跳过一个孤立零 bid；“中间缺 strike”专指合约主数据预期的执行价或其整幅报价缺失，遇到这种结构洞不跨过后继续拼接。

初始质量门：

```text
valid_otm_puts >= 4
valid_otm_calls >= 4
valid_total_strikes >= 12
K0 call/put pair exists and both bids > 0
sigma_squared > 0
```

这些数量是可开发的首版门，不是已证明最优；G2 必须报告每个载体和到期的通过率。若大量真实交易日无法通过，应升级方法版本或改变核心范围，不得静默放宽。

### 6.5 固定期限 IV30/IV60/IV90

单一到期总方差：

\[
W(T)=T\sigma^2(T).
\]

对目标期限 `H ∈ {30,60,90}` 日，必须找到两个合格到期 `a,b`：

```text
DTE_i = 365*T_i  # 由秒级时间得到的非取整自然日
```

```text
DTE_a <= H < DTE_b
两者 DTE 均 > 7 个自然日
```

按总方差线性插值：

\[
W_H=
\frac{T_b-T_H}{T_b-T_a}W_a
+\frac{T_H-T_a}{T_b-T_a}W_b,
\qquad T_H=H/365,
\]

\[
IV_H=100\sqrt{W_H/T_H}.
\]

核心字段：

```text
iv30_mf
iv60_mf              # 诊断与曲线图
iv90_mf
```

不外推。无法夹逼时标 `UNBRACKETED_TENOR`。上交所 2016 年中国波指方法在“近月剩余天数不小于 30 天”时直接使用近月波动率；MatSHIX 将该规则实现为 `iv30_ivx_compat` 诊断和回归基准，不覆盖严格字段 `iv30_mf`。

### 6.6 Forward variance 与期限结构

\[
q_H=(IV_H/100)^2,
\]

\[
fvar_{30,90}=\frac{T_{90}q_{90}-T_{30}q_{30}}{T_{90}-T_{30}},
\qquad
fvol_{30,90}=100\sqrt{fvar_{30,90}}.
\]

同时输出：

\[
term\_log\_ratio_{30,90}=\ln(IV30/IV90).
\]

若 forward variance 为负，不取绝对值、不截零；`fvol30_90=null` 并标 `NEGATIVE_FORWARD_VARIANCE`。这不是“低压力”，而是当前曲面、插值或报价无法支持该派生量。

### 6.7 ATM、25 Delta 与翼部

每个 expiry 先用 forward Black 口径计算单腿 IV：

\[
C=D(T)[FN(d_1)-KN(d_2)],\qquad
P=D(T)[KN(-d_2)-FN(-d_1)],
\]

\[
d_2=d_1-\sigma\sqrt{T}.
\]

\[
d_1=\frac{\ln(F/K)+\tfrac12\sigma^2T}{\sigma\sqrt{T}},
\]

forward delta 固定为：

\[
\Delta_C=N(d_1),\qquad \Delta_P=N(d_1)-1.
\]

v1 使用 **forward delta、非 premium-adjusted**。价格边界为 `D*max(F-K,0)<=C<D*F`、`D*max(K-F,0)<=P<D*K`。每条 OTM 腿以 Brent root 在 `sigma∈[1e-4,5.0]` 反解 Black IV，`xtol=1e-12, rtol=4*machine_epsilon, maxiter=200`；端点不能包围价格、价格违反边界或未收敛时该点无效。

令 `x=ln(K/F)`、`W(x)=T*sigma(x)^2`。相同 x 的重复/调整合约不得一起进入 PCHIP：若合同经济条款完全相同，保留 relative spread 更小者；否则标 `DUPLICATE_STRIKE_CONFLICT` 并令该 expiry smile 不可用。对排序后的唯一有效 x 使用 shape-preserving PCHIP，不外推。

`ATM` 固定为 `x=0` 的 PCHIP 总方差；0 必须被有效 x 包围。25D Put/Call 分别只在 `x<0` 与 `x>0` 的现有范围内求 `Delta_P=-0.25`、`Delta_C=+0.25` 的 root；若出现多个 root，取离 ATM 最近者并记录诊断；无包围 root 返回 null。PCHIP 仍须通过价格单调性、凸性和 calendar-arbitrage 诊断；失败标 `STATIC_ARBITRAGE_VIOLATION` 并令相关 expiry smile 不可用，不能因插值成功就视为合格曲面。

每个 expiry 计算：

```text
atm_iv
iv_25d_put
iv_25d_call
```

再按第 6.5 节的总方差方式插值为固定 30 日：

\[
RR25=IV_{25C}-IV_{25P},
\]

\[
DownSkew25=IV_{25P}-IV_{ATM},
\]

\[
UpSkew25=IV_{25C}-IV_{ATM},
\]

\[
BF25=\frac{IV_{25C}+IV_{25P}}{2}-IV_{ATM}.
\]

10 Delta Put/Call 是扩展项；缺乏有效包围 strike 时返回 `null + DELTA_NOT_BRACKETED`，禁止用 SVI 或线性外推制造尾翼。

原研究中的 `WingContribution = ModelFreeIV - ATM_IV` 改名为：

\[
WingVarianceSpread=(IV30_{MF}/100)^2-(IV30_{ATM}/100)^2.
\]

它是全曲面方差与 ATM 方差的差值代理，不声称是可加、可归因的“尾翼贡献”。

### 6.8 官方中国波指兼容诊断

上交所/中证指数 2016 年编制方案证明：中国波指以方差互换原理、近月与次近月 50ETF 期权、7 个自然日展期构造未来 30 日预期波动率，并规定了成交、单双边报价、昨结算和熔断虚拟价格的价格选择规则。

本次从第 22 节官方入口下载并阅读的编制方案 DOCX，SHA-256 为 `c37b8682a2064c15b490c12374628fa4a83bc888a61561083ca716f260f3045a`；兼容实现以该锁定文档为回归方法版本，不凭本节摘要补写遗漏规则。

MatSHIX 必须单独实现：

```text
sse50_ivx_compat
```

用途仅为：

- 对 510050 曲面公式做回归测试；
- 解释严格双边 mid 与历史官方兼容口径的差异；
- 在能够取得官方 000188 同期序列时做数值对照。

当前尚未验证 000188 是否持续维护、历史是否可授权取得。`sse50_ivx_compat` 不进入 headline score，也不能让陈旧结算价掩盖严格曲面缺失。

---

## 7. 原始特征字典

### 7.1 每个载体的核心特征

| 组 | 字段 | 经济含义 |
|---|---|---|
| 曲面 | `iv30_mf / iv60_mf / iv90_mf / atm_iv30` | 保险价格水平与期限 |
| 期限 | `term_log_ratio_30_90 / fvol_30_90` | 压力是否进入中期 |
| 尾部 | `rr25 / down_skew25 / up_skew25 / bf25 / wing_variance_spread` | 下行、上行及双向凸性 |
| 变化 | `d1/d5_log_iv30 / d5_down_skew25 / d5_up_skew25 / d5_fvol_30_90` | 重定价与扩散速度 |
| vol-of-vol | `iv_vol_of_vol20 / d5_iv_vol_of_vol20` | IV 自身不稳定度 |
| VRP | `vrp_ewma94 / vrp_percentile` | 保险价格相对事前 RV 的补偿 |
| 活动 | `pcr_volume / pcr_oi / pcr_premium` | Put/Call 活动构成，不带方向 |
| 质量 | `surface_status / quote_coverage / spread_quality` | 是否可相信曲面 |

### 7.2 Ex-ante VRP

使用经分红/公司行动处理的 ETF 总回报收盘序列：

\[
r_t=\ln(TRClose_t/TRClose_{t-1}).
\]

EWMA：

\[
\hat\sigma_t^2=0.94\hat\sigma_{t-1}^2+0.06r_t^2,
\]

\[
RVForecast30_t=252\hat\sigma_t^2,
\]

\[
VRP^{EWMA}_t=(IV30_t/100)^2-RVForecast30_t.
\]

以最早连续 252 个有效相邻交易日收益的去均值样本方差初始化，`ddof=1`。缺一个交易日时不得把跨两日收益当单日；缺口日和跨缺口首日 VRP 为 null，随后是否续接或重置由实现采用**重置并重新积累 252 个连续收益**的唯一规则，避免两种状态机。

未来实际 30 日 RV 只能作为 outcome，禁止进入当日信号。

### 7.3 IV 的 vol-of-vol

\[
iv\_vol\_of\_vol20_t=
\sqrt{252}\cdot Std_{20}(\Delta\ln IV30).
\]

要求连续 20 个有效 IV30 变化；缺口后重新积累。它只是自建 IV 不稳定度，不得标为 `VVIX`。

### 7.4 Put/Call 活动

每个载体分别计算：

\[
PCR_{volume}=PutVolume/CallVolume,
\]

\[
PCR_{OI}=PutOI/CallOI,
\]

\[
PCR_{premium}=PutPremiumAmount/CallPremiumAmount.
\]

分母为 0 时返回 null。活动字段进入诊断和 Challenger，不进入 Core v1 headline score。

### 7.5 隔夜风险的修正定义

原研究的 `Var(close_to_open)/Var(close_to_close)` 不是可加方差占比，受隔夜与日内协方差影响且可能大于 1。扩展项改为 20 日平方收益贡献：

\[
OvernightShare_{20}=
\frac{\sum r_{close\to open}^2}
{\sum r_{close\to open}^2+\sum r_{open\to close}^2}.
\]

另行输出：

```text
overnight_variance20
intraday_variance20
overnight_intraday_covariance20
```

三项并列解释，不把 `OvernightShare` 称为严格的总方差分解。

### 7.6 股指期货和 ETF 辅助量

对 IH/IF/IC：

\[
EquityFuturesBasis=Futures/Spot-1.
\]

若取得点时股息与折现曲线，可另算理论调整基差；未取得时不得用猜测的 `q` 产生“公平基差”。

ETF 辅助量：

\[
ETFPremium=ETFMarketPrice/IOPV-1.
\]

融资余额变化字段固定命名：

```text
margin_financing_balance_change
securities_lending_balance_change
```

不得把融资余额变化简称为 `MarginChange`，以免与期权保证金混淆。

---

## 8. 标准化、科创载体与横截面聚合

### 8.1 统一数学约定

全文统一：

```text
ratio = A / B
slope = A / B - 1
log_ratio = ln(A / B)
```

`ratio` 的平坦交叉点为 1；`slope/log_ratio` 为 0。配置、测试和 UI 必须携带单位与变换名，不能把 1.05 阈值用于 `ratio_minus_one`。

变化量：

```text
d1_x = x_t - x_t-1
d5_x = x_t - x_t-5
d1_log_x = ln(x_t / x_t-1)
d5_log_x = ln(x_t / x_t-5)
```

`t-5` 是前五个上交所期权交易 session。非正值不计算对数。

### 8.2 滚动百分位

对任一序列 `x_t`：

```text
reference_sessions = t 之前最近 504 个对应交易 session
minimum_valid = 252
current_t_is_excluded = true
```

mid-rank 百分位：

\[
p_t(x)=\frac{\#\{x_s<x_t\}+0.5\#\{x_s=x_t\}}{N}.
\]

先固定 504 个 session，再过滤无效值；不得为了凑 504 个有效值无限向前扫描。`p(-x)` 表示先反向再按同一窗口计算。合法极端值不 winsorize。

每个载体、经济指数和横截面 spread 使用自己的历史序列。不得用 510050 的绝对 IV 分布直接评价 588000，也不得用当天四指数横截面排名冒充时间序列极端程度。

`surface_methodology_version` 改变后，正式百分位重新 warm-up；不同方法版本不得拼入同一 reference window。旧版本可以保留用于研究桥接，但不能静默延续分位。

### 8.3 先标准化再比较经济指数

原始 IV 差：

```text
IV_STAR50 - IV_CSI300
```

混入了两个指数长期波动率水平和成分结构差异，不能直接代表“科创压力”。核心风格差使用同口径分位或 spread 自身历史：

\[
TechLevelGap=p_{STAR50}(IV30)-p_{CSI300}(IV30),
\]

\[
MidCapShockGap=p_{CSI500}(d5\ln IV30)-p_{CSI300}(d5\ln IV30).
\]

若保留 raw spread，必须对 raw spread 自身做滚动 percentile/z-score，且只用于解释。

### 8.4 科创50正式载体

科创50经济指数在 MatSHIX v1 中只有一个正式观测载体：

```text
STAR50 source carrier = STAR50_588000
S_STAR50,a = S_STAR50_588000,a
```

其中 `a` 为 Level、Shock、DownTail、UpTail、Persistence 等轴。588000 必须像另外三个正式载体一样独立完成曲面、百分位和质量门控；这里没有年度权重、双载体确认或载体间分歧。

`STAR50_588080` 明确位于 v1 universe 之外：

- 不采集、不储存为核心 raw、不生成正式曲面；
- 不作为 588000 的回退、确认或 Challenger；
- 不进入 `Breadth`、`FRAGMENTED`、概率特征、输入哈希或输出 Schema；
- 588000 不合格时，STAR50 为不可观察，顶层不能为 `OK`。

这一约束必须同时写入配置白名单与禁止名单，防止数据供应商返回全市场合约时把 588080 自动纳入。

### 8.5 三个不重复风险段

为避免上证50与沪深300高度重叠造成“双重投票”，横截面宽度使用三个风险段：

```text
large_cap = 0.5 × SSE50 + 0.5 × CSI300
mid_cap   = CSI500
tech      = STAR50
```

聚合连续分数的固定经济权重：

```text
SSE50 = 0.20
CSI300 = 0.20
CSI500 = 0.30
STAR50 = 0.30
```

这等价于大盘段 0.40、中盘 0.30、科创成长 0.30。它是透明 baseline，不是市值权重或统计独立性证明。G3 必须同时报告等权、去除 SSE50、去除 CSI300 和 40/30/30 的敏感性。

### 8.6 Canonical 聚合特征字典

以下字段是状态和概率唯一可引用的聚合量；不得由各模块自行选择“先聚合还是先取分位”：

```text
aggregate_d5_fvol30_90
aggregate_d5_fvol30_90_percentile
aggregate_etf_return_5d
aggregate_vrp_value
aggregate_vrp_percentile
aggregate_iv_vol_of_vol_percentile
cross_section_pressure_dispersion
front_event_premium_max
segment_iv_jump_score[large|mid|tech]
segment_iv_jump[large|mid|tech]
```

固定定义：

\[
aggregate\_d5\_fvol30\_90=\sum_j w_j d5\_fvol30\_90_j,
\]

其 percentile 在该聚合序列自身历史上按第 8.2 节计算。`aggregate_etf_return_5d` 对四个同步 cutoff 总回报对数收益使用相同 `w=(0.20,0.20,0.30,0.30)`。`aggregate_vrp_value` 对四个原始年化 VRP 使用同一权重；`aggregate_vrp_percentile` 和 `aggregate_iv_vol_of_vol_percentile` 则分别加权四个指数**各自历史分位**，不先混合 raw level。

\[
cross\_section\_pressure\_dispersion=
\max_j(IndexPressure_j)-\min_j(IndexPressure_j),
\]

单位为 score point，概率输入再除以 100。

风险段 IV jump 分数先取各经济指数自身的 `p_j(d1_log_iv30)`：

```text
large = 0.5*p_SSE50 + 0.5*p_CSI300
mid   = p_CSI500
tech  = p_STAR50
segment_iv_jump[k] = segment_iv_jump_score[k] >= 0.90
```

`front_event_premium_max` 是四个经济指数同口径、同日可计算的 `front_event_premium` 最大值；任一正式指数缺该可选诊断时该聚合为 null、该可选 phase 分支为 NOT_ELIGIBLE，不删除缺失项后取 max。

以上任一聚合量缺少必需组件即为 null，不重归一；它继承最弱 vintage 和输入方法版本，并写入 `aggregate_feature_version`。

---

## 9. 七个量化分数

本文权重属于 `MATSHIX_SSE_ETF_CORE_V1` 的透明研究基线。它们冻结了可重复实现，不证明经济最优；只有通过历史覆盖、消融、阈值扰动和样本外事件区分度后，才可作为正式发布版本。

### 9.1 每个经济指数的分数

以下 `p_j()` 均按第 8.2 节在经济指数 `j` 自身历史上计算。

#### InsuranceLevel

\[
InsuranceLevel_j=100\,p_j(IV30_{MF}).
\]

它回答保险价格相对自身历史高不高，不回答是否值得卖出。

#### Shock

\[
Shock_j=100[
0.35p_j(d1\_log\_iv30)
+0.25p_j(d5\_log\_iv30)
+0.20p_j(iv\_vol\_of\_vol20)
+0.20p_j(-etf\_return\_1d)].
\]

ETF 收益只提供价格冲击方向，严格读取第 5.1 节的同步 cutoff 总回报标记；15:00 收盘不反向进入该轴。

#### DownTail

\[
DownTail_j=100[
0.65p_j(DownSkew25)
+0.35p_j(d5\_DownSkew25)].
\]

#### UpTail

\[
UpTail_j=100[
0.65p_j(UpSkew25)
+0.35p_j(d5\_UpSkew25)].
\]

DownTail 与 UpTail 分开，避免把认购侧凸性错误标成下行恐慌。`BF25` 与 `WingVarianceSpread` 是双向/全曲面凸性诊断，不进入任一方向分数，防止另一侧尾翼机械抬高错误方向。

#### Persistence

\[
Persistence_j=100[
0.40p_j(fvol_{30,90})
+0.25p_j(IV90)
+0.20p_j(d5\_fvol_{30,90})
+0.15p_j(term\_log\_ratio_{30,90})].
\]

它回答中期方差是否抬升和继续扩散，不用“近月 IV 高”单独代替持续性。

#### Repair

\[
Repair_j=100[
0.30p_j(-d5\_log\_iv30)
+0.25p_j(-d5\_DownSkew25)
+0.20p_j(-d5\_fvol_{30,90})
+0.15p_j(etf\_return\_5d)
+0.10p_j(-d5\_iv\_vol\_of\_vol20)].
\]

Repair 是独立方向轴，不从当前压力机械扣除。市场可以风险仍高、同时正在修复。

### 9.2 经济指数压力

\[
IndexPressure_j=
0.20InsuranceLevel_j
+0.30Shock_j
+0.25DownTail_j
+0.25Persistence_j.
\]

三个风险段：

\[
P_{large}=0.5P_{SSE50}+0.5P_{CSI300},
\]

\[
P_{mid}=P_{CSI500},\qquad P_{tech}=P_{STAR50}.
\]

对每个轴使用相同聚合得到 `SegmentShock / SegmentDownTail / SegmentPersistence`；例如大盘段均为 SSE50 与 CSI300 的 0.5/0.5 加权，中盘和科创段分别直接取 CSI500、STAR50。

经济指数压力谓词：

```text
index_stressed_j =
    IndexPressure_j >= 65
AND (Shock_j >= 65 OR DownTail_j >= 70 OR Persistence_j >= 65)
```

段压力谓词：

```text
segment_stressed_k =
    SegmentPressure_k >= 65
AND (
      SegmentShock_k >= 65
   OR SegmentDownTail_k >= 70
   OR SegmentPersistence_k >= 65
)
```

### 9.3 Breadth

\[
BreadthScore=\frac{100}{3}[
I(large\_stressed)+I(mid\_stressed)+I(tech\_stressed)].
\]

另行输出经济权重覆盖诊断：

\[
WeightedBreadthScore=100[
0.40I(large\_stressed)+0.30I(mid\_stressed)+0.30I(tech\_stressed)].
\]

同时输出未经重叠调整的名义宽度：

\[
NominalIndexBreadth=
\frac{I(index\_stressed_{SSE50})+I(index\_stressed_{CSI300})+I(index\_stressed_{CSI500})+I(index\_stressed_{STAR50})}{4}.
\]

`BreadthScore` 是三个不重复风险段的等票广度，取值为 `0 / 33.33 / 66.67 / 100`；`WeightedBreadthScore` 与 `NominalIndexBreadth` 是诊断。三者并列，不能把 4/4 描述为四个独立风险因子，也不能让“哪两个段承压”的权重差异改变 `BROAD` 的语义。

### 9.4 市场聚合分数

对 Level、Shock、DownTail、UpTail、Persistence、Repair，统一采用：

\[
Axis=0.20Axis_{SSE50}+0.20Axis_{CSI300}
+0.30Axis_{CSI500}+0.30Axis_{STAR50}.
\]

总压力：

\[
PressureScore=
0.20InsuranceLevel
+0.25Shock
+0.20DownTail
+0.15Persistence
+0.20BreadthScore.
\]

UpTail 不进入下行压力总分；它通过 `tail_answer` 和 `UPSIDE_CONVEXITY_PRICED` phase 单独表达。

压力带：

| `PressureScore` | `pressure_level` |
|---:|---|
| `[0,35)` | `LOW` |
| `[35,55)` | `WATCH` |
| `[55,70)` | `ELEVATED` |
| `[70,85)` | `HIGH` |
| `[85,100]` | `EXTREME` |

方向：

```text
d5_pressure_score >= +7.5 -> RISING
d5_pressure_score <= -7.5 -> FALLING
otherwise                 -> STABLE
```

### 9.5 VRP 只描述补偿

VRP 不进入 PressureScore，以避免“保险价格很贵”被自动写成“卖保险很安全”。每个经济指数和聚合层另行输出：

```text
vrp_value
vrp_percentile
insurance_compensation = THIN / NORMAL / RICH / UNKNOWN
```

```text
THIN   -> vrp_percentile < 0.35
RICH   -> vrp_percentile >= 0.75
NORMAL -> otherwise
```

高 VRP 可与高 DownTail、急性 Shock 同时存在；叙事应写“补偿高但危险也高”，不能只展示一个方向。

### 9.6 固定权重缺失规则

任一轴的必需组件缺失，该轴为 null；不得删除组件后重归一。任一四经济指数核心轴缺失，顶层完整 PressureScore 不发布。科创50的正式必需载体就是 588000，不存在用 588080 回填的例外。

---

## 10. 当前答案、原子谓词与唯一 phase

### 10.1 Level

| 答案 | 条件 |
|---|---|
| `CHEAP` | InsuranceLevel < 35 |
| `NORMAL` | 35 <= InsuranceLevel < 60 |
| `RICH` | 60 <= InsuranceLevel < 85 |
| `EXTREME` | InsuranceLevel >= 85 |
| `UNKNOWN` | 必需输入不可算 |

### 10.2 Shock

先定义三个风险段的 IV jump：

```text
segment_iv_jump_k = 第8.6节 canonical segment_iv_jump[k]
cross_market_iv_jump = at_least(2, 三个 segment_iv_jump)
all_segment_iv_jump = at_least(3, 三个 segment_iv_jump)

hard_acute =
    Shock >= 85
AND cross_market_iv_jump = TRUE
AND (DownTail >= 75 OR broad_confirmed = TRUE)
```

| 答案 | 条件 |
|---|---|
| `CALM` | Shock < 40 |
| `BUILDING` | 40 <= Shock < 65 |
| `HIGH` | Shock >= 65 且 `hard_acute=FALSE` |
| `ACUTE` | `hard_acute=TRUE` |
| `UNKNOWN` | 必需输入或三段确认不可判 |

Shock >=85 但结构确认不足时仍为 HIGH，并说明“速度极端，但跨市场确认不足”。

### 10.3 Tail

按以下顺序匹配：

| 答案 | 条件 |
|---|---|
| `NEUTRAL` | DownTail < 60 且 UpTail < 60 |
| `TWO_SIDED_EVENT` | DownTail >= 75 且 UpTail >= 75 且两者差绝对值 < 15 |
| `DOWNSIDE_PRICED` | DownTail >= 60 且 DownTail - UpTail >= 15 |
| `UPSIDE_PRICED` | UpTail >= 60 且 UpTail - DownTail >= 15 |
| `MIXED` | 以上均不满足 |
| `UNKNOWN` | 任一必需分数不可算 |

尾部答案描述风险中性定价，不是物理涨跌概率。

### 10.4 Term

统一原子谓词：

```text
persistent_day_t = Persistence_t >= 75 AND PressureScore_t >= 65
persistent_now_t = 最近5个交易session中 persistent_day 至少3日为TRUE
```

窗口包含当日，使用三值逻辑：已知 TRUE 数为 `T`、UNKNOWN 数为 `U`；`T>=3` 为 TRUE，`T+U<3` 为 FALSE，否则 UNKNOWN。缺失不能当 FALSE。

| 答案 | 条件；按表中优先级匹配 |
|---|---|
| `PERSISTENT` | `persistent_now=TRUE` |
| `DIFFUSING` | Persistence >=55，`aggregate_d5_fvol30_90>0` 且 `aggregate_d5_fvol30_90_percentile>=0.70` |
| `FRONT_LOCALIZED` | Shock >=65 且 Persistence <50 |
| `NORMAL` | Persistence <55 且 Shock <65 |
| `MIXED` | 以上均不满足 |
| `UNKNOWN` | 必需输入或谓词不可判 |

### 10.5 Breadth

按三个风险段判断：

```text
stressed_segment_count = 三段全部已知时的 TRUE 数，否则为null
stressed_index_count = 四个index_stressed全部已知时的 TRUE 数，否则为null
broad_confirmed = at_least(2, large_stressed, mid_stressed, tech_stressed)
systemic_confirmed = at_least(3, large_stressed, mid_stressed, tech_stressed)
large_only = large=TRUE, mid=FALSE, tech=FALSE
local_style_only = large=FALSE 且 exactly_one(mid_stressed, tech_stressed)=TRUE
systemic = systemic_confirmed
```

`fragmented_now` 在以下任一条件成立：

- `cross_section_pressure_dispersion>=50`，且 `broad_confirmed=FALSE`；
- 任一经济指数 `abs(Shock_j-DownTail_j)>=50`，且 `broad_confirmed=FALSE`。
- `stressed_segment_count=0` 且 `stressed_index_count>=2`，表示多个指数各自承压但尚未形成一致风险段。

| 答案 | 条件；结构性宽度优先于分歧标签 |
|---|---|
| `NONE` | stressed_index_count=0、stressed_segment_count=0 且 `fragmented_now=FALSE` |
| `ISOLATED` | stressed_index_count=1，且 stressed_segment_count=0 |
| `BLUE_CHIP_LOCALIZED` | large_only=true |
| `LOCAL_STYLE` | local_style_only=true |
| `BROAD` | `broad_confirmed=TRUE` 且 `systemic_confirmed=FALSE` |
| `SYSTEMIC` | systemic=true |
| `FRAGMENTED` | `broad_confirmed=FALSE` 且 `fragmented_now=TRUE` |
| `UNKNOWN` | 三段状态无法判定 |

### 10.6 Repair

```text
stress_day_s = PressureScore_s >= 70 OR hard_acute_s = TRUE
recent_stress_t = 最近10个交易session任一 stress_day 为TRUE

repair_confirmed_t =
    recent_stress_t = TRUE
AND Repair_t >= 70 AND Repair_t-1 >= 70
AND PressureScore_t < PressureScore_t-1
AND BreadthScore_t <= BreadthScore_t-1
AND hard_acute_t = FALSE
```

三值短路规则：如果 Repair<60，即使 `recent_stress` 因历史缺失为 UNKNOWN，仍可确定 `INACTIVE`；只有现有已知值不足以决定时才传播 UNKNOWN。

| 答案 | 条件 |
|---|---|
| `CONFIRMED` | `repair_confirmed=TRUE` |
| `BUILDING` | `recent_stress=TRUE` 且 Repair>=60，但未确认 |
| `INACTIVE` | Repair<60，或已知条件能确定未形成修复 |
| `UNKNOWN` | 必需输入/历史谓词无法决定 |

### 10.7 近端事件溢价诊断

上交所没有稳定可得的 9 日期限族，原始 `IV_near/IV30` 会随到期日机械变化。v1 不把它直接放入核心分数。

对剩余到期超过 7 天的最近 expiry 计算：

\[
FrontRatio=\ln(IV_{front}/IV30).
\]

按 `front_dte_bucket = 8–14 / 15–21 / 22–29 / >=30` 和“窗口内是否含长假”分组，在历史可比日中计算 percentile，至少 60 个可比样本：

```text
front_event_premium = p(FrontRatio | same DTE bucket, same holiday bucket)
```

只有已知事件日历在 `decision_as_of` 前已公布、且事件位于 front expiry 覆盖窗口内时，才能写入具体事件归因；否则只写“近端事件溢价”，不得猜成政策事件。

事件日历未配置/未获许可，或 DTE/holiday bucket 少于 60 个样本时，`NEAR_TERM_EVENT_PREMIUM` 分支为 `NOT_ELIGIBLE` 并按 FALSE 跳过，同时保留诊断；不污染核心 phase。若日历已配置且按合同当日应到文件却缺失/损坏，同样不生成事件 phase，记录 issue 并把 `confidence` 降为 `DEGRADED`，但只要核心链完整，`data_status` 仍可为 OK。

### 10.8 唯一 primary phase

按自上而下优先级匹配：

| 优先级 | `primary_phase` | 精确条件 |
|---:|---|---|
| 1 | `UNKNOWN` | `data_status != OK`，或按下述短路规则遇到会改变分类的核心 UNKNOWN 谓词 |
| 2 | `SYSTEMIC_ACUTE_STRESS` | hard_acute=true；breadth=`SYSTEMIC`；`all_segment_iv_jump=TRUE` |
| 3 | `LOCALIZED_ACUTE_STRESS` | hard_acute=true，且第 2 行 systemic acute 谓词为 FALSE |
| 4 | `REPAIR_IN_PROGRESS` | Repair=`CONFIRMED` 且 hard_acute=false |
| 5 | `BROAD_PERSISTENT_PRESSURE` | persistent_now=true 且 `broad_confirmed=TRUE` |
| 6 | `BROAD_PRESSURE` | `broad_confirmed=TRUE` 且 PressureScore>=65 |
| 7 | `LOCAL_STYLE_PRESSURE` | breadth=`LOCAL_STYLE` 且 PressureScore>=55 |
| 8 | `BLUE_CHIP_PRESSURE` | breadth=`BLUE_CHIP_LOCALIZED` 且 PressureScore>=55 |
| 9 | `NEAR_TERM_EVENT_PREMIUM` | `front_event_premium_max>=0.90`；Persistence<55；至少一项已知事件在窗口内 |
| 10 | `DOWNSIDE_TAIL_RICH` | DownTail>=75；Shock<65；`broad_confirmed=FALSE` |
| 11 | `UPSIDE_CONVEXITY_PRICED` | tail=`UPSIDE_PRICED`；UpTail>=75；`aggregate_etf_return_5d>0` |
| 12 | `FRAGMENTED_TRANSITION` | breadth=`FRAGMENTED` |
| 13 | `CALM_POSITIVE_VRP` | VRP 上下文可用；PressureScore<35；Shock<40；`aggregate_vrp_value>0` |
| 14 | `BALANCED_MARKET` | 以上均不满足 |

“局部压力”“尾部上行”“事件溢价”等正交答案仍全部保留；primary phase 只是摘要，不抹去并存事实。

phase 分支按表中顺序用三值短路求值：遇到 TRUE 立即选中；已确定 FALSE 才继续；若某个**核心**分支仍为 UNKNOWN，且它可能抢占所有后续分支，则返回 `UNKNOWN`，不得跳过。事件日历和 VRP 上下文是可选分支：数据源未启用时，相应分支按合同为 FALSE，而不是把已知急性/广泛状态打成 UNKNOWN。

### 10.9 最小滞回

`ordered_raw_phase(t)` 从第 10.8 节优先级 2 开始逐行求三值谓词：首个 TRUE 胜出；在首个 TRUE 之前遇到 UNKNOWN 则返回 UNKNOWN；FALSE 才继续；可选分支 NOT_ELIGIBLE 按 FALSE；全部为 FALSE 返回 `BALANCED_MARKET`。

唯一发布算法：

```text
raw = ordered_raw_phase(t)

if data_status_t != OK or raw == UNKNOWN:
    publish UNKNOWN
    candidate_phase = null
    candidate_streak = 0

elif previous_published_phase is absent or previous_published_phase == UNKNOWN:
    publish raw                         # 历史bootstrap/数据恢复
    candidate_phase = null
    candidate_streak = 0

elif previous_published_phase in {SYSTEMIC_ACUTE_STRESS, LOCALIZED_ACUTE_STRESS}:
    if raw in {SYSTEMIC_ACUTE_STRESS, LOCALIZED_ACUTE_STRESS}:
        publish raw                     # 两种acute可按当日结构互换
        clear candidate
    elif hard_acute_t == FALSE and Shock_t < 75:
        if raw == previous_candidate_phase:
            candidate_streak = previous_candidate_streak + 1
        else:
            candidate_phase = raw
            candidate_streak = 1
        if candidate_streak >= 2:
            publish raw
            clear candidate
        else:
            publish previous_published_phase
    else:
        publish previous_published_phase
        clear candidate

elif raw in {SYSTEMIC_ACUTE_STRESS, LOCALIZED_ACUTE_STRESS,
             REPAIR_IN_PROGRESS, BROAD_PERSISTENT_PRESSURE}:
    publish raw                         # 自带结构/多日确认，立即进入
    clear candidate

elif raw == previous_published_phase:
    publish previous_published_phase
    clear candidate

else:
    if raw == previous_candidate_phase:
        candidate_streak = previous_candidate_streak + 1
    else:
        candidate_phase = raw
        candidate_streak = 1
    if candidate_streak >= 2:
        publish raw
        clear candidate
    else:
        publish previous_published_phase
```

`clear candidate` 固定写 `candidate_phase=null,candidate_streak=0`。两个确认日必须是连续的 `data_status=OK` session；candidate 改变或出现 UNKNOWN 均重置。acute 释放优先于 Repair/Persistent 的“立即进入”，所以从 acute 转入任何非 acute phase 都须两个相同 raw phase 的合格日。

每个 checkpoint 至少保存已发布 phase、candidate、streak、session、state/config version 与 `previous_checkpoint_hash`。`replay --session D` 必须载入已验证的 D-1 checkpoint，或从最早日顺序重放，不能只凭 D 单行猜前态。`what_changes_the_view` 必须从这套实际转移谓词生成，不能维护第二套近似句库。

---

## 11. 市场叙事生成器

叙事由确定性模板生成。未来可选 LLM 只能润色，不得改变数值、状态、证据身份、驱动、反证、概率或模型状态。

### 11.1 摘要 headline

| phase | headline |
|---|---|
| `UNKNOWN` | 按下方两类 UNKNOWN 原因选择确定模板。 |
| `SYSTEMIC_ACUTE_STRESS` | 大盘、中盘与科创期权同步进入急性保险重定价。 |
| `LOCALIZED_ACUTE_STRESS` | 急性重定价已出现，但尚未获得三段同步急性跳升确认。 |
| `REPAIR_IN_PROGRESS` | 高压后的边际修复得到多项证据确认。 |
| `BROAD_PERSISTENT_PRESSURE` | 压力已跨风险段扩散并进入持续层。 |
| `BROAD_PRESSURE` | 多个风险段的保险价格正在同步承压。 |
| `LOCAL_STYLE_PRESSURE` | 中盘或科创成长保险价格显著承压，大盘尚未完全确认。 |
| `BLUE_CHIP_PRESSURE` | 大盘权重相关保险价格显著承压，中盘与科创尚未完全确认。 |
| `NEAR_TERM_EVENT_PREMIUM` | 已知事件窗口附近的近端保险溢价突出，中期尚未同步扩散。 |
| `DOWNSIDE_TAIL_RICH` | 总体冲击尚不高，但下行尾部相对中心明显偏贵。 |
| `UPSIDE_CONVEXITY_PRICED` | 上行凸性相对突出，当前更像认购侧事件定价。 |
| `CALM_POSITIVE_VRP` | 多数风险段平稳，保险价格相对事前实现方差仍有正补偿。 |
| `FRAGMENTED_TRANSITION` | 经济指数或期限证据分化，市场处于过渡状态。 |
| `BALANCED_MARKET` | 当前没有急性、广泛或显著尾部主导证据，市场处于相对均衡状态。 |

`UNKNOWN` 不是单一数据故障模板，固定按发布原因选择：

```text
data_status != OK
    -> 今日核心曲面或正式数据链不足，暂不形成完整上交所期权市场天气。

data_status == OK AND ordered_raw_phase == UNKNOWN
    -> 今日核心曲面完整，但关键历史基线或状态谓词仍不可判，暂不发布市场天气分类。
```

不得在第二种情况下声称“核心曲面不足”。`LOCALIZED_ACUTE_STRESS` 中的 “localized” 表示没有同时满足 `breadth=SYSTEMIC AND all_segment_iv_jump=TRUE` 的三段同步急跳确认；它不否认 Breadth 答案本身可能已经是 `SYSTEMIC`。

### 11.2 Driver、反证与修复证据

每个经济指数、轴和轴内特征的风险方向贡献固定为：

\[
Contribution_{i,a,f}=
EconomicWeight_i\times NarrativeAxisWeight_a\times WithinAxisWeight_{a,f}
\times(p_{i,f}-0.5).
\]

`EconomicWeight=(SSE50:0.20, CSI300:0.20, CSI500:0.30, STAR50:0.30)`。`WithinAxisWeight` 严格复用第 9.1 节各公式；InsuranceLevel 的轴内权重为 1.00。用于 `drivers/counter_evidence` 的 `NarrativeAxisWeight` 冻结为：

```text
InsuranceLevel = 0.20
Shock          = 0.25
DownTail       = 0.20
Persistence    = 0.15
UpTail         = 0.20
```

前四项沿用 PressureScore 中连续风险轴的权重；UpTail 的 0.20 只是叙事排序权重，不让 UpTail 进入 PressureScore。Breadth、hard acute、tail side 和 known event 是结构事实，只进入 `structural_triggers`，不伪造 feature contribution。

`repair_evidence` 在独立池内排序，固定 `NarrativeAxisWeight_Repair=1.00`，并复用 Repair 的五个轴内权重；其数值不得与风险 drivers 跨池比较。所有 contribution 保存未展示舍入值，JSON 展示最多 6 位小数。

固定规则：

```text
drivers = 风险方向 percentile >=0.75，按 contribution 降序取最多3项
counter_evidence = 风险方向 percentile <=0.35，按 contribution 升序取最多2项
repair_evidence = 修复方向 percentile >=0.75，按 repair contribution 降序取最多3项
structural_triggers = hard_acute、segment stress、tail side、known event 等布尔事实
```

数值相同时再按固定 `evidence_order` 升序；不得依赖 map/dict 遍历顺序。`evidence_order` 按经济指数 `SSE50, CSI300, CSI500, STAR50`，再按轴 `InsuranceLevel, Shock, DownTail, Persistence, UpTail, Repair`，最后按第 9.1 节公式中的特征出现顺序生成。

每项证据恰好包含：

```json
{
  "evidence_id": "star50.shock.iv30_change_1d",
  "identity": "DERIVED",
  "carrier_or_index": "STAR50",
  "raw_value": 0.083,
  "unit": "log_return",
  "percentile": 0.94,
  "contribution": 0.01155,
  "meaning": "科创50的30日隐含波动率单日重定价处于自身历史高分位"
}
```

证据词典必须使用“价格结构与……一致”，不得临时生成机构身份、主动买卖、政策原因或盈利含义。

### 11.3 每日叙事模板

```text
{phase_headline}
保险价格：{level_sentence}
重定价与期限：{shock_sentence} {term_sentence}
尾部与宽度：{tail_sentence} {breadth_sentence}
修复：{repair_sentence}
主要驱动：{drivers_sentence}
反向证据：{counter_evidence_sentence}
未来判断：{outlook_sentence}
判断改变条件：{transition_predicate_sentence}
数据边界：{confidence_and_issues_sentence}
```

数组为空时不编造内容：

- drivers 为空：写“当前没有单项风险贡献超过 75% 历史分位”；
- counter evidence 为空：省略该句；
- 没有校准模型：明确写历史基准或样本不足；
- 588000 核心曲面不可观察：STAR50 相关答案保持 UNKNOWN，并在数据边界中写明缺口；
- 扩展数据不可得：不生成期货、涨跌停或事件归因。

---

## 12. 五个未来状态事件

概率引擎预测明确定义的状态事件，而不是“市场危险”“A股下跌”或某策略赚钱。五个事件独立建模，概率不要求相加为 1。

所有事件先判：

```text
global_model_observable_t(event) =
    data_status_t == OK
AND formal_vintage_eligible_t(event) == true
AND event 的固定 predictors 全部可用
```

其中：

```text
formal_vintage_eligible_t(event) =
    该事件当日 predictors 与 onset 的全部传递原始输入
    均为 OBSERVED_PIT 或有可用性证据的 ASSUMED_PIT

target_window_formal_eligible_t(event) =
    未来标签谓词在完整 horizon 内的全部传递原始输入
    均满足同一正式 vintage 准入
```

这是 event-specific 准入，不因与该事件无关的扩展诊断为 reconstructed 而停算；但 `data_status != OK` 仍是全局保险丝。

再判三值 `event_onset_t`：

```text
不可观察或 onset=UNKNOWN -> UNOBSERVABLE
可观察且 onset=FALSE     -> NOT_APPLICABLE
可观察且 onset=TRUE      -> ELIGIBLE
```

BaseRate、训练、OOF、校准和验收必须使用同一个 event-specific eligible cohort。

### 12.1 `cross_market_iv_jump_1d`

业务问题：下一交易日是否出现新的跨风险段 IV 跳升？

```text
Y=1，当且仅当 t+1：
cross_market_iv_jump = TRUE
AND Shock >= 75
```

Onset：

```text
Shock_t < 75
AND cross_market_iv_jump_t = FALSE
```

当前已经处于高/急性 Shock 时不预测“新的跳升”，返回 NOT_APPLICABLE。

### 12.2 `broad_pressure_onset_5d`

业务问题：未来五日是否由非广泛状态进入多风险段压力？

```text
Y=1，当且仅当 t+1...t+5 任一日：
broad_confirmed = TRUE
AND PressureScore >= 65
```

Onset：

```text
broad_confirmed_t = FALSE
```

### 12.3 `systemic_acute_stress_5d`

业务问题：未来五日是否形成大盘、中盘、科创同步的急性重定价？

```text
Y=1，当且仅当 t+1...t+5 任一日：
primary_phase = SYSTEMIC_ACUTE_STRESS
```

Onset：当前 phase 不是 `SYSTEMIC_ACUTE_STRESS`。

### 12.4 `persistent_cross_market_stress_20d`

业务问题：未来二十日是否形成持续、广泛的中期压力？

```text
Y=1，当且仅当 t+1...t+20 中存在任一连续5交易日窗口，使：
至少3日同时满足
  PressureScore >= 70
  Persistence >= 70
  broad_confirmed = TRUE
```

对这个事件单独定义与目标同构的当前原子：

```text
persistent_cross_market_day_s =
    PressureScore_s >= 70
AND Persistence_s >= 70
AND broad_confirmed_s = TRUE

persistent_cross_market_now_t =
    最近5个交易session中 persistent_cross_market_day 至少3日为TRUE
```

窗口使用第 5.7 节 `at_least(3)` 三值规则。Onset 为当前 `persistent_cross_market_now=FALSE`；UNKNOWN 则事件不可观察。它预测状态形成，不预测 ETF 必然下跌。

### 12.5 `fast_repair_5d`

业务问题：当前高压是否会在未来五日形成可信修复？

```text
Y=1，当且仅当 t+1...t+5 任一日：
repair_confirmed = TRUE
```

Onset：

```text
repair_answer_t in {INACTIVE, BUILDING}
AND (
  PressureScore_t >=65
  OR primary_phase in {
    SYSTEMIC_ACUTE_STRESS,
    LOCALIZED_ACUTE_STRESS,
    BROAD_PERSISTENT_PRESSURE,
    BROAD_PRESSURE,
    LOCAL_STYLE_PRESSURE,
    BLUE_CHIP_PRESSURE
  }
)
```

平静市场返回 NOT_APPLICABLE，不显示“修复概率 0%”。

### 12.6 标签窗口和删失

- 1 日标签必须完整拥有 `t+1`；
- 5 日标签必须完整拥有 `t+1...t+5`；
- 20 日标签必须完整拥有 `t+1...t+20`；
- 窗口内任一事件谓词必需字段不可计算，标签为 `CENSORED`；
- `target_window_formal_eligible_t(event) in {FALSE,UNKNOWN}`，标签为 `CENSORED`；
- 只有完整观察整个窗口且从未触发，标签才为 0；
- `outcome_available_at = max(窗口内全部必需输入的 available_at, horizon 结束后首个允许发布时点)`；事件提前触发也不能提前成熟；
- `NOT_APPLICABLE` 不进入正例或负例；
- 多个事件可以同时为 1。

这样避免把缺失、样本末端或当前已经存在的状态编码成“事件不会发生”。

`systemic_acute_stress_5d` 的 future `primary_phase` 含滞回，target builder 必须从 t 的已验证 checkpoint 顺序重放未来窗口；禁止逐日孤立计算 raw phase 后直接贴标签。

---

## 13. 概率模型、样本外路径与发布门

### 13.1 条件历史基准率

每个事件先建立可解释 climatology。令 `N` 为预测日之前、outcome 已完成的最近最多 504 个 eligible 样本数：

\[
BaseRate_t=\frac{Positive_N+1}{N+2}.
\]

使用 Beta(1,1) 平滑。少于 252 个 eligible 完成样本时不发布 BaseRate；这时不是 0%，而是 `INSUFFICIENT_HISTORY`。

### 13.2 Logistic baseline

每个事件独立使用 L2 Logistic Regression。第一实现必须锁定并保存完整运行环境。库、solver 与正则化设置参考本次已测试的 MatVIX 本地实现；下列样本窗口和正负例门槛是 MatSHIX 新增候选基线，尚未经验验证：

```text
scikit-learn = 1.7.2
penalty = L2
C = 1.0
solver = lbfgs
fit_intercept = true
class_weight = None
tol = 1e-8
max_iter = 1500
random_state = 0
minimum_training_samples = 504
maximum_training_samples = 1260
minimum_positive = 25
minimum_negative = 25
```

NumPy、SciPy、BLAS 平台和全部 lockfile hash 进入 model artifact。更换依赖、solver 或缩放规则必须升级 `probability_version` 并重建全部 OOF。

不使用 class weight，因为目标是概率校准，不是提高少数类召回率。

### 13.3 固定 predictors

所有 predictors 缩放到 `[0,1]`，特征顺序固定。定义：

\[
PressureChange5Scaled=
clip((d5\_pressure\_score+100)/200,0,1).
\]

| 事件 | predictors |
|---|---|
| `cross_market_iv_jump_1d` | InsuranceLevel/100、Shock/100、DownTail/100、BreadthScore/100、`aggregate_iv_vol_of_vol_percentile`、PressureChange5Scaled |
| `broad_pressure_onset_5d` | Shock/100、BreadthScore/100、Persistence/100、DownTail/100、`cross_section_pressure_dispersion/100`、PressureChange5Scaled |
| `systemic_acute_stress_5d` | Shock/100、DownTail/100、BreadthScore/100、三个 `segment_iv_jump` 的 TRUE 比例（全部已知才计算）、Persistence/100、PressureChange5Scaled |
| `persistent_cross_market_stress_20d` | InsuranceLevel/100、Persistence/100、BreadthScore/100、DownTail/100、`aggregate_vrp_percentile`、PressureChange5Scaled |
| `fast_repair_5d` | Repair/100、`1-PressureChange5Scaled`、Shock/100、Persistence/100、BreadthScore/100、DownTail/100 |

第一版不把四盘口数十个原子量全部塞进模型。数据质量、许可状态和缺失标志不是 alpha；不可观察时停算，不让模型学习“缺数据等于风险”。

### 13.4 Rolling-origin walk-forward

对预测日 `t` 和事件 horizon `H`：

- 训练行的 `outcome_available_at <= decision_as_of_t`；
- `t-H` 表示预测日之前第 H 个上交所期权交易 session；线上可用口径允许 `prediction_date<=t-H`，但边界行仍必须满足上一条真实 availability；
- 训练集从最早 eligible 样本扩张，超过 1260 后保留最近 1260；
- 所有验证预测逐日生成并追加到不可变 OOF ledger；
- 未来标签或数据修订不得重写已经发布的 OOF 预测，只能建立新 revision/version。

相邻 5/20 日标签高度重叠。样本行数不是独立样本数；评估必须同时提供按 horizon 作为最小 block length 的区块 bootstrap 不确定性。

G4 另行报告严格 purged 敏感性（`prediction_date<t-H`）。它不替换线上可用口径，但若结论只在 inclusive 边界成立，模型不得通过稳健性验收。

### 13.5 顺序 Platt 校准

对每个预测日：

1. 先用当时训练集产生未校准 Logistic decision score；
2. 仅使用该日之前、outcome 已完成的最近 252 个 eligible OOF score 拟合 Platt；
3. 校准集合至少 20 个正例和 20 个负例；
4. 输入为基础 Logistic 的 `decision_function z`；输出 `sigmoid(a*z+b)`；
5. 从 `a=1,b=0` 初始化，以 L-BFGS-B 最小化 mean log loss + `1e-6(a²+b²)`；边界为 `a∈[0,+∞), b∈(-∞,+∞)`，`maxiter=1000, ftol=1e-12, gtol=1e-8`；
6. `a>=0` 防止校准器在小样本下无解释地反转基础模型排序；未收敛、参数/概率非有限或优化失败时不发布特征条件概率；成功后概率裁剪到 `[1e-6,1-1e-6]`；
7. 当日校准概率追加到 ledger 后，不能反过来参与自身 calibrator。

### 13.6 模型发布验收

只有最近 252 个顺序生成、outcome 已完成的 calibrated OOF 样本，且至少 20 个正例和 20 个负例时才验收。

必须计算：

```text
Brier_model
Brier_rolling_base_rate
BrierSkill = 1 - Brier_model / Brier_base
LogLoss_model - LogLoss_base
ECE_5_equal_count_bins
reliability_table
block_bootstrap_BrierSkill_90CI
```

等频 ECE 按 `(probability, prediction_date)` 稳定升序后，将 252 行依次切为 `51/51/50/50/50` 五箱；并列概率不得用不稳定排序。

90% 区块 bootstrap 固定为 paired moving-block bootstrap：

```text
input = 最近252条按 prediction_date 排序的 calibrated OOF 行
paired item = (y, p_model, p_base)
block_length = 事件 horizon H（1、5 或20条 eligible 行）
candidate block starts = 0..252-H
replicates = 5000
seed = 按第12节事件顺序固定为 1101,1102,1103,1104,1105
每次有放回抽取连续 block，拼接至长度>=252，截取前252条
同一索引同时重采样 model/base，计算 paired BrierSkill
90% CI = 5000个 BrierSkill 的线性分位数 [5%,95%]
```

若任一 replicate 的 `Brier_base=0`，或输入不足/数值非有限，则发布门失败，不改用其他 bootstrap。block 定义与随机数生成器版本写入 `probability_version` 和 model artifact。

`CALIBRATED_MODEL` 的初始发布门：

```text
BrierSkill >= 0.02
LogLoss_model <= LogLoss_base
ECE <= 0.08
90% block-bootstrap BrierSkill lower bound > -0.02
```

这些是首版统计发布门，不是市场真理。若数据表明门槛不适合，只能通过新的 `probability_version` 和完整 OOF 重算修改，不能为让模型上线而临时放宽。

未通过时：

- BaseRate 已有至少 252 个 eligible 完成样本：`BASE_RATE_ONLY`；
- BaseRate 也不足：`INSUFFICIENT_HISTORY`；
- 作业失败：`NOT_RUN` 并记录 issue。

### 13.7 Challenger

只有 baseline 稳定后才研究：

- Elastic Net Logistic；
- monotonic gradient boosting；
- PCR、10D 尾翼、IH/IF/IC、IOPV、涨跌停和隔夜特征；
- carrier-specific 或 phase-conditional 模型。

Challenger 必须在完全相同的 eligible cohort、walk-forward 路径和发布门上改善 Brier、LogLoss 与校准。ROC-AUC、样本内收益或一次事件回放不能单独晋级。

---

## 14. 概率与输出状态真值表

必须分开：

```text
data_status  = OK | PARTIAL | UNKNOWN
event_status = ELIGIBLE | NOT_APPLICABLE | UNOBSERVABLE
model_status = CALIBRATED_MODEL | BASE_RATE_ONLY | INSUFFICIENT_HISTORY | NOT_RUN
label_status = OBSERVED_0 | OBSERVED_1 | CENSORED | NOT_APPLICABLE
```

`probability_kind`：

```text
FEATURE_CONDITIONAL
HISTORICAL_REFERENCE
null
```

每个事件对象固定包含：

```text
event_status
model_status
probability_kind
probability
base_rate
uplift
target_window_end_session
base_rate_sample_size
base_rate_positive_count
training_sample_size
training_positive_count
brier_skill
ece
interpretation
```

合法组合：

| event_status | model_status | kind | probability/base/uplift | target end | cohort counts | Brier/ECE |
|---|---|---|---|---|---|---|
| `ELIGIBLE` | `CALIBRATED_MODEL` | `FEATURE_CONDITIONAL` | 模型值/基准/差值 | horizon 结束日 | 四项均为当日实际整数 | 已验收值 |
| `ELIGIBLE` | `BASE_RATE_ONLY` | `HISTORICAL_REFERENCE` | 基准/基准/0 | horizon 结束日 | 四项均为当日实际整数 | 有完整评估则为值，否则 null |
| `ELIGIBLE` | `INSUFFICIENT_HISTORY` | null | 全 null | horizon 结束日 | 四项均为当前实际整数，可为 0 | 全 null |
| `ELIGIBLE` | `NOT_RUN` | null | 全 null | horizon 结束日 | 全 null | 全 null |
| `NOT_APPLICABLE` | `NOT_RUN` | null | 全 null | null | 全 null | 全 null |
| `UNOBSERVABLE` | `NOT_RUN` | null | 全 null | null | 全 null | 全 null |

`target_window_end_session` 是事件窗口结束日，不叫 `valid_through_session`；次日新快照会取代旧条件概率。

`base_rate_*` 统计第 13.1 节的 event-specific 基准 cohort；`training_*` 统计当日 Logistic 训练 cohort。0 是已知计数，只能出现在 `ELIGIBLE + INSUFFICIENT_HISTORY` 等确实完成计数的组合；不可观察或作业未运行时必须为 null。

表达：

- `uplift = probability - base_rate`；
- `uplift>=0.10`：“明显高于历史基准”；
- `0<uplift<0.10`：“略高于历史基准”；
- `uplift=0`：“当前仅显示同类历史发生率”；
- `uplift<0`：“低于历史基准”；
- `BASE_RATE_ONLY` 必须写明“特征模型未提供已验收的增量判断”。

### 14.1 Outlook 确定规则

```text
data_status != OK -> UNKNOWN
没有 ELIGIBLE，且至少一个 UNOBSERVABLE -> UNKNOWN
五个事件全部 NOT_APPLICABLE -> NOT_APPLICABLE
存在 CALIBRATED_MODEL -> 选 uplift 最大者：
    最大 uplift >=0.10 -> event_id
    否则 -> NO_STRONG_EDGE
不存在 calibrated，但至少一个 ELIGIBLE + BASE_RATE_ONLY -> BASE_RATE_ONLY
其余 -> UNKNOWN
```

并列按第 12 节事件顺序，保证确定性。

---

## 15. 每日 JSON 合同

以下数值仅说明结构，不是市场数据；为避免伪概率，示例中的概率均为空：

```json
{
  "schema_version": "1.0.0",
  "model_id": "MATSHIX_SSE_ETF_CORE_V1",
  "surface_version": "1.0.0",
  "feature_version": "1.0.0",
  "state_version": "1.0.0",
  "probability_version": "1.0.0",
  "source_manifest_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "input_manifest_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "config_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  "previous_checkpoint_hash": null,
  "model_artifact_ids": {
    "cross_market_iv_jump_1d": null,
    "broad_pressure_onset_5d": null,
    "systemic_acute_stress_5d": null,
    "persistent_cross_market_stress_20d": null,
    "fast_repair_5d": null
  },
  "session_date": "2026-08-20",
  "decision_as_of": "2026-08-21T09:00:00+08:00",
  "data_status": "UNKNOWN",
  "confidence": "NONE",
  "market_story": {
    "headline": "今日核心曲面或正式数据链不足，暂不形成完整上交所期权市场天气。",
    "primary_phase": "UNKNOWN",
    "candidate_phase": null,
    "candidate_streak": 0,
    "pressure_level": "UNKNOWN",
    "direction": "UNKNOWN",
    "pressure_score": null,
    "answers": {
      "level": "UNKNOWN",
      "shock": "UNKNOWN",
      "tail": "UNKNOWN",
      "term": "UNKNOWN",
      "breadth": "UNKNOWN",
      "repair": "UNKNOWN",
      "outlook": "UNKNOWN"
    },
    "scores": {
      "insurance_level": null,
      "shock": null,
      "down_tail": null,
      "up_tail": null,
      "persistence": null,
      "breadth": null,
      "repair": null
    },
    "drivers": [],
    "counter_evidence": [],
    "repair_evidence": [],
    "structural_triggers": [],
    "what_changes_the_view": [],
    "narrative": "string"
  },
  "economic_indices": {
    "SSE50": {
      "source_carrier": "SSE50_510050",
      "data_status": "UNKNOWN",
      "state": {
        "insurance_level": null,
        "shock": null,
        "down_tail": null,
        "up_tail": null,
        "persistence": null,
        "repair": null,
        "index_pressure": null
      },
      "issues": []
    },
    "CSI300": {
      "source_carrier": "CSI300_510300",
      "data_status": "UNKNOWN",
      "state": {
        "insurance_level": null,
        "shock": null,
        "down_tail": null,
        "up_tail": null,
        "persistence": null,
        "repair": null,
        "index_pressure": null
      },
      "issues": []
    },
    "CSI500": {
      "source_carrier": "CSI500_510500",
      "data_status": "UNKNOWN",
      "state": {
        "insurance_level": null,
        "shock": null,
        "down_tail": null,
        "up_tail": null,
        "persistence": null,
        "repair": null,
        "index_pressure": null
      },
      "issues": []
    },
    "STAR50": {
      "source_carrier": "STAR50_588000",
      "data_status": "UNKNOWN",
      "state": {
        "insurance_level": null,
        "shock": null,
        "down_tail": null,
        "up_tail": null,
        "persistence": null,
        "repair": null,
        "index_pressure": null
      },
      "issues": []
    }
  },
  "carriers": {
    "SSE50_510050": {
      "economic_index_id": "SSE50",
      "surface_status": "UNKNOWN",
      "quote_coverage": null,
      "relative_spread_median": null,
      "iv30_mf": null,
      "iv60_mf": null,
      "iv90_mf": null,
      "issues": []
    },
    "CSI300_510300": {
      "economic_index_id": "CSI300",
      "surface_status": "UNKNOWN",
      "quote_coverage": null,
      "relative_spread_median": null,
      "iv30_mf": null,
      "iv60_mf": null,
      "iv90_mf": null,
      "issues": []
    },
    "CSI500_510500": {
      "economic_index_id": "CSI500",
      "surface_status": "UNKNOWN",
      "quote_coverage": null,
      "relative_spread_median": null,
      "iv30_mf": null,
      "iv60_mf": null,
      "iv90_mf": null,
      "issues": []
    },
    "STAR50_588000": {
      "economic_index_id": "STAR50",
      "surface_status": "UNKNOWN",
      "quote_coverage": null,
      "relative_spread_median": null,
      "iv30_mf": null,
      "iv60_mf": null,
      "iv90_mf": null,
      "issues": []
    }
  },
  "probability_judgment": {
    "cross_market_iv_jump_1d": {
      "event_status": "UNOBSERVABLE",
      "model_status": "NOT_RUN",
      "probability_kind": null,
      "probability": null,
      "base_rate": null,
      "uplift": null,
      "target_window_end_session": null,
      "base_rate_sample_size": null,
      "base_rate_positive_count": null,
      "training_sample_size": null,
      "training_positive_count": null,
      "brier_skill": null,
      "ece": null,
      "interpretation": "当前输入不足，无法观察该问题"
    },
    "broad_pressure_onset_5d": {
      "event_status": "UNOBSERVABLE",
      "model_status": "NOT_RUN",
      "probability_kind": null,
      "probability": null,
      "base_rate": null,
      "uplift": null,
      "target_window_end_session": null,
      "base_rate_sample_size": null,
      "base_rate_positive_count": null,
      "training_sample_size": null,
      "training_positive_count": null,
      "brier_skill": null,
      "ece": null,
      "interpretation": "当前输入不足，无法观察该问题"
    },
    "systemic_acute_stress_5d": {
      "event_status": "UNOBSERVABLE",
      "model_status": "NOT_RUN",
      "probability_kind": null,
      "probability": null,
      "base_rate": null,
      "uplift": null,
      "target_window_end_session": null,
      "base_rate_sample_size": null,
      "base_rate_positive_count": null,
      "training_sample_size": null,
      "training_positive_count": null,
      "brier_skill": null,
      "ece": null,
      "interpretation": "当前输入不足，无法观察该问题"
    },
    "persistent_cross_market_stress_20d": {
      "event_status": "UNOBSERVABLE",
      "model_status": "NOT_RUN",
      "probability_kind": null,
      "probability": null,
      "base_rate": null,
      "uplift": null,
      "target_window_end_session": null,
      "base_rate_sample_size": null,
      "base_rate_positive_count": null,
      "training_sample_size": null,
      "training_positive_count": null,
      "brier_skill": null,
      "ece": null,
      "interpretation": "当前输入不足，无法观察该问题"
    },
    "fast_repair_5d": {
      "event_status": "UNOBSERVABLE",
      "model_status": "NOT_RUN",
      "probability_kind": null,
      "probability": null,
      "base_rate": null,
      "uplift": null,
      "target_window_end_session": null,
      "base_rate_sample_size": null,
      "base_rate_positive_count": null,
      "training_sample_size": null,
      "training_positive_count": null,
      "brier_skill": null,
      "ece": null,
      "interpretation": "当前输入不足，无法观察该问题"
    }
  },
  "observations": {},
  "diagnostics": {},
  "issues": [
    {
      "code": "NOT_LICENSED",
      "severity": "ERROR",
      "scope": "GLOBAL",
      "carrier_id": null,
      "economic_index_id": null,
      "field": null,
      "detail": "示例：核心数据授权尚未验证"
    }
  ]
}
```

上例使用格式合法的具体日期、RFC 3339 时间与 64 位十六进制 hash，是 A0 的 UNKNOWN golden candidate；本报告已验证其 JSON 语法，但只有 A0 落盘正式 Schema 并通过 validator 后才能标记为 accepted golden fixture。正式 JSON Schema 对顶层、四个 `economic_indices`、四个 `carriers`、五个事件和 issue item 均设置 `required` 与 `additionalProperties=false`；588080 既不在 required，也不得由 additional property 混入。

`economic_indices[*].state` 固定为示例中的七个 nullable score；其 `data_status` 使用第 5.6 节同一枚举。`carriers[*]` 固定包含示例中的经济指数映射、surface status、覆盖、价差和三期限 IV；`surface_status=VALID|DEGRADED|INVALID|UNKNOWN`。`issues[]` item 固定包含 `code/severity/scope/carrier_id/economic_index_id/field/detail`；`severity=INFO|WARN|ERROR`，`scope=GLOBAL|CARRIER|INDEX|FEATURE|EVENT`。`observations` 与 `diagnostics` 是按各自 version 管理的扩展对象，不属于第 15.1 节稳定接口。

`input_manifest_hash` 对按固定顺序 canonicalized 的核心原始记录计算 SHA-256，内容至少包含：

```text
series_id, carrier_id, contract_id, session_date, event_time,
economic_index_id, value, unit, source, source_field,
observed_at, available_at, revision_id, methodology_version,
vintage_kind, licence_scope
```

记录先按 `(series_id, carrier_id, contract_id, event_time, source_field, revision_id)` UTF-8 字节序稳定排序，每条按 RFC 8785 JSON Canonicalization Scheme 编码，记录间以单个 LF 连接且末尾无额外 LF，再计算 SHA-256。时间戳必须先规范为带时区 RFC 3339，非有限浮点值禁止进入 manifest。

`source_manifest_hash` 对四载体白名单、588080 禁止项、字段映射、许可范围和 availability 规则内容寻址；`config_hash` 对 surface/feature/state/probability 配置的 canonical bundle 内容寻址；所有 version ID 对应不可变 artifact。状态有前态时必须写 `previous_checkpoint_hash`；已运行概率 artifact 时相应 `model_artifact_ids[event]` 不得为 null。

### 15.1 下游稳定接口

下游只允许读取：

```text
session_date
decision_as_of
data_status
confidence
market_story.primary_phase
market_story.pressure_level
market_story.direction
market_story.pressure_score
market_story.answers
market_story.scores
economic_indices[*].state
probability_judgment[event].event_status
probability_judgment[event].model_status
probability_judgment[event].probability_kind
probability_judgment[event].probability
probability_judgment[event].base_rate
probability_judgment[event].uplift
probability_judgment[event].target_window_end_session
```

`narrative` 是人类解释，不是交易接口。读取 feature-conditioned probability 时，必须同时检查：

```text
event_status = ELIGIBLE
model_status = CALIBRATED_MODEL
probability_kind = FEATURE_CONDITIONAL
```

### 15.2 Parquet 合同

Parquet 不保存一个难以审计的嵌套 JSON blob，而是按主键正规化：

| 表 | 主键 | 角色 |
|---|---|---|
| `daily_market_state` | `session_date, state_version, revision_id` | 顶层 status、confidence、phase、scores、answers 与各 hash |
| `economic_index_state` | `session_date, economic_index_id, feature_version, revision_id` | 四指数 state 与 source carrier |
| `carrier_surface` | `session_date, carrier_id, expiry, surface_version, revision_id` | 四载体期限曲面、覆盖和质量 |
| `event_probability` | `session_date, event_id, probability_version, revision_id` | 五事件完整真值字段 |
| `market_evidence` | `session_date, evidence_kind, evidence_rank, state_version` | driver、反证、repair 与 trigger |
| `issue_ledger` | `session_date, issue_id` | 结构化问题与解决状态 |

所有表必须带 `decision_as_of/available_at/vintage_kind`（适用处）、内容寻址 version/hash 和 UTC-aware timestamp；null/UNKNOWN 规则与 JSON 完全一致。每日 JSON 是这些同 revision 表的确定性投影，API/Parquet/JSON/UI 对账不得跨 revision 拼接。

---

## 16. Dashboard 必须回答什么

首页按交易员阅读顺序展示：

1. **一句话天气**：primary phase、压力强度、方向、数据置信度；
2. **四指数地图**：上证50、沪深300、中证500、科创50各自 Level/Shock/Tail/Term；
3. **三段宽度**：大盘、中盘、科创哪些已确认，名义 4/4 与重叠调整宽度并列；
4. **尾部方向**：DownTail 与 UpTail 分开，不用一个颜色隐藏上行凸性；
5. **期限图**：各载体 IV30/60/90、30–90 forward vol 与 exact DTE；
6. **科创50载体**：只展示 588000 曲面、质量状态与 STAR50 经济状态；588080 不出现；
7. **为什么**：三条主要驱动、两条反证、修复证据和结构触发；
8. **未来状态**：五事件 probability/base rate/uplift、事件定义与模型状态；
9. **什么会改变判断**：来自真实状态机的进入/退出条件；
10. **诊断抽屉**：报价覆盖、价差、失效 strike、合约调整、PCR 和扩展数据。

UI 规则：

- Score 与 Probability 视觉分区；
- `BASE_RATE_ONLY` 与 `CALIBRATED_MODEL` 使用不同标签；
- `NOT_APPLICABLE` 显示“不适用”，不能显示 0%；
- 588000 核心曲面缺失时，STAR50 显示 `UNKNOWN`，且顶层不得为 `OK`；
- `UNKNOWN` 保留局部可见事实，但不生成伪 headline；
- 所有图表可选择历史日期回放当时可见版本；
- 不显示仓位、买卖箭头或策略收益，除非未来另有明确产品授权与规格。

---

## 17. MatVIX 复用裁决与最小工程架构

### 17.1 可以复用的设计

- point-in-time observation/revision ledger；
- `OBSERVED_PIT / ASSUMED_PIT / PROVIDER_RECONSTRUCTED` vintage 传播；
- 交易日窗口、mid-rank rolling percentile；
- 三值逻辑、phase hysteresis 和顺序 replay；
- event status/model status/label status 分离；
- rolling BaseRate、Logistic OOF、Platt、Brier/ECE 框架；
- deterministic narrative、manifest hash、JSON/Parquet/storage 模式；
- Dashboard 中 score/probability 的视觉分离。

### 17.2 必须重写的部分

- Cboe/CFE/SPX/VIX 数据适配器；
- VX F1–F6、M1/M2、VXCM30、Basis30；
- VIX9D/VIX3M/VIX6M、VVIX、SKEW；
- MatVIX 五轴权重、状态阈值、phase 和四个事件；
- 美国交易日与 `09:20 ET` 时点；
- VIX 专属 Dashboard 图和数据 manifest。

### 17.3 代码复用方式

MatSHIX 不把 `/Users/logan/MatVIX` 作为运行时依赖，也不从未提交工作树直接 import。实现时按以下顺序：

1. 先验证 MatVIX 通用模块测试与许可；
2. 若通用逻辑稳定，复制后重命名并保留来源说明，或提取独立内部库；
3. 上海市场专属模块从新的合同和测试实现；
4. 不保留一条“临时 VIX 路径”作为 fallback。

### 17.4 建议目录

```text
MatSHIX/
├── MATSHIX_PRE_DEVELOPMENT_REPORT.md
├── README.md
├── pyproject.toml
├── requirements.lock
├── configs/
│   ├── source_manifest_v1.yaml
│   ├── surface_v1.yaml
│   ├── features_v1.yaml
│   ├── state_v1.yaml
│   └── probability_v1.yaml
├── schemas/
│   └── daily_output.schema.json
├── src/matshix/
│   ├── calendar.py
│   ├── data/
│   │   ├── contracts.py
│   │   ├── sse_quotes.py
│   │   ├── etf.py
│   │   ├── rates.py
│   │   ├── corporate_actions.py
│   │   └── point_in_time.py
│   ├── surface/
│   │   ├── quote_filter.py
│   │   ├── forward.py
│   │   ├── model_free_variance.py
│   │   ├── constant_tenor.py
│   │   ├── delta_smile.py
│   │   └── ivx_compat.py
│   ├── features/
│   │   ├── vrp.py
│   │   ├── vol_of_vol.py
│   │   ├── activity.py
│   │   └── cross_section.py
│   ├── state/
│   │   ├── scores.py
│   │   ├── ontology.py
│   │   └── transitions.py
│   ├── probability/
│   │   ├── targets.py
│   │   ├── baseline.py
│   │   ├── walk_forward.py
│   │   └── calibration.py
│   ├── narrative/
│   │   ├── evidence.py
│   │   └── templates.py
│   ├── output.py
│   ├── pipeline.py
│   ├── dashboard.py
│   └── cli.py
└── tests/
    ├── unit/
    ├── integration/
    ├── golden/
    ├── no_lookahead/
    └── data_contract/
```

CLI 合同：

```text
matshix doctor --project-dir .
matshix import-data --session YYYY-MM-DD
matshix build-surfaces --session YYYY-MM-DD
matshix build-history --start YYYY-MM-DD --end YYYY-MM-DD
matshix build-snapshot --session YYYY-MM-DD
matshix train-probabilities --as-of YYYY-MM-DD
matshix replay --session YYYY-MM-DD
matshix export-dashboard --session YYYY-MM-DD
```

核心验收对象是可重建曲面、状态、证据和概率 ledger，不是前端框架。

---

## 18. 实施顺序与开工闸门

### G0：数据、字段与授权

必须取得并验证：

1. 四个正式盘口至少 20 个近期完整交易日的官方/授权快照样例；
2. 每种合约的基础信息、到期、单位、调整标志和公司行动样例；
3. 一个除息调整日和一个到期日的全链；
4. 四只正式 ETF 同步行情、IOPV、日线和总回报构造资料；
5. 折现曲线来源、字段、发布时间与历史覆盖；
6. 历史数据可得起点、缺口、修订和时间戳语义；
7. 非展示计算、历史存储、Dashboard 展示和派生指标发布的许可边界。

输出：`DATA_ACCESS_REPORT.md` 与机器可读 `source_manifest_v1.yaml`。

`source_manifest_v1.yaml` 必须显式列出四个 `allowed_carriers`，并在 `excluded_carriers` 固定写入 `STAR50_588080`；仅依赖“没有配置它”不足以防止全市场返回时误纳入。

**当前状态：未通过。** 官方网页证明产品存在，但本地没有观察到授权数据文件、合同或可读样例。

### 阶段 A0：合同、合成公式与工程骨架

G0 未通过也可做：

- 包结构、配置 Schema、枚举和三值逻辑；
- 合成 option chain fixtures；
- parity、模型自由方差、总方差插值、Delta、VRP 单测；
- JSON Schema 与 null/UNKNOWN truth table；
- MatVIX 通用模块的隔离验证。

完成条件：公式 golden test 和静态检查通过，但不得称真实市场引擎完成。

### G1：合约主数据与曲面数学

交付：

- 四载体合约日历与调整链；
- 严格双边 mid 曲面；
- IV30/60/90、ATM、25D、forward variance；
- 510050 `sse50_ivx_compat`；
- 每日 surface quality ledger。

验收：

- 任意历史日可从 raw 重建；
- no-arbitrage 和 strike 选择测试通过；
- 到期/除权前后无合同串接错误；
- 与官方方法的差异可解释；
- 未夹逼期限和负 forward variance 保持 UNKNOWN。

### G2：真实覆盖率

按 `carrier × expiry × year` 报告：

```text
valid two-sided quote share
IV30 bracket share
IV90 bracket share
25D put/call bracket share
10D extension share
median/95% relative spread
corporate action gap count
STAR50_588000 missing days
```

在看见分布前不放宽门槛。若核心 25D 或 IV90 覆盖不足以支持稳定日频发布，应修改核心范围或方法版本，而不是回填/外推。

### G3：状态与叙事

交付七分数、六答案、phase、滞回、driver/反证、历史 timeline 和 deterministic narrative。

必须做：

- 权重与阈值 ±5/±10 分扰动；
- 40/30/30、等权、去 SSE50、去 CSI300 的宽度敏感性；
- 每个指标/轴消融；
- 典型历史窗口回放，但不冒充 OOF；
- 交易员盲评叙事能否解释“何处、何种尾部、是否扩散、是否修复”。

### G4：标签与概率

先构建五个 target ledger 和 rolling BaseRate。只有满足第 13 节样本与校准门，才能发布 `CALIBRATED_MODEL`；否则 Dashboard 保留状态引擎，并明确显示 `BASE_RATE_ONLY` 或 `INSUFFICIENT_HISTORY`。

### G5：日频影子运行

至少连续 60 个上交所期权交易 session：

- 自动形成次日 09:00 快照；
- raw/surface/feature/state/JSON 数值一致；
- 无人工回填 past state；
- 数据问题产生 UNKNOWN/PARTIAL，而不是平静分数；
- 任意日可重放并得到同一版本结果；
- 概率 ledger 不被未来数据修改。

### G6：本地交付

- 一键重建说明；
- 本地 Dashboard；
- 数据覆盖与许可说明；
- 典型历史回放；
- API/Parquet/JSON/UI 对账；
- 完整测试、lint、type-check 与构建记录。

本报告没有授权上线公共服务或对外分发授权数据。

---

## 19. 必须测试的业务事实

### 19.1 合约与时点

- 14:56:59 之后的报价不能进入核心曲面；
- 盘后 OI/结算只有在 `available_at<=decision_as_of` 时可用；
- 到期合约、调整合约与标准合约不能串接；
- 期权 T+0 交易、欧式到期行权、次一交易日交收的语义不得被笼统写成“整个市场 T+1”；
- 未来修订不改变过去已发布 snapshot。

### 19.2 曲面

- `bid>ask`、过期、缺 call-put pair 必须拒绝；
- parity 距离并列时按两腿相对价差算术平均、再按较低 strike 的顺序确定唯一 `K_star`；
- `K0`、端点 `ΔK` 和中间 `ΔK` 与手算一致；
- 两个连续零 bid 的翼部停止规则正确；
- 孤立零 bid 被跳过但不提前触发停止，合约主数据结构洞则阻止跨洞拼接；
- 总方差插值而非 IV 简单平均；
- 不能夹逼 30/90 日时不外推；
- 负 forward variance 不静默修补；
- 25D forward delta 方向正确；
- Black IV root、ATM x=0、重复 strike 处理和 PCHIP 多 root tie-break 与手算一致；
- 目标 Delta 未被 strike 包围时为 null；
- IVX compatible 与 strict 字段不相互覆盖。

### 19.3 横截面

- STAR50 只由 `STAR50_588000` 形成；
- `STAR50_588080` 不得进入 source manifest、核心 raw、曲面、聚合、确认、备援、概率或输出；
- 588000 不合格时 STAR50 为 UNKNOWN，且不得以 588080 回填；
- 上证50和沪深300在 Breadth 中只形成一个大盘段；
- large+mid、large+tech、mid+tech 三种两段组合都必须得到 `broad_confirmed=TRUE` 和 `BROAD`；
- 多个 index_stressed、但没有完整 segment_stressed 的组合必须得到 `FRAGMENTED`，不得落入无答案；
- 名义 4/4 与三段宽度同时显示；
- 原始跨指数 IV 差不进入核心压力。

### 19.4 状态与叙事

- 高 UpTail、低 DownTail 可生成上涨凸性 phase，而非下行恐慌；
- 高 DownTail、低 Shock 可生成 quiet tail-rich；
- 局部科创压力不自动成为系统性压力；
- 普通且无分化日落入 `BALANCED_MARKET`，不得生成 FRAGMENTED 假叙事；
- 可选事件日历未启用不把已知 acute/broad phase 变成 UNKNOWN；
- Breadth=SYSTEMIC 但未获三段同步急跳确认时，LOCALIZED_ACUTE headline 不得声称宽度尚未扩散；
- `data_status=OK` 但 raw phase 因历史谓词不可判时，UNKNOWN headline 不得声称核心曲面不足；
- 两类 UNKNOWN headline 必须分别与第 11.1 节冻结模板逐字一致；
- 三值 UNKNOWN 不得通过 `!=TRUE` 落入 HIGH、INACTIVE 或 ELIGIBLE；
- 持续压力与 Repair 可以同时观察，但 phase 按优先级唯一；
- UNKNOWN 清空候选，恢复后从真实前态或顺序重放；
- drivers/counter evidence tie-break 确定；
- driver contribution 按经济指数、叙事轴、轴内特征三层权重手算一致；反证按最负贡献优先，Repair 只在独立池内比较；
- narrative 不新增订单流、机构身份、政策原因、概率或交易动作；
- `what_changes_the_view` 与实际 transition predicate 一致。

### 19.5 概率

- NOT_APPLICABLE 不进入负例；
- PROVIDER_RECONSTRUCTED 不进入正式链；
- 1/5/20 日末端窗口不完整必须 CENSORED；
- 正例也只能在完整 horizon 结束后成熟；
- 训练集不能看到预测日未完成 outcome；
- BaseRate 只用当时已完成 eligible 样本；
- Platt 不能读取当前预测，且 `a>=0`；
- 20 日 persistent event 的 current onset 与 future target 使用同一 `persistent_cross_market_day` 原子；
- paired moving-block bootstrap 的 seed、block、裁剪和 CI 与 golden value 一致；
- ECE 稳定排序、Brier/uplift 算术正确；
- 模型不达门自动退回 BASE_RATE_ONLY；
- JSON 只出现第 14 节允许的组合；
- ELIGIBLE 即使历史不足也保留可计算的 `target_window_end_session`，UNOBSERVABLE cohort count 必须为 null；
- UNKNOWN golden JSON 自身通过 Schema，且 588080 additional property 被拒绝；
- 改变 `available_at/licence_scope` 必须改变 revision/input manifest hash；
- 修改未来 raw 或 label 不能改变过去 OOF prediction。

### 19.6 数据故障

- 四个局部 `data_status` 的 OK/PARTIAL/UNKNOWN 与顶层状态真值表一致，局部 PARTIAL 不得抬升顶层状态；
- 一个 strike 缺失不被填 0；
- 一侧没有 25D 不被解释为“尾部中性”；
- 588000 缺失不被 588080 或其他 ETF 静默回填；
- rate curve 缺失不使用最近一期静默前填；
- corporate action gap 不产生伪 Shock；
- 扩展数据缺失不改变核心 score 权重。

---

## 20. Definition of Done

MatSHIX v1 完成必须同时满足：

1. G0 数据、字段、时间和许可边界有书面与机器可读证据；
2. 四载体曲面可从授权 raw 历史重建并每日更新；
3. IV30/90、25D、VRP、科创单一正式载体映射和三段宽度通过 golden 与真实覆盖测试；
4. 七分数、六答案、唯一 phase、滞回和叙事按本文实现；
5. 每个叙事事实可回指具体载体、字段、时间、值和方法版本；
6. 五事件 target、eligibility、BaseRate 和模型状态可逐日重算；
7. 未通过概率门时诚实发布 BASE_RATE_ONLY/INSUFFICIENT_HISTORY，而不是假概率；
8. 任意历史日可顺序回放，API/Parquet/JSON/UI 一致；
9. 公式、公司行动、期限、横截面、状态、叙事、概率与 no-lookahead 测试通过；
10. Dashboard 让交易员看清“哪里、何种尾部、是否扩散、是否修复、未来哪个状态更值得关注”；
11. 不可得或未授权数据保持 UNKNOWN/NOT_LICENSED；
12. 完整依赖锁、测试记录、数据覆盖报告和运行说明可由新工程师复现。

以下不构成完成：

- 只有一个漂亮仪表盘；
- 把四个 ETF 的原始 IV 直接平均成单一 SHIX；
- 用 ETF 日 K 或最后成交替代同步双边曲面；
- 用 IH/IF/IC 冒充 VIX futures；
- 把 0–100 score 称为概率；
- 用示例 0.00 填未训练概率；
- 把成交/OI 写成确认的买方行为；
- 把回看 2015/2018/2020/2022 等事件称为样本外；
- 通过放宽 quote/Delta/期限门槛制造连续状态；
- 复制 MatVIX 阈值或 Sober 指标名而没有上海市场定义。

---

## 21. 必须保留为待验证的研究问题

以下不是阻止写代码的借口，但在证据形成前必须保持 `NOT_YET_VERIFIED`：

1. 四盘口历史快照、合约调整和精确 `available_at` 的实际覆盖；
2. 14:56:59 截面在压力日与普通日的双边报价覆盖；
3. 30/90 日严格夹逼的缺口比例；
4. 各载体 25D/10D 两翼可得性和价差；
5. 2016 中国波指 000188 当前维护与历史授权状态；
6. 折现曲线的最终提供方与发布时间；
7. 40/30/30 风险段权重、所有 score 权重和阈值的稳健性；
8. 上证50/沪深300重叠调整是否优于其他聚合；
9. PCR、股指期货、IOPV、融资、涨跌停、隔夜和事件日历的增量价值；
10. “保险需求增强”“扩散”“修复”等解释能否得到事件和交易员盲评支持；
11. VRP 的 EWMA 是否优于 rolling RV、HAR-RV 等基准；
12. 五个事件是否有足够正负例；
13. 重叠标签下 Logistic 是否相对 rolling BaseRate 提供稳定增益；
14. 对外展示派生指数/状态是否需要额外指数编制或数据再发布许可。

任何一项的新证据都应进入独立研究记录；只有改变公式、字段或行为时才升级本文版本。

---

## 22. 官方方法与事实起点

以下网页于 2026-08-20 核验。它们属于会变化的外部事实入口，实施时须按 G0 再核验并保存当时版本/下载哈希。

### 上交所品种和合约

- 2026 年 7 月五个 ETF 期权品种公告：<br>
  <https://www.sse.com.cn/assortment/options/disclo/update/c/c_20260715_10825550.shtml>
- 上证50ETF 期权上市通知：<br>
  <https://www.sse.com.cn/assortment/options/rule/c/c_20150911_3985420.shtml>
- 沪深300ETF 期权上市通知：<br>
  <https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250611_10781547.shtml>
- 中证500ETF 期权上市通知：<br>
  <https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250611_10781542.shtml>
- 科创50 ETF 期权上市通知（公告同时包含 588080，但 MatSHIX v1 只采用 588000）：<br>
  <https://star.sse.com.cn/assortment/options/rule/c/c_20230602_5722097.shtml>
- 中证500ETF 期权基本条款（欧式、实物交割、交易/行权/交收时点）：<br>
  <https://www.sse.com.cn/assortment/options/contract/c/c_20230303_5717361.shtml>

### 行情、历史与许可

- 上证信息股票期权行情：<br>
  <https://www.sseinfo.com/services/assortment/options/>
- 上证信息行情历史数据：<br>
  <https://www.sseinfo.com/services/assortment/historical/>
- 上交所历史数据产品说明书 2.0.0：<br>
  <https://www.sseinfo.com/services/assortment/market/hqywwd/wdcpsms/c/10782125/files/f2ba70dea74a4323bf13b76fffce0e40.pdf>
- 上证信息产品与非展示许可价格页：<br>
  <https://www.sseinfo.com/services/cpfwjg/>

### 波动率与辅助市场

- 上证50ETF 波动率指数发布说明与编制方案入口：<br>
  <https://www.sse.com.cn/market/sseindex/diclosure/c/c_20161104_4198915.shtml>
- 中金所沪深300股指期货：<br>
  <https://www.cffex.com.cn/hs300/>
- 中金所中证500股指期货：<br>
  <https://www.cffex.com.cn/cn/zz500.html>
- 中金所上证50股指期货：<br>
  <https://www.cffex.com.cn/cn/sz50gzqh.html>

### 工程标准

- RFC 8785 JSON Canonicalization Scheme：<br>
  <https://www.rfc-editor.org/rfc/rfc8785>

官方来源证明产品、规则和数据产品事实；它们不证明本文指标权重、状态阈值或预测性能。

---

## 23. 给工程团队的最终裁决

MatSHIX 的实现主线冻结为：

```text
授权原始报价与合约主数据
  -> 四个正式ETF独立严格曲面
  -> 四个经济指数保险状态
  -> 三个不重复风险段与横截面宽度
  -> 七个透明分数和六个当前答案
  -> 唯一当前市场叙事
  -> 五个明确的1/5/20日状态事件
  -> rolling BaseRate与经验证的校准概率
  -> Dashboard与历史回放
```

MatSHIX 的核心价值不在于复制一只海外波动率指数，也不在于增加更多指标。它必须用上海 ETF 期权自己的价格语言，稳定回答：

- 保险价格在哪个经济指数先变；
- 当前重定价偏下行、上行还是双向事件；
- 压力是否从局部风格扩散到大盘、中盘和科创；
- 高压是短暂前端现象，还是进入 30–90 日持续层；
- 当前仍在恶化，还是出现了可信修复；
- 下一个明确状态事件相对同类历史基准是否真的更可能发生。

必要的数据质量、PIT 和概率门只服务于这条业务链，不能反过来把项目写成庞大治理系统；但没有数据、公式、事件和样本外证据时，也绝不能用一个漂亮仪表或 0.00 概率掩盖未知。
