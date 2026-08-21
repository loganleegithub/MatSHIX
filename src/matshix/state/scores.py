from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from matshix.constants import ECONOMIC_WEIGHTS, INDEX_ORDER, INDEX_TO_CARRIER, SEGMENT_ORDER
from matshix.features.cross_section import breadth_metrics, segment_values, weighted_axis
from matshix.features.percentile import rolling_midrank_percentile
from matshix.logic import Tri, at_least_k_true

AXIS_COMPONENTS: dict[str, tuple[tuple[str, float], ...]] = {
    "shock": (
        ("p_d1_log_iv30", 0.35),
        ("p_d5_log_iv30", 0.25),
        ("p_iv_vol_of_vol20", 0.20),
        ("p_neg_etf_return_1d", 0.20),
    ),
    "down_tail": (("p_down_skew25", 0.65), ("p_d5_down_skew25", 0.35)),
    "up_tail": (("p_up_skew25", 0.65), ("p_d5_up_skew25", 0.35)),
    "persistence": (
        ("p_fvol_30_90", 0.40),
        ("p_iv90", 0.25),
        ("p_d5_fvol_30_90", 0.20),
        ("p_term_log_ratio_30_90", 0.15),
    ),
    "repair": (
        ("p_neg_d5_log_iv30", 0.30),
        ("p_neg_d5_down_skew25", 0.25),
        ("p_neg_d5_fvol_30_90", 0.20),
        ("p_etf_return_5d", 0.15),
        ("p_neg_d5_iv_vol_of_vol20", 0.10),
    ),
}
INDEX_PRESSURE_WEIGHTS = {
    "insurance_level": 0.20,
    "shock": 0.30,
    "down_tail": 0.25,
    "persistence": 0.25,
}
PRESSURE_WEIGHTS = {
    "insurance_level": 0.20,
    "shock": 0.25,
    "down_tail": 0.20,
    "persistence": 0.15,
    "breadth": 0.20,
}


def _weighted_fixed(
    row: Mapping[str, Any], components: tuple[tuple[str, float], ...]
) -> float | None:
    total = 0.0
    for field, weight in components:
        value = row.get(field)
        if value is None or pd.isna(value):
            return None
        total += weight * float(value)
    return 100.0 * total


def score_index(row: Mapping[str, Any]) -> dict[str, Any]:
    level = row.get("p_iv30")
    axes: dict[str, float | None] = {
        "insurance_level": None if level is None or pd.isna(level) else 100.0 * float(level)
    }
    axes.update(
        {axis: _weighted_fixed(row, components) for axis, components in AXIS_COMPONENTS.items()}
    )
    if all(axes[field] is not None for field in INDEX_PRESSURE_WEIGHTS):
        pressure_total = 0.0
        for field, weight in INDEX_PRESSURE_WEIGHTS.items():
            value = axes[field]
            assert value is not None
            pressure_total += weight * value
        axes["index_pressure"] = pressure_total
    else:
        axes["index_pressure"] = None
    complete = all(value is not None and np.isfinite(value) for value in axes.values())
    surface_status = str(row.get("surface_status", "UNKNOWN"))
    if surface_status == "VALID" and complete:
        status = "OK"
    elif surface_status != "UNKNOWN" or any(value is not None for value in axes.values()):
        status = "PARTIAL"
    else:
        status = "UNKNOWN"
    issues = row.get("issues", [])
    if isinstance(issues, str):
        issues = [value for value in issues.split("|") if value]
    return {
        "source_carrier": INDEX_TO_CARRIER[str(row["economic_index_id"])],
        "data_status": status,
        "state": axes,
        "issues": list(issues),
    }


def _weighted_raw(rows: dict[str, Mapping[str, Any]], field: str) -> float | None:
    total = 0.0
    for index in INDEX_ORDER:
        value = rows[index].get(field)
        if value is None or not np.isfinite(value):
            return None
        total += ECONOMIC_WEIGHTS[index] * float(value)
    return total


