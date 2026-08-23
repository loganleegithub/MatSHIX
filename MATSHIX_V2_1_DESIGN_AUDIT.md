# MatSHIX V2.1 结算曲面设计审计

- 状态：`OUTCOME_BLIND_DESIGN_EVIDENCE`
- 审计日期：`2026-08-23`
- 父 Authority：`MATSHIX_V2_AUTHORITY.md`
- 父 Authority SHA-256：`18309ed4e71c8e8074ea3abc5645f25e465b612b300ad3b80ed9379776dad152`
- V2.0 裁决：`MATSHIX_V2_ADJUDICATION.md`
- V2.0 裁决 SHA-256：`eb0a0b90db9d3e3213c620568bc472ba2bbe62cb0a36fba78f042ec9e0315ebc`
- 设计样本：`2023-01-03` 至 `2024-12-31`
- 隔离 Confirmation：`2025-01-02` 至 `2026-06-05`

本审计只读取 AETF 期权/ETF 分钟价格、日结算、合约条款，以及 H2 ledger
中的日期、载体、上市、horizon 和 target-end 元数据。没有读取 future outcome 数值、
天气标签、ShortVol 逐日收益、选腿、仓位、退出、成本或 NAV。以下结果只用于冻结
V2.1 测量合同，不是 Q acceptance verdict。

---

## 1. 已确认的数据语义缺陷

`OPTION/1m_opt` 为每个合约保存完整分钟行，但 14:56 行不等于该分钟发生交易。
在设计样本中，四载体合约日的 14:56 正成交比例为：

| Carrier | 14:56 正成交 | 当日有成交 | 最近 30 分钟有成交 |
|---|---:|---:|---:|
| SSE50_510050 | 47.14% | 99.43% | 91.58% |
| CSI300_510300 | 43.35% | 99.23% | 89.06% |
| CSI500_510500 | 36.14% | 95.15% | 77.78% |
| STAR50_588000 | 33.27% | 96.85% | 78.54% |

抽查的零成交 14:56 bar 全部满足 `open=high=low=close`，且 close 与前一分钟
完全相同。因此 `MINUTE_CLOSE_1456` 是 provider reconstructed as-of last price，
不是同步 14:56 成交或双边报价。

该事实确认：V2.0 的 `NEAR_CLOSE_PRINT_VWAP_1452_1456` coverage gate 与历史
分钟数据的市场微观结构不匹配；它不能证明 AETF 历史整体失效，也不能把未成交
bar 称为 contemporaneous quote。

---

## 2. 被拒绝的窗口放宽方案

所有诊断都保持 14:56 主 Q 不变，只以正 volume/amount 的成交 VWAP 重建敏感性
曲面：

| Robustness proxy | paired exact H20 coverage | exact availability agreement | median abs delta | p90 abs delta | wing agreement |
|---|---:|---:|---:|---:|---:|
| 14:27–14:56 VWAP | 55.79% | 69.39% | 0.97% | 3.30% | 95.21% |
| 13:57–14:56 VWAP | 66.27% | 76.31% | 1.21% | 3.86% | 94.50% |
| 13:00–14:56 VWAP | 74.60% | 81.32% | 1.69% | 5.18% | 93.92% |
| 全日 VWAP | 81.51% | 85.40% | 3.30% | 8.77% | 92.13% |

尾盘 30 分钟仍无法达到 70% paired coverage。下午或全日窗口虽提高 coverage，
但仍未达到原冻结的 95% availability agreement，并把更早的期权成交价格与
14:56 ETF spot 混入同一曲面。它们因时间错配被拒绝为主 Q 或正式 robustness
proxy，不进入 V2.1 Confirmation。

V2.0 已配对 cohort 的 1.17% 是绝对相对差中位数，不是有符号 bias 检验；正成交
pair 还具有明显的流动性选择。它不能单独证明缺失日期无偏。

---

## 3. 结算曲面设计样本可行性

V2.1 候选以 AETF `OPTION/1d_opt_price.settle` 作为 provider reconstructed
exchange-settlement research price，以 ETF 15:00 close 作为 spot，并继续使用
V1 已测试的 parity、model-free variance、wing 与 total-variance interpolation。

设计样本结果：

```text
settlement positive-price rows                 215,168
settlement carrier sessions                     1,836
settlement exact H20 rows                        1,225
paired exact H20 rows                            1,222
paired / settlement-primary exact coverage      99.76%
paired / 14:56 exact coverage                    96.98%
exact-bracket availability agreement             97.77%
median absolute relative Q variance delta          0.74%
p90 absolute relative Q variance delta             2.46%
wing dominant-side agreement                      90.84%
```

这些值只证明该候选值得预冻结验证。设计样本不得再次用于 V2.1 Q verdict，
也不得据此修改阈值。

---

## 4. 市场规则与证据边界

上海证券交易所现行股票期权规则规定每日收盘后公布结算价格；当收盘集合竞价没有
形成价格或价格明显不合理时，由交易所另行计算。不活跃合约的公开结算规则还依次
使用近收盘成交、收盘最优买卖价、相关合约隐含波动率和合理性修正。

参考：

- https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250610_10781448.shtml
- https://big5.sse.com.cn/site/cht/www.sse.com.cn/assortment/options/rule/c/c_20210128_5312075.shtml

本地 AETF 没有历史发布 receipt、同步 bid/ask 或已核验的数据许可链。因此即使
结算曲面通过 V2.1 门，其证据仍严格为：

```text
evidence_tier = RESEARCH_ONLY
vintage_kind = PROVIDER_RECONSTRUCTED
formal_publication_status = NOT_ELIGIBLE
tradable_price_claim = false
```

未来 `FORMAL_PIT_QUOTES` 采集是独立前向证据，不得回填成历史 tick/quote 事实。

---

## 5. Defect 裁决

```text
Q-ROBUSTNESS-001 = CLOSED_BY_PRESERVED_V2_0_STOP
Q-ROBUSTNESS-002 = CONFIRMED
cause = NARROW_TRANSACTION_WINDOW_MISMATCHES_RECONSTRUCTED_MINUTE_DATA
authorized_challenger = PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT
confirmation_range = 2025-01-02..2026-06-05
future_outcome_used = false
strategy_input_used = false
```

只有独立冻结 V2.1 Authority 后，才允许实现该 challenger 并读取隔离
Confirmation 的结算值。Confirmation 失败或证据不足时必须再次停止。
