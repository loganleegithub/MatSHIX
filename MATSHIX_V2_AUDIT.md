# MatSHIX V2 阶段 A 业务审计与缺陷台账

- 审计合同：`MATSHIX_V2_BUSINESS_AUDIT_1.0.0`
- 阶段结论：`STAGE_A_COMPLETE_SEMANTIC_IMPLEMENTATION_NOT_STARTED`
- 证据边界：未读取 ShortVol 逐日收益、交易台账、选腿、仓位、退出、成本或 NAV。
- 施工边界：本阶段未修改运行语义；任何语义施工须先冻结 `MATSHIX_V2_AUTHORITY.md`。
- 日审计表：`outputs/v2_audit/business_audit_daily.parquet` / `1553b4e8a6f25519360768aa49b98e0d735fdee8b87d25e56bd7a1d31e189403`
- 汇总 JSON：`outputs/v2_audit/business_audit_summary.json` / `dbddb416f1b297bad668b2d61b16620f1e5917521a50782cec960cb4d15b415a`

## 核心事实

- contract master 上市日复核：`PASS`；510050/510300/510500/588000 分别为 2015-02-09、2019-12-23、2022-09-19、2023-06-05。
- V1 common state 从 2023-06-05 才开始；此前 `100` 个 ERA_C surface session 没有机器可读的 partial-era market state。
- V1 VRP 单位恒等式检查 `2005` 行，最大残差 `1.388e-17`；`UNIT-001=REJECTED_LEAD`。
- V1 没有策略无关 realized outcome、同期限 H20 Q/P 或 Q−P 主账本。
- V1 calibrated model 行数为 `0`；最大完整 eligible 标签数为 `167`，低于冻结的顺序可达门 `756`。
- V1 replay 的集成验收可通过，但这不构成 P、Q−P 或条件概率能力 PASS。

## 缺陷裁决

### ERA-001 — CONFIRMED / P0 / DATA

- defect_id: `ERA-001`
- status: `CONFIRMED`
- severity: `P0`
- layer: `DATA`
- observed symptom: V1 starts the common market-state ledger only when all four carriers exist and has no machine-readable listing era or NOT_LISTED carrier rows.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: AETF contract master dates are 2015-02-09, 2019-12-23, 2022-09-19 and 2023-06-05. V1 surface history contains 100 ERA_C sessions, but the state builder silently skips sessions whose economic-index set is not exactly the four-index set.
- financial consequence: Three-carrier history cannot be distinguished from unavailable four-market history, so coverage and breadth claims can be misinterpreted.
- minimal repair: Add an immutable era registry and carry coverage_regime, available_carrier_count, listing_age_sessions and NOT_LISTED through V2 records.
- affected files: `src/matshix/state/scores.py`, `src/matshix/data/aetf.py`
- semantic/version impact: New V2 data and state schema; V1 remains frozen.
- station acceptance criterion: Contract-master launch dates match hand checks; pre-listing rows are NOT_LISTED and no partial era is labelled four-carrier breadth.

### OUTCOME-001 — CONFIRMED / P0 / OUTCOME

- defect_id: `OUTCOME-001`
- status: `CONFIRMED`
- severity: `P0`
- layer: `OUTCOME`
- observed symptom: V1 has no strategy-independent realized variance, path or overnight-gap outcome ledger.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The frozen targets table labels future internal weather states only; no baseline artifact contains realized_variance, max_up_log_move, max_down_log_move or overnight_gap fields.
- financial consequence: Forecast quality cannot be judged against future market risk, so station usefulness and internal-state persistence are conflated.
- minimal repair: Build the frozen H5/H10/H20 ETF outcome ledger before changing weather features.
- affected files: `src/matshix/probability/targets.py`
- semantic/version impact: New V2 outcome schema and definition version.
- station acceptance criterion: Outcome hand checks pass; incomplete windows are CENSORED and use no weather or strategy input.

### HORIZON-001 — CONFIRMED / P0 / QP

- defect_id: `HORIZON-001`
- status: `CONFIRMED`
- severity: `P0`
- layer: `QP`
- observed symptom: V1 Q facts use fixed 30/60/90 calendar-day tenors while event targets use 1/5/20 exchange sessions; no same-target H20 Q/P pair exists.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The frozen surface columns are iv30_mf/iv60_mf/iv90_mf and the target horizons are 1, 5 and 20 sessions. V1 vrp_ewma94 compares only the 30-day IV point to EWMA94.
- financial consequence: A premium sign can be attributed to tenor mismatch rather than compensation.
- minimal repair: Construct exact-bracket H20 total variance using the actual target-end year fraction and compare it with H20 P variance in identical units.
- affected files: `src/matshix/surface/research.py`, `src/matshix/features/history.py`
- semantic/version impact: New V2 Q and Q_MINUS_P definitions; no reinterpretation of V1 columns.
- station acceptance criterion: Every primary Q_MINUS_P row has the same carrier, target window, unit and horizon on both sides.

### UNIT-001 — REJECTED_LEAD / P0 / QP

