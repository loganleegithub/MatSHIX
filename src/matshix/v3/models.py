from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from matshix.features.percentile import rolling_midrank_percentile
from matshix.v3.authority import (
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    CHALLENGER_FEATURES,
    HAR_FEATURES,
    HORIZON_SESSIONS,
    TRADING_DAYS_PER_YEAR,
)


def _daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.sort_values("session_date", kind="stable").reset_index(drop=True).copy()
    variance = pd.to_numeric(frame["daily_total_variance"], errors="coerce")
    lagged = variance.shift(1)
    frame["log_rv_d1_lag1"] = np.log((252.0 * lagged).clip(lower=1e-12))
    frame["log_mean_rv_d5_lag1"] = np.log(
        (252.0 * lagged.rolling(5, min_periods=5).mean()).clip(lower=1e-12)
    )
    frame["log_mean_rv_d22_lag1"] = np.log(
        (252.0 * lagged.rolling(22, min_periods=22).mean()).clip(lower=1e-12)
    )

    state_values: list[float] = []
    state: float | None = None
    for value in variance.to_numpy(dtype=float):
        if np.isfinite(value) and value > 0:
            state = value if state is None else 0.94 * state + 0.06 * value
        state_values.append(math.nan if state is None else state)
    ewma_state = pd.Series(state_values, index=frame.index, dtype=float)
    prior_input_valid = lagged.notna() & lagged.gt(0)
    frame["p_b1_ewma94_variance_h20"] = (252.0 * ewma_state.shift(1)).where(prior_input_valid)
    return frame[
        [
            "session_date",
            *HAR_FEATURES,
            "p_b1_ewma94_variance_h20",
        ]
    ].rename(columns={"session_date": "forecast_session"})


def build_model_frame(
    daily: pd.DataFrame,
    outcomes: pd.DataFrame,
    q: pd.DataFrame,
) -> pd.DataFrame:
    q_fields = q[
        [
            "forecast_session",
            "q_status",
            "q_variance_h20",
            "q_total_variance_h20",
            "target_year_fraction",
            "q_known_at" if "q_known_at" in q.columns else "known_at",
            "q_method" if "q_method" in q.columns else "method",
            "evidence_tier",
        ]
    ].copy()
    q_fields = q_fields.rename(
        columns={
            "known_at": "q_known_at",
            "method": "q_method",
            "evidence_tier": "q_evidence_tier",
        }
    )
    frame = outcomes.merge(
        _daily_features(daily),
        on="forecast_session",
        how="left",
        validate="one_to_one",
    )
    frame = frame.merge(q_fields, on="forecast_session", how="left", validate="one_to_one")
    q_total_variance = pd.to_numeric(frame["q_total_variance_h20"], errors="coerce")
    frame["log_q_total_variance_h20"] = np.log(q_total_variance).where(
        q_total_variance.gt(0)
    )
    frame["authority_version"] = AUTHORITY_VERSION
    frame["authority_sha256"] = AUTHORITY_SHA256
    frame["physical_model"] = "P_PRIMARY_HAR"
    frame["challenger_model"] = "P_HAR_Q_CHALLENGER"
    return frame.sort_values("forecast_session", kind="stable").reset_index(drop=True)


def _prepare_design(
    training: pd.DataFrame,
    current: pd.Series,
    features: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray] | None:
    design = training.loc[:, list(features)].apply(pd.to_numeric, errors="coerce")
    medians = design.median(axis=0, skipna=True)
    if medians.isna().any():
        return None
    design = design.fillna(medians)
    means = design.mean(axis=0)
    scales = design.std(axis=0, ddof=0)
    if scales.isna().any() or scales.le(0).any():
        return None
    current_values = pd.to_numeric(current.loc[list(features)], errors="coerce").fillna(medians)
    if current_values.isna().any():
        return None
    x_train = ((design - means) / scales).to_numpy(dtype=float)
    x_current = ((current_values - means) / scales).to_numpy(dtype=float).reshape(1, -1)
    if not np.isfinite(x_train).all() or not np.isfinite(x_current).all():
        return None
    return x_train, x_current


def _duan_smearing_factor(log_residuals: np.ndarray) -> float | None:
    residuals = np.asarray(log_residuals, dtype=float)
    if residuals.ndim != 1 or len(residuals) == 0 or not np.isfinite(residuals).all():
        return None
    factor = float(np.exp(residuals).mean())
    return factor if np.isfinite(factor) and factor > 0 else None