def aggregate_market_session(rows: dict[str, Mapping[str, Any]]) -> dict[str, Any]:
    if set(rows) != set(INDEX_ORDER):
        raise ValueError("exactly four economic-index rows are required")
    index_states = {index: score_index(rows[index]) for index in INDEX_ORDER}
    ok_count = sum(value["data_status"] == "OK" for value in index_states.values())
    data_status = "OK" if ok_count == 4 else "PARTIAL" if ok_count else "UNKNOWN"
    if data_status == "OK":
        confidence = (
            "DEGRADED" if any(value["issues"] for value in index_states.values()) else "FULL"
        )
    else:
        confidence = "LOW" if data_status == "PARTIAL" else "NONE"
    index_axis = {
        axis: {index: index_states[index]["state"][axis] for index in INDEX_ORDER}
        for axis in (
            "insurance_level",
            "shock",
            "down_tail",
            "up_tail",
            "persistence",
            "repair",
            "index_pressure",
        )
    }
    breadth = breadth_metrics(
        index_pressure=index_axis["index_pressure"],
        index_shock=index_axis["shock"],
        index_down_tail=index_axis["down_tail"],
        index_persistence=index_axis["persistence"],
    )
    market_scores = {
        axis: weighted_axis(index_axis[axis])
        for axis in (
            "insurance_level",
            "shock",
            "down_tail",
            "up_tail",
            "persistence",
            "repair",
        )
    }
    market_scores["breadth"] = breadth["breadth_score"]
    if data_status == "OK" and all(market_scores[field] is not None for field in PRESSURE_WEIGHTS):
        pressure = 0.0
        for field, weight in PRESSURE_WEIGHTS.items():
            value = market_scores[field]
            assert value is not None
            pressure += weight * value
    else:
        pressure = None
        market_scores = {key: None for key in market_scores}
    jump_by_index = {
        index: None
        if rows[index].get("p_d1_log_iv30") is None or pd.isna(rows[index].get("p_d1_log_iv30"))
        else float(rows[index]["p_d1_log_iv30"])
        for index in INDEX_ORDER
    }
    jump_scores = segment_values(jump_by_index)
    segment_jump: dict[str, Tri] = {}
    for segment in SEGMENT_ORDER:
        jump_score = jump_scores[segment]
        segment_jump[segment] = None if jump_score is None else jump_score >= 0.90
    index_pressures = [
        value for value in index_axis["index_pressure"].values() if value is not None
    ]
    dispersion = None if len(index_pressures) != 4 else max(index_pressures) - min(index_pressures)
    return {
        "session_date": str(next(iter(rows.values()))["session_date"]),
        "evidence_tier": "RESEARCH_ONLY",
        "data_status": data_status,
        "confidence": confidence,
        "economic_indices": index_states,
        "scores": market_scores,
        "pressure_score": pressure,
        "breadth_metrics": breadth,
        "segment_iv_jump_score": jump_scores,
        "segment_iv_jump": segment_jump,
        "cross_market_iv_jump": at_least_k_true(segment_jump.values(), 2),
        "all_segment_iv_jump": at_least_k_true(segment_jump.values(), 3),
        "cross_section_pressure_dispersion": dispersion,
        "aggregate_d5_fvol30_90": _weighted_raw(rows, "d5_fvol_30_90"),
        "aggregate_etf_return_5d": _weighted_raw(rows, "etf_return_5d"),
        "aggregate_vrp_value": _weighted_raw(rows, "vrp_ewma94"),
        "aggregate_vrp_percentile": _weighted_raw(rows, "vrp_percentile"),
        "aggregate_iv_vol_of_vol_percentile": _weighted_raw(rows, "p_iv_vol_of_vol20"),
        "front_event_premium_max": None,
    }


def build_market_score_history(
    index_features: pd.DataFrame,
    *,
    reference_sessions: int = 504,
    minimum_valid: int = 252,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    frame = index_features.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    for session, group in frame.groupby("session_date", sort=True):
        rows = {str(row["economic_index_id"]): row for row in group.to_dict(orient="records")}
        if set(rows) != set(INDEX_ORDER):
            continue
        record = aggregate_market_session(rows)
        record["session_date"] = pd.Timestamp(session)
        records.append(record)
    result = pd.DataFrame(records).sort_values("session_date").reset_index(drop=True)
    result["d5_pressure_score"] = pd.to_numeric(
        result["pressure_score"], errors="coerce"
    ) - pd.to_numeric(result["pressure_score"], errors="coerce").shift(5)
    # Canonical contract: percentile of the aggregate raw series itself.
    result["aggregate_d5_fvol30_90_percentile"] = rolling_midrank_percentile(
        pd.to_numeric(result["aggregate_d5_fvol30_90"], errors="coerce"),
        reference_sessions=reference_sessions,
        minimum_valid=minimum_valid,
    )
    return result
