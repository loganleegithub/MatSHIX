# MATSHIX V2.2 CONSTRUCTION PLAN

**状态：`HUMAN_FROZEN / EXECUTION_AUTHORIZED`**

**人类冻结：`2026-08-23 / 照此施工`**

**建议版本：`2.2.0`**

**建议分支：`codex/matshix-weather-v2-2-local`**

**父基线：`V2.1.1 @ 58c0ae91afb878b26af7671b45bc260b104e9b20`**

本文件经人类冻结后才成为施工合同。

## 1. 最终方案

采用“**研发解耦，验收不追认**”：

- 主线：单独建设 `CSI300_LOCAL`，立即在现有历史数据上完成 H4–H6 研发。
- 支线：独立审计 510500 的 2025 结算价，不得阻断 `CSI300_LOCAL`。
- 历史 14:56 分钟价可用于 `RESEARCH_ONLY` Q；正式接受仍使用冻结后追加的前瞻报价。
- 510300 历史结果只能是开发结果，不能倒签为正式 OOF 或生产放行。
- 上证 50 本版不施工。它尚未通过同一冻结 Q 门，待 510300 本地链稳定后另立 Authority。

当前全局四品种站继续保持 `V2_STATION_NOT_READY`。

## 2. 最小范围

### 2.1 做什么

1. 冻结 `MATSHIX_V2_2_AUTHORITY.md`。
2. 复用现有 H1–H3 产物，建设 510300 本地 H4 天气、H5 P、H6 Q−P。
3. 输出历史开发评分与失败台账。
4. 建立最小前瞻报价记录和正式接受入口。
5. 独立输出 510500 结算价审计结论。

### 2.2 不做什么

- 不建立通用多品种框架、注册表或插件层。
- 不建设全市场 breadth/phase；本地链中二者为 `NOT_APPLICABLE`。
- 不读取策略收益、仓位、选腿或退出结果调整天气站。
- 不用近邻到期填 exact H20 缺口，也不扫描容错参数找绿灯。
- 不把历史分钟价称为可交易报价或正式 PIT quote。

## 3. 冻结语义

以下内容必须逐项写入 `MATSHIX_V2_2_AUTHORITY.md` 后才能施工。

### 3.1 Era 与证据

- `DEVELOPMENT_ERA`：现有 2023–2026 数据；允许开发和评分，不允许正式晋升。
- `FORWARD_ERA`：Authority 冻结后新增的 append-only 数据。
- 历史 Q 价格源：`MINUTE_CLOSE_1456 / RESEARCH_ONLY`。
- 前瞻 Q 对照：14:56 as-of last，并保存同刻 bid/ask midpoint 和原始收据 hash。
- 不满足正式定义的观测不得标记为 `FORMAL_PIT_QUOTES`。
- 95% exact-bracket availability 是前瞻接受门，不再阻断历史研发；历史缺口仍保留 `UNKNOWN`，由 P 的固定样本门判断是否证据充足。

### 3.2 Primary targets

- H20：未来已实现方差。
- H10 downside：未来路径下行风险。
- H10 upside：未来路径上行风险。
- outcome、切分和 embargo 规则沿用 V2，且只能使用预测时点之后的数据解析标签。

### 3.3 Q

- 复用 V2 Q 定义和单位。
- 必须使用 exact H20 expiry bracket。
- bracket、wing 或价格证据不足时保留 `UNKNOWN`。
- 保留 variance、downside、upside、term/wing repair 输出。

### 3.4 H4 本地天气

只计算 510300 自身状态：

- `common_iv_shock`
- `downside_price_shock` / `upside_price_shock`
- `down_tail` / `up_tail`
- `down_persistence` / `up_persistence`
- `variance_repair`
- `downside_repair` / `upside_repair`
- `term_repair`

窗口、因果百分位和缺失语义沿用 V2。`market_breadth`、`primary_phase` 固定为 `NOT_APPLICABLE`。

### 3.5 H5 P

- H20 variance P：复用 V2 的 carrier-local C2 特征和固定模型流程。
- H10 双侧 P：复用 V2 C2，但删除唯一的跨品种特征 `side_tail_breadth`。
- 不做新特征搜索、阈值搜索或模型赛马。
- 训练、校准、OOF、embargo 和缺失处理沿用 V2。

### 3.6 H6 Q−P

- 仅在对应 P 门通过后计算。
- 定义、方向、单位和标准化沿用 V2。
- Q−P 只表达天气站经济溢价，不携带交易许可。

## 4. 施工顺序

### A. 基线封存

1. 验证 main、runtime、AETF 和 V1 确定性基线。
2. 记录 ShortVol 代码、V2.1.1 Authority、adjudication、failure ledger 和失败产物 hash。
3. 保存 `baseline_manifest.json`，确认 H3 FAIL 与 H4–H6 未执行的历史事实。
4. 基线通过后创建建议分支。

