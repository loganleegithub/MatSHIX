# MatSHIX 数据接入与发布边界

日期：2026-08-21

## 当前可用数据

本机 `/Users/logan/OptiMatrix_DATA/AETF` 可读取 2023-01-03 至 2026-06-05 的 ETF 期权与 ETF 行情。MatSHIX 只选择：

- `510050` / 上证50；
- `510300` / 沪深300；
- `510500` / 中证500；
- `588000` / 科创50。

`588080` 被 source manifest 和采集白名单显式排除。完整构建实际读取 388,164 条 14:56 期权分钟观察，形成 3,208 个 carrier-session 曲面。原始数据保留在 AETF 目录，本项目只保存四载体的规范化研究投影。

## 能证明与不能证明的内容

AETF 期权分钟表提供 OHLCV/OI，合约表提供 option type、strike、expiry 与 contract unit；当前副本没有 bid/ask、五档深度、历史 `available_at`、逐日正式合约修订链或可核验的非展示许可文件。

因此当前证据层固定为：

```text
evidence_tier = RESEARCH_ONLY
vintage_kind = PROVIDER_RECONSTRUCTED
licence_scope = LOCAL_RESEARCH_RIGHTS_UNVERIFIED
formal_publication_allowed = false
```

真实研究数据可以验收曲面覆盖、状态叙事、事件标签和历史基准率；不能被称为正式同步盘口、可成交 mid、PIT 正式概率或 G0–G6 正式验收。

## 正式数据仍缺什么

正式入口要求：

1. 14:56:59 前 5 秒内四载体所有入选腿与 ETF mark 的同步 bid/ask；
2. `event_time`、`available_at`、`vintage_kind` 与不可变 revision；
3. 当日合约条款、调整链与公司行动；
4. 正式人民币折现曲线及其 PIT 可用时间；
5. 历史存储、非展示计算、Dashboard 展示和派生发布的许可凭证。

缺少任一核心项时，[正式快照](outputs/formal/latest.json) 保持 `WITHHELD + UNKNOWN`。

上交所规则确认连续竞价至 14:57，上海证券信息有限公司的期权行情产品包含实时五档买卖盘；历史快照和非展示使用属于另行的数据产品/许可范围：

- [上交所股票期权交易规则](https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250610_10781448.shtml)
- [上证所信息网络有限公司期权行情服务](https://www.sseinfo.com/services/assortment/options/)
- [上证所信息网络有限公司产品服务价格](https://www.sseinfo.com/services/cpfwjg/)

这些公开页面只证明官方字段与服务边界，不证明本机 AETF 数据已获得相应许可。