def ridge_forecast(
    training: pd.DataFrame,
    current: pd.Series,
    *,
    features: tuple[str, ...],
) -> tuple[float | None, float | None, str]:
    if len(training) < 252:
        return None, None, "INSUFFICIENT_HISTORY"
    prepared = _prepare_design(training, current, features)
    if prepared is None:
        return None, None, "UNOBSERVABLE"
    target = pd.to_numeric(training["rv_variance_h20"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(target).all() or np.any(target <= 0):
        return None, None, "UNOBSERVABLE"
    x_train, x_current = prepared
    log_target = np.log(np.maximum(target, 1e-12))
    model = Ridge(alpha=1.0)
    model.fit(x_train, log_target)
    smearing_factor = _duan_smearing_factor(log_target - model.predict(x_train))
    if smearing_factor is None:
        return None, None, "UNOBSERVABLE"
    prediction = math.exp(float(model.predict(x_current)[0])) * smearing_factor
    if not np.isfinite(prediction) or prediction <= 0:
        return None, None, "UNOBSERVABLE"
    return prediction, smearing_factor, "RETROSPECTIVE_SCORE"


def _mature_training(frame: pd.DataFrame, position: int) -> pd.DataFrame:
    current_known_at = frame.at[position, "known_at"]
    prior = frame.iloc[:position].copy()
    target = pd.to_numeric(prior["rv_variance_h20"], errors="coerce")
    available = pd.to_datetime(prior["outcome_available_at"], utc=True, errors="coerce")
    known = pd.Timestamp(current_known_at).tz_convert("UTC")
    mask = target.notna() & target.gt(0) & available.notna() & available.le(known)
    return prior.loc[mask].tail(1260)


def _mature_error_history(
    frame: pd.DataFrame,
    position: int,
    *,
    forecast_field: str,
) -> pd.Series:
    current_known_at = frame.at[position, "known_at"]
    prior = frame.iloc[:position].copy()
    actual = pd.to_numeric(prior["rv_variance_h20"], errors="coerce")
    forecast = pd.to_numeric(prior[forecast_field], errors="coerce")
    available = pd.to_datetime(prior["outcome_available_at"], utc=True, errors="coerce")
    known = pd.Timestamp(current_known_at).tz_convert("UTC")
    mask = (
        actual.notna()
        & actual.gt(0)
        & forecast.notna()
        & forecast.gt(0)
        & available.notna()
        & available.le(known)
    )
    errors = np.log(actual.loc[mask]) - np.log(forecast.loc[mask])
    return errors.tail(504)


def _set_interval(
    result: pd.DataFrame,
    position: int,
    *,
    forecast_field: str,
    low_field: str,
    high_field: str,
    status_field: str,
) -> None:
    forecast = pd.to_numeric(
        pd.Series([result.at[position, forecast_field]]), errors="coerce"
    ).iloc[0]
    if pd.isna(forecast) or float(forecast) <= 0:
        result.at[position, status_field] = "UNOBSERVABLE"
        return
    errors = _mature_error_history(result, position, forecast_field=forecast_field)
    if len(errors) < 126:
        result.at[position, status_field] = "INSUFFICIENT_INTERVAL_HISTORY"
        return
    low_error, high_error = np.quantile(errors.to_numpy(dtype=float), [0.10, 0.90])
    result.at[position, low_field] = float(forecast) * math.exp(float(low_error))
    result.at[position, high_field] = float(forecast) * math.exp(float(high_error))
    result.at[position, status_field] = "OOF_INTERVAL"


def add_physical_forecasts(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    numeric_fields = (
        "p_b0_climatology_variance_h20",
        "p_primary_variance_h20",
        "p_primary_smearing_factor_h20",
        "p_interval_low_h20",
        "p_interval_high_h20",
        "p_challenger_variance_h20",
        "p_challenger_smearing_factor_h20",
        "p_challenger_interval_low_h20",
        "p_challenger_interval_high_h20",
        "p_primary_total_variance_h20",
        "p_interval_total_low_h20",
        "p_interval_total_high_h20",
        "p_challenger_total_variance_h20",
        "p_challenger_interval_total_low_h20",
        "p_challenger_interval_total_high_h20",
        "causal_extreme_threshold_h20",
    )
    for field in numeric_fields:
        result[field] = math.nan
    result["p_model_status"] = "INSUFFICIENT_HISTORY"
    result["p_interval_status"] = "INSUFFICIENT_INTERVAL_HISTORY"
    result["p_publish_opportunity"] = False
    result["p_evaluation_opportunity"] = False
    result["is_causal_extreme"] = False
    result["challenger_model_status"] = "INSUFFICIENT_HISTORY"
    result["challenger_interval_status"] = "INSUFFICIENT_INTERVAL_HISTORY"
    result["challenger_publish_opportunity"] = False
    result["challenger_evaluation_opportunity"] = False

    for position in range(len(result)):
        current = result.iloc[position]
        training = _mature_training(result, position)
        publish_opportunity = len(training) >= 252
        observed_current = str(current.get("outcome_status")) == "OBSERVED" and pd.notna(
            current.get("rv_variance_h20")
        )
        result.at[position, "p_publish_opportunity"] = publish_opportunity
        result.at[position, "p_evaluation_opportunity"] = bool(
            publish_opportunity and observed_current
        )
        if publish_opportunity:
            climatology = pd.to_numeric(
                training.tail(504)["rv_variance_h20"], errors="coerce"
            )
            if climatology.notna().all() and climatology.gt(0).all():
                result.at[position, "p_b0_climatology_variance_h20"] = float(
                    climatology.mean()
                )
            forecast, smearing_factor, status = ridge_forecast(
                training, current, features=HAR_FEATURES
            )
            result.at[position, "p_model_status"] = status
            if forecast is not None:
                result.at[position, "p_primary_variance_h20"] = forecast
                result.at[position, "p_primary_smearing_factor_h20"] = smearing_factor
                _set_interval(
                    result,
                    position,
                    forecast_field="p_primary_variance_h20",
                    low_field="p_interval_low_h20",
                    high_field="p_interval_high_h20",
                    status_field="p_interval_status",
                )
            threshold_values = pd.to_numeric(
                training.tail(504)["rv_variance_h20"], errors="coerce"
            ).dropna()
            if len(threshold_values) >= 252:
                threshold = float(threshold_values.quantile(0.90))
                result.at[position, "causal_extreme_threshold_h20"] = threshold
                actual = pd.to_numeric(
                    pd.Series([current.get("rv_variance_h20")]), errors="coerce"
                ).iloc[0]
                result.at[position, "is_causal_extreme"] = bool(
                    pd.notna(actual) and float(actual) > threshold
                )

        exact_training = training.loc[training["q_status"].eq("OK")].copy()
        current_exact_q = current.get("q_status") == "OK" and pd.notna(
            current.get("log_q_total_variance_h20")
        )
        challenger_publish = bool(current_exact_q and len(exact_training) >= 252)
        result.at[position, "challenger_publish_opportunity"] = challenger_publish
        result.at[position, "challenger_evaluation_opportunity"] = bool(
            challenger_publish and observed_current
        )
        if current_exact_q:
            forecast, smearing_factor, status = ridge_forecast(
                exact_training,
                current,
                features=CHALLENGER_FEATURES,
            )
            result.at[position, "challenger_model_status"] = status
            if forecast is not None:
                result.at[position, "p_challenger_variance_h20"] = forecast
                result.at[position, "p_challenger_smearing_factor_h20"] = smearing_factor
                _set_interval(
                    result,
                    position,
                    forecast_field="p_challenger_variance_h20",
                    low_field="p_challenger_interval_low_h20",
                    high_field="p_challenger_interval_high_h20",
                    status_field="challenger_interval_status",
                )
        elif publish_opportunity:
            result.at[position, "challenger_model_status"] = "UNOBSERVABLE_Q"
    total_scale = HORIZON_SESSIONS / TRADING_DAYS_PER_YEAR
    for annualized_field, total_field in (
        ("p_primary_variance_h20", "p_primary_total_variance_h20"),
        ("p_interval_low_h20", "p_interval_total_low_h20"),
        ("p_interval_high_h20", "p_interval_total_high_h20"),
        ("p_challenger_variance_h20", "p_challenger_total_variance_h20"),
        ("p_challenger_interval_low_h20", "p_challenger_interval_total_low_h20"),
        ("p_challenger_interval_high_h20", "p_challenger_interval_total_high_h20"),
    ):
        result[total_field] = pd.to_numeric(result[annualized_field], errors="coerce") * total_scale
    return result


def add_qp_ledger_fields(frame: pd.DataFrame, *, p_core_passed: bool) -> pd.DataFrame:
    result = frame.copy()
    fields = (
        "qp_total_variance_premium_h20",
        "qp_total_interval_low_h20",
        "qp_total_interval_high_h20",
        "ex_post_q_total_minus_realized_h20",
    )
    for field in fields:
        result[field] = math.nan
    if not p_core_passed:
        result["qp_status"] = "NOT_APPLICABLE"
        result["qp_evidence_tier"] = "RESEARCH_QP_ESTIMATE"
        result["qp_percentile_h20"] = math.nan
        result["qp_sign_confident_h20"] = False
        result["qp_unit"] = "TOTAL_VARIANCE"
        return result

    q_total = pd.to_numeric(result["q_total_variance_h20"], errors="coerce")
    p_total = pd.to_numeric(result["p_primary_total_variance_h20"], errors="coerce")
    p_total_low = pd.to_numeric(result["p_interval_total_low_h20"], errors="coerce")
    p_total_high = pd.to_numeric(result["p_interval_total_high_h20"], errors="coerce")
    actual_total = pd.to_numeric(result["rv_total_variance_h20"], errors="coerce")
    observable = q_total.notna() & p_total.notna() & p_total_low.notna() & p_total_high.notna()
    result.loc[observable, "qp_total_variance_premium_h20"] = q_total - p_total
    result.loc[observable, "qp_total_interval_low_h20"] = q_total - p_total_high
    result.loc[observable, "qp_total_interval_high_h20"] = q_total - p_total_low
    ex_post_observable = observable & actual_total.notna()
    result.loc[ex_post_observable, "ex_post_q_total_minus_realized_h20"] = (
        q_total - actual_total
    )
    low = pd.to_numeric(result["qp_total_interval_low_h20"], errors="coerce")
    high = pd.to_numeric(result["qp_total_interval_high_h20"], errors="coerce")
    result["qp_status"] = "UNOBSERVABLE"
    result.loc[observable & low.gt(0), "qp_status"] = "THICK_COMPENSATION"
    result.loc[observable & high.lt(0), "qp_status"] = "THIN_COMPENSATION"
    result.loc[observable & low.le(0) & high.ge(0), "qp_status"] = "UNCERTAIN"
    result["qp_evidence_tier"] = "RESEARCH_QP_ESTIMATE"
    result["qp_unit"] = "TOTAL_VARIANCE"
    result["qp_percentile_h20"] = rolling_midrank_percentile(
        pd.to_numeric(result["qp_total_variance_premium_h20"], errors="coerce"),
        reference_sessions=504,
        minimum_valid=126,
    )
    result["qp_sign_confident_h20"] = observable & (low.gt(0) | high.lt(0))
    return result


def project_qp_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "forecast_session",
        "target_start_session",
        "target_end_session",
        "known_at",
        "outcome_available_at",
        "carrier_id",
        "economic_index_id",
        "horizon_sessions",
        "unit",
        "q_evidence_tier",
        "p_primary_variance_h20",
        "p_interval_low_h20",
        "p_interval_high_h20",
        "p_primary_total_variance_h20",
        "p_interval_total_low_h20",
        "p_interval_total_high_h20",
        "q_variance_h20",
        "q_total_variance_h20",
        "target_year_fraction",
        "rv_total_variance_h20",
        "qp_total_variance_premium_h20",
        "qp_total_interval_low_h20",
        "qp_total_interval_high_h20",
        "ex_post_q_total_minus_realized_h20",
        "qp_percentile_h20",
        "qp_sign_confident_h20",
        "qp_status",
        "qp_unit",
        "qp_evidence_tier",
        "authority_version",
        "authority_sha256",
    ]
    return frame.loc[:, fields].copy()


def frame_identity_payload(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(frame),
        "start_session": pd.Timestamp(frame["forecast_session"].min()).date().isoformat(),
        "end_session": pd.Timestamp(frame["forecast_session"].max()).date().isoformat(),
        "columns": list(frame.columns),
    }
