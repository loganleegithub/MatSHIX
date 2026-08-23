from __future__ import annotations

import pandas as pd

from matshix.research.weather_v2_audit import (
    DEFECT_LEDGER,
    build_business_audit_daily,
    coverage_regime,
)


def test_frozen_era_boundaries() -> None:
    assert coverage_regime("2015-02-09") == "ERA_A_50_ONLY"
    assert coverage_regime("2019-12-22") == "ERA_A_50_ONLY"
    assert coverage_regime("2019-12-23") == "ERA_B_50_300"
    assert coverage_regime("2022-09-19") == "ERA_C_50_300_500"
    assert coverage_regime("2023-06-04") == "ERA_C_50_300_500"
    assert coverage_regime("2023-06-05") == "ERA_D_FOUR_CARRIERS"


def test_daily_audit_preserves_not_listed_without_strategy_fields() -> None:
    sessions = pd.to_datetime(["2023-06-02", "2023-06-05"])
    carriers = ["SSE50_510050", "CSI300_510300", "CSI500_510500"]
    surface_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    for session in sessions:
        active = carriers if session == pd.Timestamp("2023-06-02") else [*carriers, "STAR50_588000"]
        for carrier in active:
            surface_rows.append(
                {
                    "session_date": session,
                    "carrier_id": carrier,
                    "surface_status": "VALID",
                    "evidence_tier": "RESEARCH_ONLY",
                    "vintage_kind": "PROVIDER_RECONSTRUCTED",
                    "decision_as_of": session + pd.Timedelta(days=1),
                    "available_at": pd.NaT,
                    "iv30_mf": 20.0,
                    "iv30_method": "TOTAL_VARIANCE_INTERPOLATION",
                    "iv60_mf": 21.0,
                    "iv60_method": "TOTAL_VARIANCE_INTERPOLATION",
                    "iv90_mf": 22.0,
                    "iv90_method": "TOTAL_VARIANCE_INTERPOLATION",
                    "iv_25d_put30": 23.0,
                    "iv_25d_put30_method": "TOTAL_VARIANCE_INTERPOLATION",
                    "iv_25d_call30": 19.0,
                    "iv_25d_call30_method": "TOTAL_VARIANCE_INTERPOLATION",
                    "down_skew25": 3.0,
                    "up_skew25": -1.0,
                    "fvar_30_90": 0.04,
                    "input_contracts": 20,
                    "eligible_contracts": 20,
                    "issues": "",
                }
            )
            feature_rows.append(
                {
                    "session_date": session,
                    "carrier_id": carrier,
                    "rv_forecast30": 0.03,
                    "vrp_ewma94": 0.01,
                    "vrp_percentile": 0.6,
                    "insurance_compensation": "NORMAL",
                }
            )
    states = pd.DataFrame(
        [
            {
                "session_date": pd.Timestamp("2023-06-05"),
                "data_status": "OK",
                "primary_phase": "BALANCED_MARKET",
                "pressure_score": 40.0,
                "shock": 30.0,
                "down_tail": 40.0,
                "up_tail": 45.0,
                "breadth": 30.0,
                "repair": 20.0,
                "hard_acute": False,
            }
        ]
    )
    listing_dates = {
        "SSE50_510050": pd.Timestamp("2015-02-09"),
        "CSI300_510300": pd.Timestamp("2019-12-23"),
        "CSI500_510500": pd.Timestamp("2022-09-19"),
        "STAR50_588000": pd.Timestamp("2023-06-05"),
    }
    result = build_business_audit_daily(
        pd.DataFrame(surface_rows), pd.DataFrame(feature_rows), states, listing_dates
    )
    star_before_listing = result.loc[
        result["session_date"].eq(pd.Timestamp("2023-06-02"))
        & result["carrier_id"].eq("STAR50_588000")
    ].iloc[0]
    assert star_before_listing["data_status"] == "NOT_LISTED"
    assert pd.isna(star_before_listing["listing_age_sessions"])
    assert star_before_listing["available_carrier_count"] == 3
    assert set(result["history_evidence_kind"]) == {"RETROSPECTIVE_WALK_FORWARD"}
    forbidden_tokens = {"pnl", "nav", "trade", "position", "leg", "risk_unit"}
    assert not any(
        token in column.lower() for column in result.columns for token in forbidden_tokens
    )


def test_defect_ledger_has_contract_fields_and_no_pre_authority_semantic_permission() -> None:
    required = {
        "defect_id",
        "status",
        "severity",
        "layer",
        "observed_symptom",
        "reproduction_command",
        "causal_evidence",
        "financial_consequence",
        "minimal_repair",
        "affected_files",
        "semantic_version_impact",
        "station_acceptance_criterion",
    }
    assert all(required <= set(defect) for defect in DEFECT_LEDGER)
    by_id = {str(defect["defect_id"]): defect for defect in DEFECT_LEDGER}
    assert by_id["UNIT-001"]["status"] == "REJECTED_LEAD"
    assert by_id["Q-ROBUSTNESS-001"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert by_id["ACCEPT-001"]["status"] == "CONFIRMED"
