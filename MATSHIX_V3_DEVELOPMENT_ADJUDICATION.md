# MatSHIX V3 回顾性开发裁决

- 顶层状态：`V3_RESEARCH_CORE_ACCEPTED`
- Authority：`MATSHIX_V3_AUTHORITY.md` / `6e7c8234306b715d0514a247c8880ff761aa2a7b71684b3e3e427c9ca401ba95`
- 实现提交：`d68710a1186708a6cdd646028e0ee80994b5f4c5`
- 分支：`codex/matshix-weather-v3`
- 冻结 era：`2020-01-02` -> `2026-06-05`
- 证据层：`RETROSPECTIVE_DEVELOPMENT / RESEARCH_ONLY`
- 3.0.1 修正构建开始：`2026-08-24T18:08:55.615850+00:00`
- 3.0.1 修正构建结束：`2026-08-24T18:12:14.917147+00:00`
- 命令：`python -m matshix build-v3-research --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- 开始时工作树干净：`true`
- deterministic replay：`true`
- strategy inputs used：`false`
- formal PIT claimed：`false`

## 独立接受矩阵

| Dimension | Verdict | Reason |
|---|---|---|
| `ENGINEERING` | `PASS` | `ENGINEERING_GATES_PASSED` |
| `OUTCOME_INTEGRITY` | `PASS` | `OUTCOME_INTEGRITY_PASSED` |
| `P_CORE_H20` | `PASS` | `P_CORE_H20_GATES_PASSED` |
| `Q_RESEARCH_INTEGRITY` | `PASS` | `Q_RESEARCH_INTEGRITY_PASSED` |
| `P_HAR_Q_CHALLENGER` | `FAIL` | `CHALLENGER_GATE_FAILED` |
| `QP_CONSTRUCTION_INTEGRITY` | `PASS` | `QP_CONSTRUCTION_INTEGRITY_PASSED` |
| `QP_DIRECTION_RESEARCH` | `NOT_APPLICABLE` | `SHARED_Q_OUTCOME_NOT_IDENTIFYING` |
| `FORWARD_Q` | `NOT_APPLICABLE` | `HISTORICAL_BUILD_ONLY` |
| `FORWARD_P` | `NOT_APPLICABLE` | `HISTORICAL_BUILD_ONLY` |

## 核心停止裁决

所有回顾性核心门通过；本结果仍不是正式前向通过或交易授权。候选冻结须另按合同生成。

## 产物与 hash

- `data/processed/v3/csi300_outcome_ledger.parquet`
  `c1e2473bc1835d88680b350be2dba674d6245141f250f8162c10f7dc1481f049`
- `data/processed/v3/csi300_p_ledger.parquet`
  `08bba11923e317519f0cd84a77864d8b60ed86bcbce3edbb237e5e581f24faf4`
- `data/processed/v3/csi300_q_ledger.parquet`
  `d365af0db0acd3333d4268aa1a1180a023a5dfbc698353d243f73454334cd3e8`
- `data/processed/v3/csi300_qp_ledger.parquet`
  `54713ebdba49c17902db4dbb7270fdda604699858316dc1d49c7b8a7004d9bf9`
- `outputs/v3/development_score.json`
  `fe08ed1cb3ddf91bdd089dbd00cd6ebb1dadee8338f973bafa63c93cd02015d0`
- `MATSHIX_V3_FAILURE_LEDGER.json`
  `26bfaf8f464e96acc2c4f4f6eb905470086a5ff8308e0573e0c5cb46590548d2`

## 边界

Q 历史输入仅为 AETF 14:56 minute close，不是 bid/ask 或可成交 mid。Q−P 只按 absolute
total variance 构造；共享 Q 的方向相关检验不再执行。该事实不是卖方许可、错误定价
或具体结构的预期收益。
