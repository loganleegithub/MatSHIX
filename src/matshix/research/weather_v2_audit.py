from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from matshix.calendar import exchange_sessions_in_range
from matshix.constants import CARRIER_TO_INDEX
from matshix.data.aetf import AetfPaths, contract_master
from matshix.probability.predictors import PREDICTOR_FIELDS
from matshix.serialization import file_hash, jsonable, write_json
from matshix.storage import write_parquet

AUDIT_VERSION = "MATSHIX_V2_BUSINESS_AUDIT_1.0.0"
BASELINE_ARTIFACTS = (
    "v1_carrier_surface.parquet",
    "v1_index_features.parquet",
    "v1_market_states.parquet",
    "v1_targets.parquet",
    "v1_probabilities.parquet",
)
SHORTVOL_SOURCE_PATHS = (
    "src/matshix/research/shortvol.py",
    "src/matshix/research/shortvol_timing.py",
    "tests/test_shortvol_backtest.py",
    "tests/test_shortvol_timing.py",
    "MATSHIX_510300_SHORT_VOL_BACKTEST_DESIGN.md",
)
FORBIDDEN_STRATEGY_INPUTS = (
    "trade_ledger.csv",
    "daily_ledger.parquet",
    "rejection_ledger.csv",
    "account_nav",
    "option_legs",
    "position_units",
    "strategy_pnl",
)

ERA_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "coverage_regime": "ERA_A_50_ONLY",
        "start_session": "2015-02-09",
        "end_session": "2019-12-22",
        "available_carriers": ("SSE50_510050",),
    },
    {
        "coverage_regime": "ERA_B_50_300",
        "start_session": "2019-12-23",
        "end_session": "2022-09-18",
        "available_carriers": ("SSE50_510050", "CSI300_510300"),
    },
    {
        "coverage_regime": "ERA_C_50_300_500",
        "start_session": "2022-09-19",
        "end_session": "2023-06-04",
        "available_carriers": (
            "SSE50_510050",
            "CSI300_510300",
            "CSI500_510500",
        ),
    },
    {
        "coverage_regime": "ERA_D_FOUR_CARRIERS",
        "start_session": "2023-06-05",
        "end_session": None,
        "available_carriers": tuple(CARRIER_TO_INDEX),
    },
)


def _defect(
    defect_id: str,
    status: str,
    severity: str,
    layer: str,
    symptom: str,
    causal_evidence: str,
    financial_consequence: str,
    minimal_repair: str,
    affected_files: list[str],
    semantic_impact: str,
    acceptance_criterion: str,
) -> dict[str, Any]:
    return {
        "defect_id": defect_id,
        "status": status,
        "severity": severity,
        "layer": layer,
        "observed_symptom": symptom,
        "reproduction_command": (
            ".venv/bin/python -m matshix audit-weather-v2 "
            "--project-dir . --aetf-root /Users/logan/OptiMatrix_DATA/AETF"
        ),
        "causal_evidence": causal_evidence,
        "financial_consequence": financial_consequence,
        "minimal_repair": minimal_repair,
        "affected_files": affected_files,
        "semantic_version_impact": semantic_impact,
        "station_acceptance_criterion": acceptance_criterion,
    }