基线失败时停止。通过后启动两条互不阻断的施工线。

### B. `CSI300_LOCAL` 主线

#### B1. 冻结 Authority

写入第 3、5 节全部定义，记录 Authority SHA-256 和 `FORWARD_ERA` 起点。

#### B2. 最小实现

- 给现有 Q builder 增加明确的 `carrier_scope=510300`，默认全局行为不变。
- 复用现有 outcome ledger，不重建标签系统。
- 新增一个本地 H4–H6 builder；不拆成通用 carrier 平台。
- 新增一个 CLI 入口：`matshix build-v2-2-local`。
- 输出逐日账本、开发评分、失败原因和输入 manifest。

#### B3. 历史开发评分

固定 `DEVELOPMENT_ERA` 运行一次完整 H4–H6。结论只能是：

- `DEVELOPMENT_PASS`
- `DEVELOPMENT_FAIL`
- `INSUFFICIENT_EVIDENCE`

无论结果如何，状态最高只能到 `V2_2_LOCAL_RESEARCH_BUILT`。

#### B4. 前瞻接受

- 每日追加 14:56 last/bid/ask、source timestamp、receive timestamp 和收据 hash。
- cohort 不因结果重启或删样本。
- 达到样本门后运行一次正式接受。

### C. 510500 结算价审计支线

本支线只读，不修改 Q 语义：

1. 按 expiry/DTE 统计 call-put 回归隐含贴现和拒绝原因。
2. 检查标准/非标准合约、合约单位和同族配对。
3. 比较结算价与 14:56 分钟价的 parity 行为及可用率。

结论只允许：

- `DATA_FIELD_DEFECT`
- `METHOD_MISMATCH`
- `INSUFFICIENT_EVIDENCE`

若确认窄代码/字段缺陷，另立 `2.1.2` 修补合同；若是方法不匹配，则进入后续 Authority。审计不得直接扩大 0.94–1.02 区间或配对容错。

## 5. Acceptance gates

### 5.1 工程门

- 无策略收益、仓位、选腿或退出输入。
- Q、特征和 outcome 通过时间因果检查。
- exact bracket 缺失保持 `UNKNOWN`。
- ledger 只含 510300；breadth/phase 为 `NOT_APPLICABLE`。
- 固定输入可确定性重放。

任一项失败：`V2_2_LOCAL_NOT_READY`。

### 5.2 前瞻 Q 门

不降低 V2 冻结标准：

- paired exact H20 rows `>= 126`
- paired exact H20 coverage `>= 70%`
- median absolute deviation `<= 5%`
- p90 absolute deviation `<= 15%`
- exact-bracket availability `>= 95%`
- wing availability `>= 90%`
- V2 定义的 block-bootstrap 区间位于 `[-5%, +5%]`

历史 `RESEARCH_ONLY` 样本不得补足前瞻门。

### 5.3 P 与 Q−P 门

- 复用 V2 Authority 10.2–10.4 的 OOF、样本、完整性和经济方向门。
- H20 variance、H10 downside、H10 upside 分别判定。
- P 失败时不判定对应 Q−P。

### 5.4 状态

- 历史链建成：`V2_2_LOCAL_RESEARCH_BUILT`
- 前瞻 Q、P、Q−P 全部门通过：`V2_2_LOCAL_FORWARD_ACCEPTED`
- 其他：`V2_2_LOCAL_NOT_READY`
- 全局四品种站：始终保持 `V2_STATION_NOT_READY`，直到另立全局验收合同。

## 6. 最小产物

- `MATSHIX_V2_2_AUTHORITY.md`
- `data/processed/v2_2/csi300_local_ledger.parquet`
- `outputs/v2_2_local/development_score.json`
- `outputs/v2_2_local/failure_ledger.json`
- `data/raw/v2_2_forward/quotes.jsonl`
- `outputs/v2_2_forward/acceptance.json`
- `outputs/v2_2_audit/settlement_parity_audit.json`
- `outputs/v2_2_audit/settlement_parity_audit.md`

只新增两个命令：

```text
matshix build-v2-2-local
matshix audit-v2-2-settlement
```

前瞻接受作为 `build-v2-2-local --forward-accept`，不再增加第三套入口。

## 7. 提交单元

1. `freeze v2.2 authority`
2. `build csi300 local weather station`
3. `record v2.2 development adjudication`
4. `audit csi500 settlement semantics`
5. `record v2.2 forward adjudication`

每个提交都带对应产物 hash。主线不等待 510500 审计结论；任一核心门失败或证据不足时，仅停止受影响的施工线。

## 8. 冻结声明

冻结后不得通过选腿、仓位、退出、概率降门或策略收益给天气站补洞。任何 Q/P/Q−P、primary target 或 acceptance gate 变更，必须先形成新的 Authority 和 hash。
