# MatSHIX V3 回顾性开发裁决

- 顶层状态：`V3_RESEARCH_CORE_ACCEPTED`
- Authority：`MATSHIX_V3_AUTHORITY.md` / `01bb4a250da9bf6d738f17e5345ff7b2370c5315ad092b2c2cf3741d4114f454`
- 实现提交：`c2c759e7cfe75adf8568f70733e94b02e22748d2`
- 分支：`codex/matshix-weather-v3`
- 冻结 era：`2020-01-02` -> `2026-06-05`
- 证据层：`RETROSPECTIVE_DEVELOPMENT / RESEARCH_ONLY`
- 首次完整构建开始：`2026-08-23T18:29:08.054278+00:00`
- 首次完整构建结束：`2026-08-23T18:32:14.031273+00:00`
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
| `QP_DIRECTION_RESEARCH` | `FAIL` | `QP_DIRECTION_GATE_FAILED` |
| `FORWARD_Q` | `NOT_APPLICABLE` | `HISTORICAL_BUILD_ONLY` |
| `FORWARD_P` | `NOT_APPLICABLE` | `HISTORICAL_BUILD_ONLY` |

## 核心停止裁决

所有回顾性核心门通过；本结果仍不是正式前向通过或交易授权。候选冻结须另按合同生成。

## 产物与 hash

- `data/processed/v3/csi300_outcome_ledger.parquet`
  `6d8dc4effcb608886926dce9c5ea06fc05b296b5f42e6705a3d5c8ec1f6c0545`
- `data/processed/v3/csi300_p_ledger.parquet`
  `795a01a1c66bb3ecfd19d221f49be29ae8bb6a23d0c8f17195222436c29ea173`
- `data/processed/v3/csi300_q_ledger.parquet`
  `16f194bd616c4144ab8e627ec0c02a56ada9008ef7bb62c5b7bf99f60d2e34a2`
- `data/processed/v3/csi300_qp_ledger.parquet`
  `32c61f22bf9f1b28f6f28e1d8c58c75b33046858c46d43630f4353efa5a75a29`
- `outputs/v3/development_score.json`
  `59b5fd19aa7ad4b6944bd9a62a623725dabbe888f38ea806bb300a66224816ca`
- `MATSHIX_V3_FAILURE_LEDGER.json`
  `18232e29363961ed264fc8c6cb9acf174de587e66d5bcf4675d878d47510815b`

## 边界

Q 历史输入仅为 AETF 14:56 minute close，不是 bid/ask 或可成交 mid。Q−P 即使可构造，
也只是同期限方差补偿事实，不是卖方许可、错误定价或具体结构的预期收益。
