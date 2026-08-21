from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from matshix.constants import CARRIER_TO_INDEX, EVENT_IDS, EXCLUDED_CARRIERS
from matshix.pipeline import compute_engine_artifact_hash


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: dict[str, bool]
    details: dict[str, Any]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _schema_valid(instance: dict[str, Any], schema_path: Path) -> tuple[bool, list[str]]:
    schema = _read_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    return not errors, [f"{list(error.path)}: {error.message}" for error in errors]


def _equal_number(left: Any, right: Any, *, tolerance: float = 1e-10) -> bool:
    if left is None and (right is None or pd.isna(right)):
        return True
    if right is None and (left is None or pd.isna(left)):
        return True
    try:
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def verify_research_outputs(project_dir: Path) -> VerificationResult:
    project = project_dir.expanduser().resolve()
    processed = project / "data/processed/research"
    latest = _read_json(project / "outputs/research/latest.json")
    formal = _read_json(project / "outputs/formal/latest.json")
    dashboard = _read_json(project / "outputs/research/dashboard_data.json")
    acceptance = _read_json(project / "outputs/acceptance/real_data_research.json")
    state = pd.read_parquet(processed / "daily_market_state.parquet")
    surfaces = pd.read_parquet(processed / "carrier_surface.parquet")
    features = pd.read_parquet(processed / "economic_index_feature.parquet")
    index_states = pd.read_parquet(processed / "economic_index_state.parquet")
    probabilities = pd.read_parquet(processed / "event_probability.parquet")
    market_evidence = pd.read_parquet(processed / "market_evidence.parquet")
    issues = pd.read_parquet(processed / "issue_ledger.parquet")
    raw_options = pd.read_parquet(
        processed / "option_observation.parquet",
        columns=["option_underlying_code", "carrier_id", "evidence_tier"],
    )
    research_schema_ok, research_errors = _schema_valid(
        latest, project / "schemas/daily_snapshot.schema.json"
    )
    formal_schema_ok, formal_errors = _schema_valid(
        formal, project / "schemas/formal_unknown.schema.json"
    )
    final_session = pd.Timestamp(state["session_date"].max()).date().isoformat()
    final_state = state.sort_values("session_date").iloc[-1]
    surface_latest = surfaces.loc[
        pd.to_datetime(surfaces["session_date"]).dt.date.astype(str) == final_session
    ]
    feature_latest = features.loc[
        pd.to_datetime(features["session_date"]).dt.date.astype(str) == final_session
    ]
    probability_latest = probabilities.loc[
        pd.to_datetime(probabilities["session_date"]).dt.date.astype(str) == final_session
    ]
    surface_reconciled = len(surface_latest) == 4
    if surface_reconciled:
        for row in surface_latest.itertuples(index=False):
            index = CARRIER_TO_INDEX[str(row.carrier_id)]
            json_surface = latest["economic_indices"][index]["surface"]
            surface_reconciled = surface_reconciled and _equal_number(
                json_surface["iv30_mf"], row.iv30_mf
            )
            surface_reconciled = surface_reconciled and _equal_number(
                json_surface["iv90_mf"], row.iv90_mf
            )
    probabilities_reconciled = len(probability_latest) == len(EVENT_IDS)
    if probabilities_reconciled:
        for row in probability_latest.to_dict(orient="records"):
            output = latest["probabilities"][str(row["event_id"])]
            probabilities_reconciled = probabilities_reconciled and (
                output["model_status"] == row["model_status"]
                and output["event_status"] == row["event_status"]
                and _equal_number(output["probability"], row["probability"])
            )
    revision = str(latest["revision_id"])
    current_engine_hash = compute_engine_artifact_hash(project)
    parquet_revisions = {
        str(value)
        for frame in (state, surfaces, features, probabilities)
        for value in frame["revision_id"].dropna().unique()
    }
    excluded_absent = (
        not raw_options["option_underlying_code"].astype(str).eq("OP588080.SH").any()
        and not raw_options["carrier_id"].astype(str).isin(EXCLUDED_CARRIERS).any()
        and not surfaces["carrier_id"].astype(str).isin(EXCLUDED_CARRIERS).any()
    )
    daily_files = list((project / "outputs/research/daily").glob("*.json"))
    checks = {
        "research_schema_valid": research_schema_ok,
        "formal_unknown_schema_valid": formal_schema_ok,
        "real_input_nonempty": len(raw_options) > 0,
        "formal_publication_withheld": formal["publication_status"] == "WITHHELD"
        and formal["data_status"] == "UNKNOWN",
        "excluded_588080_absent": excluded_absent,
        "four_index_latest_complete": len(feature_latest) == 4,
        "normalized_index_state_complete": len(index_states) == 4 * len(state),
        "normalized_market_evidence_nonempty": len(market_evidence) > 0,
        "normalized_issue_ledger_nonempty": len(issues) > 0,
        "state_json_reconciled": latest["session_date"] == final_session
        and latest["primary_phase"] == final_state["primary_phase"]
        and _equal_number(latest["pressure_score"], final_state["pressure_score"]),
        "surface_json_reconciled": surface_reconciled,
        "probability_json_reconciled": probabilities_reconciled,
        "revision_reconciled": parquet_revisions == {revision}
        and dashboard["revision_id"] == revision,
        "engine_artifact_current": latest["engine_artifact_hash"] == current_engine_hash
        and formal["engine_artifact_hash"] == current_engine_hash,
        "dashboard_latest_reconciled": dashboard["days"][-1]["session_date"] == final_session,
        "proxy_confidence_not_full": not latest["narrative"]["research_proxies"]
        or latest["confidence"] != "FULL",
        "daily_replay_complete": len(daily_files) == len(state),
        "minimum_60_sessions": len(state) >= 60,
        "research_acceptance_passed": acceptance["overall_status"]
        == "PASS_RESEARCH_ONLY_FORMAL_BLOCKED",
        "formal_g0_not_overclaimed": acceptance["formal_gates"]["G0"] == "NOT_PASSED",
    }
    return VerificationResult(
        passed=all(checks.values()),
        checks=checks,
        details={
            "research_schema_errors": research_errors,
            "formal_schema_errors": formal_errors,
            "state_sessions": len(state),
            "surface_rows": len(surfaces),
            "feature_rows": len(features),
            "economic_index_state_rows": len(index_states),
            "probability_rows": len(probabilities),
            "market_evidence_rows": len(market_evidence),
            "issue_rows": len(issues),
            "raw_option_rows": len(raw_options),
            "latest_session": final_session,
            "revision_id": revision,
        },
    )
