# MatSHIX

MatSHIX 是上交所四个 ETF 期权载体的日频市场叙事与状态概率引擎：

- `510050` → 上证 50
- `510300` → 沪深 300
- `510500` → 中证 500
- `588000` → 科创 50

科创 50 只使用 `588000`。`588080` 在采集、曲面、聚合、概率和输出中均被拒绝。

当前实现把业务链分为两个明确证据层：

1. `FORMAL_PIT_QUOTES`：授权的 14:56:59 前五秒双边盘口。只有这一层可以形成正式发布。
2. `RESEARCH_MINUTE_CLOSE`：本机 AETF 14:56 分钟收盘价。它是真实市场数据，但不是 bid/ask，且历史可用性与非展示许可未被证明；仅用于研究级真实数据验收。

研究曲面当前为 `MATSHIX_RESEARCH_MINUTE_CLOSE_V2`：优先使用固定期限总方差与 Delta 夹逼；无法夹逼时，只在冻结的期限/Delta 距离内使用最近真实合约代理，并在每个输出字段公开 method。研究分位与 BaseRate 使用单独、较短的有效样本门槛，不能与正式 252 日合同混称。

两层共享同一套四指数、三风险段、七分数、六答案、唯一 phase、叙事和五事件概率定义。研究层不会伪装成正式盘口层。

## 快速开始

```bash
cd /Users/logan/MatSHIX
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e . --no-deps

.venv/bin/python -m matshix doctor --project-dir .
.venv/bin/python -m matshix build-research-history \
  --aetf-root /Users/logan/OptiMatrix_DATA/AETF \
  --project-dir .
.venv/bin/python -m matshix accept-real-research --project-dir .
.venv/bin/python -m matshix export-dashboard --project-dir .
```

默认从数据本身识别共同交易日，不使用写死到某一年的交易日列表。构建产物写入 `data/processed/` 与 `outputs/`，不会复制或提交原始 AETF 数据。

## 证据边界

`RESEARCH_MINUTE_CLOSE` 使用真实分钟 OHLCV/OI，但缺少五档 bid/ask、逐秒同步证据、每日合约条款修订链和可核验的许可文件。因此：

- 可以验收真实数据覆盖、曲面重建、状态叙事、事件标签和历史基准概率；
- 不可以声称 G0–G6 正式盘口 Definition of Done 已完成；
- 不可以把分钟收盘价称为可成交 mid；
- 不可以把历史基准率称为已验收的特征条件概率。

正式方法与完整产品合同见 [MATSHIX_PRE_DEVELOPMENT_REPORT.md](MATSHIX_PRE_DEVELOPMENT_REPORT.md)。本次工程裁决见 [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)。
当前真实数据字段、许可与正式拒发边界见 [DATA_ACCESS_REPORT.md](DATA_ACCESS_REPORT.md)。
MatSHIX V2 的 Q/P/Q−P、站内验收、候选冻结和固定外部探针施工合同见 [MATSHIX_V2_CONSTRUCTION_PLAN.md](MATSHIX_V2_CONSTRUCTION_PLAN.md)。