DEFECT_LEDGER: tuple[dict[str, Any], ...] = (
    _defect(
        "ERA-001",
        "CONFIRMED",
        "P0",
        "DATA",
        "V1 starts the common market-state ledger only when all four carriers exist and has no "
        "machine-readable listing era or NOT_LISTED carrier rows.",
        "AETF contract master dates are 2015-02-09, 2019-12-23, 2022-09-19 and "
        "2023-06-05. V1 surface history contains 100 ERA_C sessions, but the state builder "
        "silently skips sessions whose economic-index set is not exactly the four-index set.",
        "Three-carrier history cannot be distinguished from unavailable four-market history, "
        "so coverage and breadth claims can be misinterpreted.",
        "Add an immutable era registry and carry coverage_regime, available_carrier_count, "
        "listing_age_sessions and NOT_LISTED through V2 records.",
        ["src/matshix/state/scores.py", "src/matshix/data/aetf.py"],
        "New V2 data and state schema; V1 remains frozen.",
        "Contract-master launch dates match hand checks; pre-listing rows are NOT_LISTED and "
        "no partial era is labelled four-carrier breadth.",
    ),
    _defect(
        "OUTCOME-001",
        "CONFIRMED",
        "P0",
        "OUTCOME",
        "V1 has no strategy-independent realized variance, path or overnight-gap outcome ledger.",
        "The frozen targets table labels future internal weather states only; no baseline artifact "
        "contains realized_variance, max_up_log_move, max_down_log_move or overnight_gap fields.",
        "Forecast quality cannot be judged against future market risk, so station usefulness and "
        "internal-state persistence are conflated.",
        "Build the frozen H5/H10/H20 ETF outcome ledger before changing weather features.",
        ["src/matshix/probability/targets.py"],
        "New V2 outcome schema and definition version.",
        "Outcome hand checks pass; incomplete windows are CENSORED and use no weather or strategy input.",
    ),
    _defect(
        "HORIZON-001",
        "CONFIRMED",
        "P0",
        "QP",
        "V1 Q facts use fixed 30/60/90 calendar-day tenors while event targets use 1/5/20 "
        "exchange sessions; no same-target H20 Q/P pair exists.",
        "The frozen surface columns are iv30_mf/iv60_mf/iv90_mf and the target horizons are "
        "1, 5 and 20 sessions. V1 vrp_ewma94 compares only the 30-day IV point to EWMA94.",
        "A premium sign can be attributed to tenor mismatch rather than compensation.",
        "Construct exact-bracket H20 total variance using the actual target-end year fraction and "
        "compare it with H20 P variance in identical units.",
        ["src/matshix/surface/research.py", "src/matshix/features/history.py"],
        "New V2 Q and Q_MINUS_P definitions; no reinterpretation of V1 columns.",
        "Every primary Q_MINUS_P row has the same carrier, target window, unit and horizon on both sides.",
    ),
    _defect(
        "UNIT-001",
        "REJECTED_LEAD",
        "P0",
        "QP",
        "The suspected V1 IV-versus-RV arithmetic unit mix is not reproduced.",
        "For every non-null frozen row, vrp_ewma94 equals (iv30_mf/100)^2 minus "
        "rv_forecast30 to floating-point tolerance; both operands are annualized variance.",
        "No arithmetic repair is justified; changing the formula would create a false defect.",
        "Preserve V1 arithmetic as a golden test and add explicit unit/measure fields only in V2.",
        ["src/matshix/features/history.py"],
        "No V1 semantic change; V2 adds metadata.",
        "Golden variance arithmetic remains byte-compatible and every V2 measure declares its unit.",
    ),
    _defect(
        "UPSIDE-001",
        "CONFIRMED",
        "P1",
        "PROBABILITY",
        "V1 computes up_tail but none of the five frozen event predictor registries consumes it.",
        "The union of PREDICTOR_FIELDS contains down_tail_scaled but not up_tail_scaled.",
        "Call-wing repricing cannot affect conditional risk estimates even when the state vector observes it.",
        "Freeze new target-specific, two-sided V2 predictor registries; do not append up_tail to old events.",
        ["src/matshix/probability/predictors.py"],
        "New V2 predictor registry and model version.",
        "Put/Call mirror fixtures swap predictor sides and upside targets receive causal call-side facts.",
    ),
    _defect(
        "UPSIDE-002",
        "CONFIRMED",
        "P1",
        "STATE",
        "V1 shock, breadth, hard-acute and repair semantics are structurally downside-pressure led.",
        "Shock includes negative ETF return; hard_acute accepts down_tail or broad pressure but not "
        "up_tail; repair is conditioned on recent stress and decreasing downside pressure.",
        "An upside convexity shock can be reported as calm or merely as a late human phase.",
        "Publish orthogonal common-IV, downside and upside shock/breadth/persistence/repair facts.",
        ["src/matshix/state/scores.py", "src/matshix/state/ontology.py"],
        "New V2 two-sided state schema and state version.",
        "Mirrored fixtures exchange down/up facts and an upside shock cannot be suppressed solely by return sign.",
    ),
    _defect(
        "TIMING-001",
        "CONFIRMED",
        "P1",
        "STATE",
        "UPSIDE_CONVEXITY_PRICED requires the aggregate trailing five-session ETF return already to be positive.",
        "The V1 ontology branch combines tail=UPSIDE_PRICED, up_tail>=75 and "
        "aggregate_etf_return_5d>0 as mandatory conditions.",
        "The station can recognize upside repricing only after part of the move has occurred.",
        "Treat past return as confirmation/counter-evidence, not as an entry gate for leading upside risk.",
        ["src/matshix/state/ontology.py"],
        "New V2 phase definition version.",
        "An outcome-blind rising call-wing fixture enters upside-building facts before a required past rally.",
    ),
    _defect(
        "PHASE-001",
        "CONFIRMED",
        "P1",
        "ACCEPTANCE",
        "The downstream ShortVol adapter consumes primary_phase as a machine sizing map and only a "
        "subset of downside-oriented local axes as caps.",
        "shortvol.py renames primary_phase to phase and maps PHASE_UNITS; its local cap reads "
        "index_pressure, shock, down_tail and persistence but not up_tail.",
        "A lossy human summary can silently become trade permission and discard orthogonal risk facts.",
        "Freeze a versioned vector interface; retain primary_phase only as a human summary.",
        ["src/matshix/research/shortvol.py", "src/matshix/state/ontology.py"],
        "New V2 consumer interface; frozen ShortVol remains unchanged during station work.",
        "Station acceptance and future consumers use vector fields and no weather snapshot contains trade permission.",
    ),
    _defect(
        "P-001",
        "CONFIRMED",
        "P1",
        "P",
        "V1 exposes EWMA94 as rv_forecast30 without an independent physical-forecast harness.",
        "No frozen artifact reports QLIKE, bias, interval coverage or comparison with climatology, "
        "rolling RV and HAR-RV on the same cohort.",
        "Q_MINUS_P can inherit a weak or biased P estimate and appear to measure compensation.",
        "Evaluate frozen baselines and a small pre-specified challenger on causal rolling H20 outcomes.",
        ["src/matshix/features/history.py"],
        "New V2 P model and validation versions.",
        "P beats its frozen benchmark gates with block-aware evidence or is published as BASELINE_ONLY/FAIL.",
    ),
    _defect(
        "QP-001",
        "CONFIRMED",
        "P1",
        "QP",
        "V1 VRP is one 30-day-IV minus EWMA94 point estimate with percentile labels and no uncertainty.",
        "The frozen features table has vrp_ewma94 and vrp_percentile but no forecast interval, "
        "same-H20 status, sign confidence or model disagreement.",
        "A fragile point estimate can be presented as stable compensation.",
        "Publish same-horizon variance difference, quantiles/interval, sign confidence and abstention status.",
        ["src/matshix/features/history.py"],
        "New V2 Q_MINUS_P definition and schema versions.",
        "Q_MINUS_P is non-null only when accepted Q and P share horizon/unit; uncertainty and sign status are explicit.",
    ),
    _defect(
        "PROB-001",
        "CONFIRMED",
        "P1",
        "PROBABILITY",
        "All V1 binary targets predict future internal state/phase predicates rather than realized market risk.",
        "build_target_ledger labels cross-market IV jump, pressure onset, systemic phase, persistence "
        "and repair from future state records.",
        "Self-referential targets can reward ontology persistence without forecasting future economic risk.",
        "Retire the old events from V2 primary acceptance and label frozen realized variance/path targets.",
        ["src/matshix/probability/targets.py"],
        "New V2 target and probability definition versions.",
        "Primary targets are outcome-ledger fields and their labels do not read phase, probability or strategy data.",
    ),
    _defect(
        "SAMPLE-001",
        "CONFIRMED",
        "P1",
        "PROBABILITY",
        "The frozen 504-training plus 252-calibration path is unreachable for every V1 event in current history.",
        "V1 has 727 state sessions and at most 167 completed eligible labels for any event, versus at "
        "least 756 sequential completed labels before a 252-row calibrated OOF gate can be evaluated.",
        "INSUFFICIENT_HISTORY can be mistaken for a failed model or thresholds can be relaxed after seeing the gap.",
        "Keep gates frozen, report reachability separately and publish conditional_probability=null until passed.",
        ["src/matshix/probability/model.py", "configs/model_v1.yaml"],
        "New V2 reachability status; probability gates are not lowered.",
        "Each capability reports eligible/completed/required counts and stops before calibration when unreachable.",
    ),
    _defect(
        "ACCEPT-001",
        "CONFIRMED",
        "P0",
        "ACCEPTANCE",
        "V1 top-level research acceptance passes with zero calibrated model rows because a historical "
        "base rate satisfies latest_probability_judgment_available.",
        "The frozen replay passes 19/19 while probability output contains 314 BASE_RATE_ONLY rows, "
        "zero CALIBRATED_MODEL rows and no Brier/ECE values.",
        "A green research integration check can be read as evidence that predictive capability passed.",
        "Separate data/integration, score, P forecast, calibration and formal gates; BASE_RATE_ONLY is never probability PASS.",
        ["src/matshix/pipeline.py", "src/matshix/validation.py"],
        "New V2 station acceptance schema and verdict vocabulary.",
        "Zero calibrated rows forces probability gate NOT_EVALUABLE/FAIL and prevents a station-ready verdict.",
    ),
    _defect(
        "Q-ROBUSTNESS-001",
        "INSUFFICIENT_EVIDENCE",
        "P1",
        "Q",
        "V1 has only the 14:56 minute-close price proxy and no outcome-blind near-close VWAP sensitivity ledger.",
        "The baseline discloses MINUTE_CLOSE_1456 and missing bid/ask; no matched 14:52-14:56 "
        "positive-volume sensitivity artifact exists.",
        "Wing or Q classification stability under the research price proxy is not yet known.",
        "Add the frozen near-close VWAP scenario without consulting future outcomes or strategy returns.",
        ["src/matshix/data/aetf.py", "src/matshix/surface/research.py"],
        "New V2 Q robustness artifact; no main-Q threshold change.",
        "Core Q classifications remain stable under the frozen scenario or the Q gate stops as INSUFFICIENT_EVIDENCE.",
    ),
)


