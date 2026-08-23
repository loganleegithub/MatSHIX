# MATSHIX V2.1.1 AUTHORITY AMENDMENT

- 状态：`FROZEN_FOR_FIRST_EXECUTION`
- Authority 版本：`2.1.1`
- 父 Authority：`MATSHIX_V2_1_AUTHORITY.md`
- 父 Authority SHA-256：`d41dd08b93548ce6c3ab6f2e5bda503a5e11b0d022814fbbcdffec27bbd13557`
- 根 Authority：`MATSHIX_V2_AUTHORITY.md`
- 根 Authority SHA-256：`18309ed4e71c8e8074ea3abc5645f25e465b612b300ad3b80ed9379776dad152`
- V2.0 裁决 SHA-256：`eb0a0b90db9d3e3213c620568bc472ba2bbe62cb0a36fba78f042ec9e0315ebc`
- 施工合同 SHA-256：`785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f`
- 冻结分支：`codex/matshix-weather-v2-1-settlement`
- 修正时点：首次 V2.1 Confirmation settlement 执行之前

本修正与父 Authority 共同构成唯一施工合同，仅覆盖下列 Q spot 价格坐标与版本。
父 Authority 的 settlement primary、14:56 comparator、Confirmation、Q gate、H4-H6、
证据等级、停止规则和策略隔离边界全部不变。

本修正前未读取 `2025-01-02..2026-06-05` Confirmation settlement 曲面或 gate
结果；修正原因来自定价恒等式和 Development 区间 ETF `adj_factor` 元数据，不是
事后调门。

---

## 1. Q spot 价格坐标修正

父 Authority 第 4.1 节的：

```text
spot = adjusted ETF 15:00 close
```

替换为：

```text
spot = SPLIT_CONSISTENT_UNADJUSTED_ETF_CLOSE_1500
spot_value = ETF/1m_etf 15:00 close
spot_observation_time = t 15:00:00 Asia/Shanghai
```

理由：option strike、option settlement 与 parity forward 必须位于同一当日名义价格
坐标。将 `ETF close × adj_factor` 直接作为 option surface spot 会使 strike/spot
失配，破坏 forward 合理性筛选和 model-free variance 输入。

`adj_factor` 仍必须保存，并只用于：

- H2 复权 ETF realized return、overnight 和 path outcome；
- H4/H5 的 ETF 15:00 close-to-close return 与 EWMA94；
- 公司行动连续性验证。

它不得乘入 Q surface spot。Primary 与 comparator 都遵守同一坐标规则：primary
使用未复权 15:00 ETF close，comparator 使用未复权 14:56 ETF close。该修正不改变
option settlement/minute price，不改变 observation/known time，也不改变任何门槛。

---

## 2. 版本覆盖

下列版本统一升级为 `2.1.1`：

```text
authority_version
outcome_definition_version
q_definition_version
state_definition_version
phase_definition_version
capability_definition_version
target_definition_version
predictor_registry_version
physical_model_version
qp_definition_version
probability_definition_version
acceptance_definition_version
failure_ledger_version
weather_snapshot_schema_version
```

`era_definition_version=2.0.0` 与
`sampling_grid_version=ETF_5M_GRID_XSHG_2.0.0` 不变。产物继续写入父 Authority 冻结的
`data/processed/v2_1/` 与 `outputs/v2_1_*`，不得覆盖 V2.0。

---

## 3. 冻结声明

本文件独立提交后，Q spot 坐标和所有父 Authority 条款共同冻结。首次 Confirmation
运行后不得因结果修改 proxy、坐标、阈值、样本门或 failure 分类。任一核心门
`FAIL` 或 `INSUFFICIENT_EVIDENCE` 仍立即停止后续施工。
