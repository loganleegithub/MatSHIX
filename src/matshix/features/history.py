from __future__ import annotations

import math

import numpy as np
import pandas as pd

from matshix.features.percentile import rolling_midrank_percentile

PERCENTILE_TRANSFORMS: dict[str, tuple[str, float]] = {
    "p_iv30": ("iv30_mf", 1.0),
    "p_d1_log_iv30": ("d1_log_iv30", 1.0),
    "p_d5_log_iv30": ("d5_log_iv30", 1.0),
    "p_iv_vol_of_vol20": ("iv_vol_of_vol20", 1.0),
    "p_neg_etf_return_1d": ("etf_return_1d", -1.0),
    "p_down_skew25": ("down_skew25", 1.0),
    "p_d5_down_skew25": ("d5_down_skew25", 1.0),
    "p_up_skew25": ("up_skew25", 1.0),
    "p_d5_up_skew25": ("d5_up_skew25", 1.0),
    "p_fvol_30_90": ("fvol_30_90", 1.0),
    "p_iv90": ("iv90_mf", 1.0),
    "p_d5_fvol_30_90": ("d5_fvol_30_90", 1.0),
    "p_term_log_ratio_30_90": ("term_log_ratio_30_90", 1.0),
    "p_neg_d5_log_iv30": ("d5_log_iv30", -1.0),
    "p_neg_d5_down_skew25": ("d5_down_skew25", -1.0),
    "p_neg_d5_fvol_30_90": ("d5_fvol_30_90", -1.0),
    "p_etf_return_5d": ("etf_return_5d", 1.0),
    "p_neg_d5_iv_vol_of_vol20": ("d5_iv_vol_of_vol20", -1.0),
    "p_vrp": ("vrp_ewma94", 1.0),
}


def _add_returns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    grouped = result.groupby("economic_index_id", sort=False)
    result["etf_return_1d"] = grouped["tr_mark"].transform(
        lambda values: np.log(values / values.shift(1))
    )
    result["etf_return_5d"] = grouped["tr_mark"].transform(
        lambda values: np.log(values / values.shift(5))
    )
    return result


def _add_iv_changes(frame: pd.DataFrame, *, vov_max_span_sessions: int) -> pd.DataFrame:
    result = frame.copy()
    grouped = result.groupby("economic_index_id", sort=False)
    result["d1_log_iv30"] = grouped["iv30_mf"].transform(
        lambda values: np.log(values / values.shift(1))
    )
    result["d5_log_iv30"] = grouped["iv30_mf"].transform(
        lambda values: np.log(values / values.shift(5))
    )
    for field in ("down_skew25", "up_skew25", "fvol_30_90"):
        result[f"d5_{field}"] = grouped[field].transform(lambda values: values - values.shift(5))
    result["iv_vol_of_vol20"] = np.nan
    result["iv_vov_observation_span_sessions"] = np.nan
    for positions in result.groupby("economic_index_id", sort=False).groups.values():
        ordered = list(positions)
        valid: list[tuple[int, float]] = []
        for local_position, frame_position in enumerate(ordered):
            value = result.at[frame_position, "d1_log_iv30"]
            valid = [
                item for item in valid if item[0] >= local_position - (vov_max_span_sessions - 1)
            ]
            if value is None or not np.isfinite(value):
                continue
            valid.append((local_position, float(value)))
            if len(valid) >= 20:
                selected = valid[-20:]
                result.at[frame_position, "iv_vol_of_vol20"] = float(
                    np.std([item[1] for item in selected], ddof=1) * math.sqrt(252.0)
                )
                result.at[frame_position, "iv_vov_observation_span_sessions"] = (
                    selected[-1][0] - selected[0][0] + 1
                )
    result["d5_iv_vol_of_vol20"] = grouped["iv_vol_of_vol20"].transform(
        lambda values: values - values.shift(5)
    )
    return result


def _add_vrp(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["ewma_variance"] = np.nan
    result["rv_forecast30"] = np.nan
    result["vrp_ewma94"] = np.nan
    for _, positions in result.groupby("economic_index_id", sort=False).groups.items():
        buffer: list[float] = []
        variance: float | None = None
        for position in positions:
            value = result.at[position, "etf_return_1d"]
            if value is None or not np.isfinite(value):
                buffer = []
                variance = None
                continue
            numeric = float(value)
            if variance is None:
                buffer.append(numeric)
                if len(buffer) < 252:
                    continue
                if len(buffer) > 252:
                    raise RuntimeError("EWMA initialization exceeded 252 contiguous returns")
                variance = float(np.var(np.asarray(buffer), ddof=1))
            else:
                variance = 0.94 * variance + 0.06 * numeric * numeric
            result.at[position, "ewma_variance"] = variance
            result.at[position, "rv_forecast30"] = 252.0 * variance
            iv30 = result.at[position, "iv30_mf"]
            if iv30 is not None and np.isfinite(iv30) and float(iv30) > 0:
                result.at[position, "vrp_ewma94"] = (float(iv30) / 100.0) ** 2 - 252.0 * variance
    return result


def build_index_feature_history(
    surfaces: pd.DataFrame,
    etf_marks: pd.DataFrame,
    *,
    reference_sessions: int = 504,
    minimum_valid: int = 252,
    vov_max_span_sessions: int = 80,
) -> pd.DataFrame:
    required_surface = {
        "session_date",
        "carrier_id",
        "economic_index_id",
        "surface_status",
        "iv30_mf",
        "iv90_mf",
        "fvol_30_90",
        "term_log_ratio_30_90",
        "down_skew25",
        "up_skew25",
    }
    missing = required_surface - set(surfaces.columns)
    if missing:
        raise ValueError(f"surface history missing fields: {sorted(missing)}")
    marks = etf_marks.loc[:, ["session_date", "carrier_id", "etf_mark", "tr_mark"]].copy()
    result = surfaces.merge(
        marks,
        on=["session_date", "carrier_id"],
        how="left",
        validate="one_to_one",
    )
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.normalize()
    result = result.sort_values(["economic_index_id", "session_date"], kind="stable").reset_index(
        drop=True
    )
    result = _add_returns(result)
    result = _add_iv_changes(result, vov_max_span_sessions=vov_max_span_sessions)
    result = _add_vrp(result)
    for output, (source, sign) in PERCENTILE_TRANSFORMS.items():
        result[output] = np.nan
        for positions in result.groupby("economic_index_id", sort=False).groups.values():
            index = list(positions)
            transformed = sign * pd.to_numeric(result.loc[index, source], errors="coerce")
            result.loc[index, output] = rolling_midrank_percentile(
                transformed,
                reference_sessions=reference_sessions,
                minimum_valid=minimum_valid,
            ).to_numpy()
    result["vrp_percentile"] = result["p_vrp"]
    result["insurance_compensation"] = np.select(
        [result["vrp_percentile"] < 0.35, result["vrp_percentile"] >= 0.75],
        ["THIN", "RICH"],
        default="NORMAL",
    )
    result.loc[result["vrp_percentile"].isna(), "insurance_compensation"] = "UNKNOWN"
    result["front_event_premium"] = np.nan
    return result.sort_values(["session_date", "economic_index_id"], kind="stable").reset_index(
        drop=True
    )
