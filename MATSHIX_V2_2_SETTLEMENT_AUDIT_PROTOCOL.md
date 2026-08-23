# MATSHIX V2.2 CSI500 SETTLEMENT AUDIT PROTOCOL

- 状态：`FROZEN_BEFORE_FIRST_AUDIT`
- Authority：`MATSHIX_V2_2_AUTHORITY.md`
- Authority SHA-256：`2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8`
- 审计区间：`2025-01-02..2025-12-31`
- 审计载体：`CSI500_510500`

## 1. 固定方法

Settlement 与 14:56 minute close 使用完全相同的现有 parity 方法：

```text
strike window = [0.65*spot, 1.35*spot]
minimum call-put pairs = 5
Theil-Sen method = joint
admissible discount = [0.94, 1.02]
admissible forward/spot = [0.65, 1.35]
```

每个 `session × expiry` 同时记录：raw inferred discount、forward/spot、pair count、
rejection reason、DTE、standard/non-standard 数量、contract-unit matched/mismatched pair 数。

另用 standard-only 合约原样重放一次，只做原因识别，不替换正式结果。

## 2. Verdict

只允许以下三类：

### `DATA_FIELD_DEFECT`

Settlement 的 `PARITY_DISCOUNT_INVALID` chains 至少 126 个，且满足任一：

- standard-only 可使至少 50% invalid chains 变为 `OK`；或
- 至少 50% invalid chains 仅能形成 call/put contract-unit mismatched pair。

### `METHOD_MISMATCH`

必须全部满足：

- Settlement `PARITY_DISCOUNT_INVALID` chains 至少 126 个；
- 同一 `session × expiry` 的 14:56 comparator 至少恢复其中 70% 为 `OK`；
- 被恢复 chains 的 settlement raw discount median 不在 `[0.94,1.02]`；
- 同链 14:56 raw discount median 位于 `[0.94,1.02]`；
- standard-only rescue share 小于 10%。

### `INSUFFICIENT_EVIDENCE`

以上两类均不满足。

## 3. 禁止事项

- 不扫描或扩大 discount、strike、expiry、pair-count 容错；
- 不选择最好 DTE、月份或合约 family 改写总裁决；
- 不修改 `src/matshix/surface/research.py`；
- 不读取策略收益；
- 审计结论不改变 `CSI300_LOCAL` 裁决。
