# MatSHIX V2.2 510500 settlement audit 裁决

- 裁决：`METHOD_MISMATCH`
- 原因：`SETTLEMENT_PARITY_REJECTED_WHILE_SAME_CHAIN_MINUTE_PARITY_RECOVERS`
- 审计范围：`CSI500_510500 / 2025-01-02..2025-12-31`
- Authority：`MATSHIX_V2_2_AUTHORITY.md`
- Authority SHA-256：`2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8`
- 冻结审计协议 SHA-256：`ccc1e1da777426d8abb9e9c1acba93638df4d09e1db054005b49e9efd5c2ea1c`
- 首次执行提交：`7b0fb129ff84ab83289d31ae2be487442c195ec0`
- 分支：`codex/matshix-weather-v2-2-local`

本裁决来自协议冻结后的第一次真实执行。Settlement 与 14:56 comparator 使用相同的
strike window、minimum pairs、Theil-Sen parity 方法和 admissibility bounds。没有扫描或
扩大容错，没有读取策略收益，也没有改变 `CSI300_LOCAL` 裁决。

## 1. 冻结分类证据

```text
paired session-expiry chains                       972
settlement PARITY_DISCOUNT_INVALID                 547
same-chain 14:56 recovered                         546 / 99.82%
standard-only rescue                                 0 / 0.00%
contract-unit-mismatched-only chains                 0 / 0.00%
recovered settlement raw discount median          1.0432983870967742
recovered 14:56 raw discount median                0.9946729593497964
admissible discount range                         [0.94, 1.02]
```

`DATA_FIELD_DEFECT` 的两条冻结路径均未满足。`METHOD_MISMATCH` 的 invalid-chain 数、
同链恢复率、两侧 discount median 和 standard-only 上限全部满足。因此不能把失败归因于
非标准合约、contract unit 或同族配对，也不能据此优化配对容错。

## 2. 全量状态与 DTE 分层

| Proxy | OK | Discount invalid | Pair missing |
|---|---:|---:|---:|
| provider-reconstructed settlement | 413 | 547 | 12 |
| 14:56 minute close | 970 | 2 | 0 |

| DTE | Chains | Settlement invalid | 14:56 recovered | Settlement median | 14:56 median |
|---|---:|---:|---:|---:|---:|
| `<=20` | 174 | 4 | 4 | 1.005978 | 0.998908 |
| `21..40` | 152 | 52 | 52 | 1.017288 | 0.997900 |
| `41..70` | 184 | 123 | 123 | 1.028221 | 0.996950 |
| `>70` | 462 | 368 | 367 | 1.050800 | 0.992110 |

Settlement 的失配随 DTE 增强，而相同 expiry chain 的 14:56 comparator 基本保持在冻结
区间内。这是价格构造/当前 parity admissibility 不匹配的证据，不是 settlement 原始字段
错误的证明。

## 3. 工程与产物

```text
deterministic replay              true
pricing tolerances changed        false
strategy inputs used              false
CSI300 adjudication changed       false
option contract master SHA-256    91ab679fa57bfbeb70c3b0bf07d9974a73f729264cf1b2f7f9948ba1c53d6bef

outputs/v2_2_audit/settlement_parity_audit.json
  55c39647a9f9fb43d654d9b363db17eb77fa21f1ecffca274056d38e2bb79747

outputs/v2_2_audit/settlement_parity_audit.md
  be7ffc69320a2546a85cc745197cd1b0499eac6b7cbc1e73cdfb888a206b209d
```

## 4. 施工裁决

不建立 `V2.1.2` 配对容错补丁，不修改 `src/matshix/surface/research.py`，不扩大
`[0.94,1.02]`。510500 的 provider-reconstructed settlement 继续不得作为当前正式 Q
价格源。

若以后建设 `CSI500_LOCAL`，必须另立 Authority：历史研发可候选使用 14:56
`RESEARCH_ONLY`，正式接受仍需冻结后追加的 PIT last/bid/ask 收据。该后续版本不得倒签
本次历史审计，也不得改变 V2.2 的 `CSI300_LOCAL = INSUFFICIENT_EVIDENCE`。