- defect_id: `UNIT-001`
- status: `REJECTED_LEAD`
- severity: `P0`
- layer: `QP`
- observed symptom: The suspected V1 IV-versus-RV arithmetic unit mix is not reproduced.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: For every non-null frozen row, vrp_ewma94 equals (iv30_mf/100)^2 minus rv_forecast30 to floating-point tolerance; both operands are annualized variance.
- financial consequence: No arithmetic repair is justified; changing the formula would create a false defect.
- minimal repair: Preserve V1 arithmetic as a golden test and add explicit unit/measure fields only in V2.
- affected files: `src/matshix/features/history.py`
- semantic/version impact: No V1 semantic change; V2 adds metadata.
- station acceptance criterion: Golden variance arithmetic remains byte-compatible and every V2 measure declares its unit.

### UPSIDE-001 — CONFIRMED / P1 / PROBABILITY

- defect_id: `UPSIDE-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `PROBABILITY`
- observed symptom: V1 computes up_tail but none of the five frozen event predictor registries consumes it.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The union of PREDICTOR_FIELDS contains down_tail_scaled but not up_tail_scaled.
- financial consequence: Call-wing repricing cannot affect conditional risk estimates even when the state vector observes it.
- minimal repair: Freeze new target-specific, two-sided V2 predictor registries; do not append up_tail to old events.
- affected files: `src/matshix/probability/predictors.py`
- semantic/version impact: New V2 predictor registry and model version.
- station acceptance criterion: Put/Call mirror fixtures swap predictor sides and upside targets receive causal call-side facts.

### UPSIDE-002 — CONFIRMED / P1 / STATE

- defect_id: `UPSIDE-002`
- status: `CONFIRMED`
- severity: `P1`
- layer: `STATE`
- observed symptom: V1 shock, breadth, hard-acute and repair semantics are structurally downside-pressure led.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: Shock includes negative ETF return; hard_acute accepts down_tail or broad pressure but not up_tail; repair is conditioned on recent stress and decreasing downside pressure.
- financial consequence: An upside convexity shock can be reported as calm or merely as a late human phase.
- minimal repair: Publish orthogonal common-IV, downside and upside shock/breadth/persistence/repair facts.
- affected files: `src/matshix/state/scores.py`, `src/matshix/state/ontology.py`
- semantic/version impact: New V2 two-sided state schema and state version.
- station acceptance criterion: Mirrored fixtures exchange down/up facts and an upside shock cannot be suppressed solely by return sign.

### TIMING-001 — CONFIRMED / P1 / STATE

- defect_id: `TIMING-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `STATE`
- observed symptom: UPSIDE_CONVEXITY_PRICED requires the aggregate trailing five-session ETF return already to be positive.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The V1 ontology branch combines tail=UPSIDE_PRICED, up_tail>=75 and aggregate_etf_return_5d>0 as mandatory conditions.
- financial consequence: The station can recognize upside repricing only after part of the move has occurred.
- minimal repair: Treat past return as confirmation/counter-evidence, not as an entry gate for leading upside risk.
- affected files: `src/matshix/state/ontology.py`
- semantic/version impact: New V2 phase definition version.
- station acceptance criterion: An outcome-blind rising call-wing fixture enters upside-building facts before a required past rally.

### PHASE-001 — CONFIRMED / P1 / ACCEPTANCE

- defect_id: `PHASE-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `ACCEPTANCE`
- observed symptom: The downstream ShortVol adapter consumes primary_phase as a machine sizing map and only a subset of downside-oriented local axes as caps.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: shortvol.py renames primary_phase to phase and maps PHASE_UNITS; its local cap reads index_pressure, shock, down_tail and persistence but not up_tail.
- financial consequence: A lossy human summary can silently become trade permission and discard orthogonal risk facts.
- minimal repair: Freeze a versioned vector interface; retain primary_phase only as a human summary.
- affected files: `src/matshix/research/shortvol.py`, `src/matshix/state/ontology.py`
- semantic/version impact: New V2 consumer interface; frozen ShortVol remains unchanged during station work.
- station acceptance criterion: Station acceptance and future consumers use vector fields and no weather snapshot contains trade permission.

### P-001 — CONFIRMED / P1 / P

- defect_id: `P-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `P`
- observed symptom: V1 exposes EWMA94 as rv_forecast30 without an independent physical-forecast harness.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: No frozen artifact reports QLIKE, bias, interval coverage or comparison with climatology, rolling RV and HAR-RV on the same cohort.
- financial consequence: Q_MINUS_P can inherit a weak or biased P estimate and appear to measure compensation.
- minimal repair: Evaluate frozen baselines and a small pre-specified challenger on causal rolling H20 outcomes.
- affected files: `src/matshix/features/history.py`
- semantic/version impact: New V2 P model and validation versions.
- station acceptance criterion: P beats its frozen benchmark gates with block-aware evidence or is published as BASELINE_ONLY/FAIL.

### QP-001 — CONFIRMED / P1 / QP

