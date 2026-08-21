from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PREDICTOR_FIELDS: dict[str, tuple[str, ...]] = {
    "cross_market_iv_jump_1d": (
        "insurance_level_scaled",
        "shock_scaled",
        "down_tail_scaled",
        "breadth_scaled",
        "aggregate_iv_vol_of_vol_percentile",
        "pressure_change5_scaled",
    ),
    "broad_pressure_onset_5d": (
        "shock_scaled",
        "breadth_scaled",
        "persistence_scaled",
        "down_tail_scaled",
        "cross_section_pressure_dispersion_scaled",
        "pressure_change5_scaled",
    ),
    "systemic_acute_stress_5d": (
        "shock_scaled",
        "down_tail_scaled",
        "breadth_scaled",
        "segment_iv_jump_true_share",
        "persistence_scaled",
        "pressure_change5_scaled",
    ),
    "persistent_cross_market_stress_20d": (
        "insurance_level_scaled",
        "persistence_scaled",
        "breadth_scaled",
        "down_tail_scaled",
        "aggregate_vrp_percentile",
        "pressure_change5_scaled",
    ),
    "fast_repair_5d": (
        "repair_scaled",
        "inverse_pressure_change5_scaled",
        "shock_scaled",
        "persistence_scaled",
        "breadth_scaled",
        "down_tail_scaled",
    ),
}


def add_probability_predictors(history: pd.DataFrame) -> pd.DataFrame:
    result = history.copy()
    for axis in ("insurance_level", "shock", "down_tail", "persistence", "breadth", "repair"):
        result[f"{axis}_scaled"] = result["scores"].map(
            lambda values, name=axis: np.nan
            if values.get(name) is None
            else float(values[name]) / 100.0
        )
    change = pd.to_numeric(result["d5_pressure_score"], errors="coerce")
    result["pressure_change5_scaled"] = change.map(
        lambda value: np.nan
        if pd.isna(value)
        else float(np.clip((float(value) + 100.0) / 200.0, 0.0, 1.0))
    )
    result["inverse_pressure_change5_scaled"] = 1.0 - result["pressure_change5_scaled"]
    result["cross_section_pressure_dispersion_scaled"] = (
        pd.to_numeric(result["cross_section_pressure_dispersion"], errors="coerce") / 100.0
    )

    def true_share(values: dict[str, Any]) -> float:
        ordered = [values.get(segment) for segment in ("large", "mid", "tech")]
        if any(value is None for value in ordered):
            return float("nan")
        return sum(value is True for value in ordered) / 3.0

    result["segment_iv_jump_true_share"] = result["segment_iv_jump"].map(true_share)
    return result


def predictors_complete(row: dict[str, Any] | pd.Series, event_id: str) -> bool:
    for field in PREDICTOR_FIELDS[event_id]:
        value = row.get(field)
        if value is None or pd.isna(value) or not np.isfinite(float(value)):
            return False
        if not 0.0 <= float(value) <= 1.0:
            return False
    return True