@dataclass(frozen=True)
class WeatherV2AuditArtifacts:
    daily_path: Path
    summary_path: Path
    audit_path: Path
    summary: dict[str, Any]


def coverage_regime(session: str | pd.Timestamp) -> str:
    value = pd.Timestamp(session).normalize()
    for era in ERA_REGISTRY:
        start = pd.Timestamp(str(era["start_session"]))
        end_value = era["end_session"]
        if value >= start and (end_value is None or value <= pd.Timestamp(str(end_value))):
            return str(era["coverage_regime"])
    raise ValueError(f"session predates the frozen MatSHIX era registry: {value.date()}")


def _sha256_without_prefix(path: Path) -> str:
    return file_hash(path).removeprefix("sha256:")


def _verify_baseline(project: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("invariants", {}).get("baseline_status") != "PASS":
        raise ValueError("V1 baseline manifest is not PASS")
    baseline = project / "outputs/v2_baseline"
    artifacts = manifest.get("artifacts", {})
    for name in BASELINE_ARTIFACTS:
        path = baseline / name
        expected = artifacts.get(name, {}).get("sha256")
        if not path.is_file() or expected != _sha256_without_prefix(path):
            raise ValueError(f"V1 baseline hash mismatch: {name}")
    frozen_sources = manifest.get("shortvol_freeze", {}).get("source_hashes", {})
    for relative in SHORTVOL_SOURCE_PATHS:
        path = project / relative
        if frozen_sources.get(relative) != _sha256_without_prefix(path):
            raise ValueError(f"ShortVol source changed after freeze: {relative}")


def _listing_ages(
    sessions: pd.Series, carriers: pd.Series, listing_dates: dict[str, pd.Timestamp]
) -> pd.Series:
    first = min(listing_dates.values())
    last = pd.to_datetime(sessions).max()
    calendar = exchange_sessions_in_range(first, last)
    positions = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    ages: list[int | None] = []
    for session, carrier in zip(pd.to_datetime(sessions), carriers.astype(str), strict=True):
        launch = listing_dates[carrier]
        normalized = pd.Timestamp(session).normalize()
        if normalized < launch:
            ages.append(None)
        else:
            ages.append(positions[normalized] - positions[launch] + 1)
    return pd.Series(ages, index=sessions.index, dtype="Int64")


def build_business_audit_daily(
    surfaces: pd.DataFrame,
    features: pd.DataFrame,
    states: pd.DataFrame,
    listing_dates: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    """Build an outcome- and strategy-blind carrier/session audit panel."""

    surface = surfaces.copy()
    feature = features.copy()
    state = states.copy()
    for frame in (surface, feature, state):
        frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    sessions = pd.DatetimeIndex(surface["session_date"].drop_duplicates().sort_values())
    grid = pd.MultiIndex.from_product(
        [sessions, tuple(CARRIER_TO_INDEX)], names=["session_date", "carrier_id"]
    ).to_frame(index=False)
    grid["economic_index_id"] = grid["carrier_id"].map(CARRIER_TO_INDEX)
    grid["listing_date"] = grid["carrier_id"].map(listing_dates)
    grid["is_listed"] = grid["session_date"] >= grid["listing_date"]
    grid["listing_age_sessions"] = _listing_ages(
        grid["session_date"], grid["carrier_id"], listing_dates
    )
    grid["coverage_regime"] = grid["session_date"].map(coverage_regime)
    grid["available_carrier_count"] = grid.groupby("session_date")["is_listed"].transform("sum")
    observed_counts = surface.groupby("session_date")["carrier_id"].nunique()
    grid["observed_carrier_count"] = grid["session_date"].map(observed_counts).astype("Int64")

    surface_columns = [
        "session_date",
        "carrier_id",
        "surface_status",
        "evidence_tier",
        "vintage_kind",
        "decision_as_of",
        "available_at",
        "iv30_mf",
        "iv30_method",
        "iv60_mf",
        "iv60_method",
        "iv90_mf",
        "iv90_method",
        "iv_25d_put30",
        "iv_25d_put30_method",
        "iv_25d_call30",
        "iv_25d_call30_method",
        "down_skew25",
        "up_skew25",
        "fvar_30_90",
        "input_contracts",
        "eligible_contracts",
        "issues",
    ]
    frame = grid.merge(surface[surface_columns], on=["session_date", "carrier_id"], how="left")
    feature_columns = [
        "session_date",
        "carrier_id",
        "rv_forecast30",
        "vrp_ewma94",
        "vrp_percentile",
        "insurance_compensation",
    ]
    frame = frame.merge(feature[feature_columns], on=["session_date", "carrier_id"], how="left")
    state_columns = [
        "session_date",
        "data_status",
        "primary_phase",
        "pressure_score",
        "shock",
        "down_tail",
        "up_tail",
        "breadth",
        "repair",
        "hard_acute",
    ]
    state_frame = state[state_columns].rename(
        columns={
            column: f"v1_market_{column}" for column in state_columns if column != "session_date"
        }
    )
    frame = frame.merge(state_frame, on="session_date", how="left")

    frame["data_status"] = frame["surface_status"]
    frame.loc[~frame["is_listed"], "data_status"] = "NOT_LISTED"
    frame.loc[frame["is_listed"] & frame["surface_status"].isna(), "data_status"] = "MISSING"
    frame["price_proxy"] = (
        frame["surface_status"].notna().map({True: "MINUTE_CLOSE_1456", False: None})
    )
    method = frame["iv30_method"].fillna("UNAVAILABLE").astype(str)
    frame["q_30_method_status"] = "UNAVAILABLE"
    frame.loc[method.eq("TOTAL_VARIANCE_INTERPOLATION"), "q_30_method_status"] = (
        "EXACT_EXPIRY_BRACKET"
    )
    frame.loc[method.str.contains("NEAREST", regex=False), "q_30_method_status"] = (
        "NEAREST_EXPIRY_PROXY"
    )
    frame["q_variance_30_annualized"] = (pd.to_numeric(frame["iv30_mf"]) / 100.0) ** 2
    frame["p_variance_30_annualized"] = pd.to_numeric(frame["rv_forecast30"])
    frame["q_minus_p_variance_30_annualized"] = (
        frame["q_variance_30_annualized"] - frame["p_variance_30_annualized"]
    )
    frame["q_h20_status"] = "NOT_IMPLEMENTED_V1"
    frame["p_h20_status"] = "NOT_IMPLEMENTED_V1"
    frame["q_minus_p_h20_status"] = "NOT_IMPLEMENTED_V1"
    frame["realized_outcome_status"] = "NOT_IMPLEMENTED_V1"
    frame["history_evidence_kind"] = "RETROSPECTIVE_WALK_FORWARD"
    frame["audit_version"] = AUDIT_VERSION
    return frame.sort_values(["session_date", "carrier_id"], kind="stable").reset_index(drop=True)


def _group_records(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    records = frame.groupby(fields, dropna=False).size().rename("rows").reset_index()
    return list(jsonable(records.to_dict(orient="records")))


def _build_summary(
    project: Path,
    manifest: dict[str, Any],
    daily: pd.DataFrame,
    surfaces: pd.DataFrame,
    features: pd.DataFrame,
    states: pd.DataFrame,
    targets: pd.DataFrame,
    probabilities: pd.DataFrame,
    listing_dates: dict[str, pd.Timestamp],
    daily_path: Path,
) -> dict[str, Any]:
    expected_listing = {
        "SSE50_510050": "2015-02-09",
        "CSI300_510300": "2019-12-23",
        "CSI500_510500": "2022-09-19",
        "STAR50_588000": "2023-06-05",
    }
    actual_listing = {
        carrier: pd.Timestamp(value).date().isoformat()
        for carrier, value in sorted(listing_dates.items())
    }
    valid_units = features[["iv30_mf", "rv_forecast30", "vrp_ewma94"]].dropna()
    unit_residual = (
        (valid_units["iv30_mf"] / 100.0) ** 2
        - valid_units["rv_forecast30"]
        - valid_units["vrp_ewma94"]
    )
    target_completed = (
        targets.loc[targets["label_status"].isin(["OBSERVED_0", "OBSERVED_1"])]
        .groupby("event_id")
        .size()
        .sort_index()
    )
    predictor_union = sorted({field for values in PREDICTOR_FIELDS.values() for field in values})
    surface_coverage = surfaces.copy()
    surface_coverage["year"] = pd.to_datetime(surface_coverage["session_date"]).dt.year
    surface_coverage["iv30_exactness"] = surface_coverage["iv30_method"].map(
        lambda value: "EXACT_EXPIRY_BRACKET"
        if value == "TOTAL_VARIANCE_INTERPOLATION"
        else "NEAREST_EXPIRY_PROXY"
        if "NEAREST" in str(value)
        else "UNAVAILABLE"
    )
    probability_counts = {
        str(key): int(value)
        for key, value in probabilities["model_status"].value_counts(dropna=False).items()
    }
    confirmed = [item["defect_id"] for item in DEFECT_LEDGER if item["status"] == "CONFIRMED"]
    insufficient = [
        item["defect_id"] for item in DEFECT_LEDGER if item["status"] == "INSUFFICIENT_EVIDENCE"
    ]
    rejected = [item["defect_id"] for item in DEFECT_LEDGER if item["status"] == "REJECTED_LEAD"]
    return {
        "audit_version": AUDIT_VERSION,
        "audit_status": "STAGE_A_COMPLETE_SEMANTIC_IMPLEMENTATION_NOT_STARTED",
        "evidence_boundary": {
            "strategy_daily_returns_used": False,
            "strategy_artifacts_opened": False,
            "strategy_join_columns": [],
            "allowed_inputs": [
                "outputs/v2_baseline/v1_manifest.json",
                *[f"outputs/v2_baseline/{name}" for name in BASELINE_ARTIFACTS],
                "/Users/logan/OptiMatrix_DATA/AETF/OPTION/opt_basic.parquet",
                *SHORTVOL_SOURCE_PATHS,
            ],
            "forbidden_inputs": list(FORBIDDEN_STRATEGY_INPUTS),
        },
        "baseline": {
            "manifest_sha256": _sha256_without_prefix(
                project / "outputs/v2_baseline/v1_manifest.json"
            ),
            "baseline_id": manifest["baseline_id"],
            "v1_code_git_sha": manifest["repository"]["v1_code_git_sha"],
            "construction_plan_sha256": manifest["repository"]["construction_plan_sha256"],
            "engine_artifact_hash": manifest["build"]["engine_artifact_hash"],
            "deterministic_replay_mismatches": manifest["build"]["byte_mismatch_count"],
            "shortvol_source_hashes": manifest["shortvol_freeze"]["source_hashes"],
            "shortvol_failure_artifact_hashes_recorded_only": manifest["shortvol_freeze"][
                "failure_artifact_hashes"
            ],
            "shortvol_failure_artifacts_opened_by_stage_a": False,
        },
        "era_audit": {
            "registry": list(ERA_REGISTRY),
            "contract_master_listing_dates": actual_listing,
            "expected_listing_dates": expected_listing,
            "listing_dates_match": actual_listing == expected_listing,
            "daily_rows": len(daily),
            "session_range": [
                pd.Timestamp(daily["session_date"].min()).date().isoformat(),
                pd.Timestamp(daily["session_date"].max()).date().isoformat(),
            ],
            "session_counts_by_regime": _group_records(
                daily.drop_duplicates("session_date"), ["coverage_regime"]
            ),
            "carrier_data_status_counts": _group_records(
                daily, ["coverage_regime", "carrier_id", "data_status"]
            ),
        },
        "q_audit": {
            "price_proxy": "MINUTE_CLOSE_1456",
            "formal_bid_ask_available": False,
            "evidence_tier": "RESEARCH_ONLY",
            "surface_status_counts": _group_records(surfaces, ["surface_status"]),
            "carrier_year_iv30_method_counts": _group_records(
                surface_coverage, ["carrier_id", "year", "iv30_exactness"]
            ),
            "constant_tenor_calendar_days": [30, 60, 90],
            "h20_same_target_q_available": False,
            "near_close_vwap_sensitivity_available": False,
        },
        "unit_audit": {
            "checked_rows": len(valid_units),
            "identity": "vrp_ewma94 == (iv30_mf/100)^2 - rv_forecast30",
            "max_absolute_residual": float(unit_residual.abs().max()),
            "identity_passed": bool(unit_residual.abs().max() <= 1e-12),
            "unit_001_verdict": "REJECTED_LEAD",
        },
        "state_audit": {
            "rows": len(states),
            "session_range": [
                pd.Timestamp(states["session_date"].min()).date().isoformat(),
                pd.Timestamp(states["session_date"].max()).date().isoformat(),
            ],
            "first_state_equals_four_carrier_launch": bool(
                pd.Timestamp(states["session_date"].min()) == pd.Timestamp("2023-06-05")
            ),
            "era_c_surface_sessions_without_v1_market_state": int(
                daily.loc[daily["coverage_regime"].eq("ERA_C_50_300_500"), "session_date"].nunique()
            ),
            "data_status_counts": _group_records(states, ["data_status"]),
            "primary_phase_counts": _group_records(states, ["primary_phase"]),
        },
        "outcome_audit": {
            "strategy_independent_outcome_ledger_available": False,
            "target_horizons_sessions": sorted(int(value) for value in targets["horizon"].unique()),
            "target_event_ids": sorted(str(value) for value in targets["event_id"].unique()),
            "targets_are_internal_weather_events": True,
            "primary_realized_variance_h20_available": False,
            "primary_upside_path_h10_available": False,
            "primary_downside_path_h10_available": False,
        },
        "probability_audit": {
            "predictor_union": predictor_union,
            "up_tail_scaled_present": "up_tail_scaled" in predictor_union,
            "model_status_counts": probability_counts,
            "calibrated_model_rows": int(
                probabilities["model_status"].eq("CALIBRATED_MODEL").sum()
            ),
            "nonnull_brier_rows": int(probabilities["brier_skill"].notna().sum()),
            "nonnull_ece_rows": int(probabilities["ece"].notna().sum()),
            "completed_eligible_labels_by_event": {
                str(key): int(value) for key, value in target_completed.items()
            },
            "training_minimum_samples": 504,
            "calibration_samples": 252,
            "minimum_sequential_completed_labels": 756,
            "current_max_completed_eligible_labels": int(target_completed.max()),
            "calibration_gate_reachable_in_frozen_history": bool(target_completed.max() >= 756),
            "baseline_research_replay_acceptance": manifest["build"]["replay_a_acceptance"],
            "top_level_pass_with_zero_calibrated_models": bool(
                manifest["build"]["replay_a_acceptance"] == "PASS_19_OF_19"
                and probabilities["model_status"].ne("CALIBRATED_MODEL").all()
            ),
        },
        "defect_counts": {
            "CONFIRMED": len(confirmed),
            "REJECTED_LEAD": len(rejected),
            "INSUFFICIENT_EVIDENCE": len(insufficient),
        },
        "confirmed_defects": confirmed,
        "rejected_leads": rejected,
        "insufficient_evidence": insufficient,
        "defect_ledger": list(DEFECT_LEDGER),
        "output": {
            "business_audit_daily": str(daily_path.relative_to(project)),
            "business_audit_daily_sha256": _sha256_without_prefix(daily_path),
        },
        "construction_authorization": {
            "authority_document_required_before_semantic_code": True,
            "semantic_implementation_started": False,
            "only_confirmed_defects_authorized_after_authority_freeze": confirmed,
            "q_robustness_gate": "INSUFFICIENT_EVIDENCE",
        },
    }


def _render_audit(summary: dict[str, Any], summary_path: Path) -> str:
    era = summary["era_audit"]
    unit = summary["unit_audit"]
    probability = summary["probability_audit"]
    lines = [
        "# MatSHIX V2 阶段 A 业务审计与缺陷台账",
        "",
        f"- 审计合同：`{summary['audit_version']}`",
        f"- 阶段结论：`{summary['audit_status']}`",
        "- 证据边界：未读取 ShortVol 逐日收益、交易台账、选腿、仓位、退出、成本或 NAV。",
        "- 施工边界：本阶段未修改运行语义；任何语义施工须先冻结 `MATSHIX_V2_AUTHORITY.md`。",
        f"- 日审计表：`{summary['output']['business_audit_daily']}` / "
        f"`{summary['output']['business_audit_daily_sha256']}`",
        f"- 汇总 JSON：`outputs/v2_audit/business_audit_summary.json` / "
        f"`{_sha256_without_prefix(summary_path)}`",
        "",
        "## 核心事实",
        "",
        f"- contract master 上市日复核：`{'PASS' if era['listing_dates_match'] else 'FAIL'}`；"
        "510050/510300/510500/588000 分别为 2015-02-09、2019-12-23、"
        "2022-09-19、2023-06-05。",
        f"- V1 common state 从 2023-06-05 才开始；此前 `{summary['state_audit']['era_c_surface_sessions_without_v1_market_state']}` "
        "个 ERA_C surface session 没有机器可读的 partial-era market state。",
        f"- V1 VRP 单位恒等式检查 `{unit['checked_rows']}` 行，最大残差 "
        f"`{unit['max_absolute_residual']:.3e}`；`UNIT-001=REJECTED_LEAD`。",
        "- V1 没有策略无关 realized outcome、同期限 H20 Q/P 或 Q−P 主账本。",
        f"- V1 calibrated model 行数为 `{probability['calibrated_model_rows']}`；最大完整 eligible "
        f"标签数为 `{probability['current_max_completed_eligible_labels']}`，低于冻结的顺序可达门 "
        f"`{probability['minimum_sequential_completed_labels']}`。",
        "- V1 replay 的集成验收可通过，但这不构成 P、Q−P 或条件概率能力 PASS。",
        "",
        "## 缺陷裁决",
        "",
    ]
    for defect in summary["defect_ledger"]:
        affected = ", ".join(f"`{path}`" for path in defect["affected_files"])
        lines.extend(
            [
                f"### {defect['defect_id']} — {defect['status']} / {defect['severity']} / {defect['layer']}",
                "",
                f"- defect_id: `{defect['defect_id']}`",
                f"- status: `{defect['status']}`",
                f"- severity: `{defect['severity']}`",
                f"- layer: `{defect['layer']}`",
                f"- observed symptom: {defect['observed_symptom']}",
                f"- reproduction command: `{defect['reproduction_command']}`",
                f"- causal evidence: {defect['causal_evidence']}",
                f"- financial consequence: {defect['financial_consequence']}",
                f"- minimal repair: {defect['minimal_repair']}",
                f"- affected files: {affected}",
                f"- semantic/version impact: {defect['semantic_version_impact']}",
                f"- station acceptance criterion: {defect['station_acceptance_criterion']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 阶段 A 停止点",
            "",
            f"- `CONFIRMED`：`{', '.join(summary['confirmed_defects'])}`。",
            f"- `REJECTED_LEAD`：`{', '.join(summary['rejected_leads'])}`。",
            f"- `INSUFFICIENT_EVIDENCE`：`{', '.join(summary['insufficient_evidence'])}`。",
            "- 下一提交必须只冻结 Authority、era、outcome、Q/P/Q−P、primary targets、"
            "predictor registry 与 acceptance gates；不得先改语义代码。",
            "- `Q-ROBUSTNESS-001` 在 outcome-blind near-close VWAP sensitivity 完成前保持证据不足；"
            "若核心 Q 分类不稳定，施工必须停止。",
            "",
        ]
    )
    return "\n".join(lines)


def run_weather_v2_business_audit(*, project_dir: Path, aetf_root: Path) -> WeatherV2AuditArtifacts:
    project = project_dir.expanduser().resolve()
    baseline = project / "outputs/v2_baseline"
    manifest_path = baseline / "v1_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_baseline(project, manifest)

    surfaces = pd.read_parquet(baseline / "v1_carrier_surface.parquet")
    features = pd.read_parquet(baseline / "v1_index_features.parquet")
    states = pd.read_parquet(baseline / "v1_market_states.parquet")
    targets = pd.read_parquet(baseline / "v1_targets.parquet")
    probabilities = pd.read_parquet(baseline / "v1_probabilities.parquet")
    contracts = contract_master(AetfPaths.from_root(aetf_root))
    listing_dates = {
        str(carrier): pd.Timestamp(value).normalize()
        for carrier, value in contracts.groupby("carrier_id")["list_date"].min().items()
    }
    if set(listing_dates) != set(CARRIER_TO_INDEX):
        raise ValueError("contract master does not contain the frozen four carriers")

    daily = build_business_audit_daily(surfaces, features, states, listing_dates)
    output = project / "outputs/v2_audit"
    daily_path = write_parquet(daily, output / "business_audit_daily.parquet")
    summary_path = output / "business_audit_summary.json"
    summary = _build_summary(
        project,
        manifest,
        daily,
        surfaces,
        features,
        states,
        targets,
        probabilities,
        listing_dates,
        daily_path,
    )
    write_json(summary_path, summary)
    audit_path = project / "MATSHIX_V2_AUDIT.md"
    audit_path.write_text(_render_audit(summary, summary_path), encoding="utf-8")
    return WeatherV2AuditArtifacts(daily_path, summary_path, audit_path, summary)