- defect_id: `QP-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `QP`
- observed symptom: V1 VRP is one 30-day-IV minus EWMA94 point estimate with percentile labels and no uncertainty.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The frozen features table has vrp_ewma94 and vrp_percentile but no forecast interval, same-H20 status, sign confidence or model disagreement.
- financial consequence: A fragile point estimate can be presented as stable compensation.
- minimal repair: Publish same-horizon variance difference, quantiles/interval, sign confidence and abstention status.
- affected files: `src/matshix/features/history.py`
- semantic/version impact: New V2 Q_MINUS_P definition and schema versions.
- station acceptance criterion: Q_MINUS_P is non-null only when accepted Q and P share horizon/unit; uncertainty and sign status are explicit.

### PROB-001 — CONFIRMED / P1 / PROBABILITY

- defect_id: `PROB-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `PROBABILITY`
- observed symptom: All V1 binary targets predict future internal state/phase predicates rather than realized market risk.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: build_target_ledger labels cross-market IV jump, pressure onset, systemic phase, persistence and repair from future state records.
- financial consequence: Self-referential targets can reward ontology persistence without forecasting future economic risk.
- minimal repair: Retire the old events from V2 primary acceptance and label frozen realized variance/path targets.
- affected files: `src/matshix/probability/targets.py`
- semantic/version impact: New V2 target and probability definition versions.
- station acceptance criterion: Primary targets are outcome-ledger fields and their labels do not read phase, probability or strategy data.

### SAMPLE-001 — CONFIRMED / P1 / PROBABILITY

- defect_id: `SAMPLE-001`
- status: `CONFIRMED`
- severity: `P1`
- layer: `PROBABILITY`
- observed symptom: The frozen 504-training plus 252-calibration path is unreachable for every V1 event in current history.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: V1 has 727 state sessions and at most 167 completed eligible labels for any event, versus at least 756 sequential completed labels before a 252-row calibrated OOF gate can be evaluated.
- financial consequence: INSUFFICIENT_HISTORY can be mistaken for a failed model or thresholds can be relaxed after seeing the gap.
- minimal repair: Keep gates frozen, report reachability separately and publish conditional_probability=null until passed.
- affected files: `src/matshix/probability/model.py`, `configs/model_v1.yaml`
- semantic/version impact: New V2 reachability status; probability gates are not lowered.
- station acceptance criterion: Each capability reports eligible/completed/required counts and stops before calibration when unreachable.

### ACCEPT-001 — CONFIRMED / P0 / ACCEPTANCE

- defect_id: `ACCEPT-001`
- status: `CONFIRMED`
- severity: `P0`
- layer: `ACCEPTANCE`
- observed symptom: V1 top-level research acceptance passes with zero calibrated model rows because a historical base rate satisfies latest_probability_judgment_available.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The frozen replay passes 19/19 while probability output contains 314 BASE_RATE_ONLY rows, zero CALIBRATED_MODEL rows and no Brier/ECE values.
- financial consequence: A green research integration check can be read as evidence that predictive capability passed.
- minimal repair: Separate data/integration, score, P forecast, calibration and formal gates; BASE_RATE_ONLY is never probability PASS.
- affected files: `src/matshix/pipeline.py`, `src/matshix/validation.py`
- semantic/version impact: New V2 station acceptance schema and verdict vocabulary.
- station acceptance criterion: Zero calibrated rows forces probability gate NOT_EVALUABLE/FAIL and prevents a station-ready verdict.

### Q-ROBUSTNESS-001 — INSUFFICIENT_EVIDENCE / P1 / Q

- defect_id: `Q-ROBUSTNESS-001`
- status: `INSUFFICIENT_EVIDENCE`
- severity: `P1`
- layer: `Q`
- observed symptom: V1 has only the 14:56 minute-close price proxy and no outcome-blind near-close VWAP sensitivity ledger.
- reproduction command: `.venv/bin/python -m matshix audit-weather-v2 --project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF`
- causal evidence: The baseline discloses MINUTE_CLOSE_1456 and missing bid/ask; no matched 14:52-14:56 positive-volume sensitivity artifact exists.
- financial consequence: Wing or Q classification stability under the research price proxy is not yet known.
- minimal repair: Add the frozen near-close VWAP scenario without consulting future outcomes or strategy returns.
- affected files: `src/matshix/data/aetf.py`, `src/matshix/surface/research.py`
- semantic/version impact: New V2 Q robustness artifact; no main-Q threshold change.
- station acceptance criterion: Core Q classifications remain stable under the frozen scenario or the Q gate stops as INSUFFICIENT_EVIDENCE.

## 阶段 A 停止点

- `CONFIRMED`：`ERA-001, OUTCOME-001, HORIZON-001, UPSIDE-001, UPSIDE-002, TIMING-001, PHASE-001, P-001, QP-001, PROB-001, SAMPLE-001, ACCEPT-001`。
- `REJECTED_LEAD`：`UNIT-001`。
- `INSUFFICIENT_EVIDENCE`：`Q-ROBUSTNESS-001`。
- 下一提交必须只冻结 Authority、era、outcome、Q/P/Q−P、primary targets、predictor registry 与 acceptance gates；不得先改语义代码。
- `Q-ROBUSTNESS-001` 在 outcome-blind near-close VWAP sensitivity 完成前保持证据不足；若核心 Q 分类不稳定，施工必须停止。
