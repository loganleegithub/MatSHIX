from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression, Ridge

from matshix.calendar import exchange_sessions_in_range, surface_cutoff
from matshix.data.aetf import AetfPaths, extract_history
from matshix.features.history import build_index_feature_history
from matshix.features.percentile import rolling_midrank_percentile
from matshix.serialization import file_hash, write_json
from matshix.storage import write_parquet
from matshix.v2.authority import EXPECTED_LISTING_DATES
from matshix.v2.outcomes import (
    _extract_etf_minutes,
    build_daily_realized_inputs,
    build_realized_outcome_ledger,
)
from matshix.v2.provenance import repository_provenance, runtime_provenance
from matshix.v2.q_surface import _build_q_ledger, _surface_rows, enrich_outcomes_with_q

AUTHORITY_VERSION = "2.2.3"
AUTHORITY_DOCUMENT = "MATSHIX_V2_2_3_AUTHORITY.md"
AUTHORITY_SHA256 = "d47dc66aac34061d0b7287d6caa7877f3077d7f7aca1cd158b5d3805315de665"
V222_AUTHORITY_SHA256 = "5f21d1f2842ae91a0a845324b3823302f33da54a39efa9ae847b7d40b20d056b"
V222_ADJUDICATION_SHA256 = "3b834c22871a935690cca2481302d45b3809ee7f3791490c374e85ff354dc10a"
V222_FAILURE_SHA256 = "9e3db4b51c5db2b013b61c6eb0633ad232c5ed87fbe799b394bad08a822824d8"
V221_AUTHORITY_SHA256 = "eb10f33b6b45da6707fabebba9a1556854c5e52f44978d4e3f82a47f9d4886b0"
V221_ADJUDICATION_SHA256 = "7f1d629b8d77f61b484d289a3e1bf05e1a0756399294651af85003ad6136f7ac"
V221_FAILURE_SHA256 = "3e15522e4cb3a579bb610ffabf602fe97043a04e5d95c79b8f68efe13d8dcc50"
V22_AUTHORITY_SHA256 = "2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8"
V22_ADJUDICATION_SHA256 = "c4f376d3d177a95d23ad2c8cd6059c40b83b1878d13c8bd61c7a0f31a47acf6b"
V22_FAILURE_SHA256 = "a3a4350016cc4e223adda8d4f0521cf1b18536340ffbdab4f9db58f34d07938e"
PLAN_SHA256 = "effaf0f0779dc0636a5b55814bcd935a47c6085cb751752b48c56f08b30d81b8"
BASELINE_SHA256 = "f120300187c3b00b3038fbe73aa439fbc7ee03c6f3aea94a98d1f3e6dd43b6eb"
FREEZE_SHA256 = "41704acbece335b2c74e35b954d4f1358962fe4f484bf1f89f8efc3e071be64d"
PARENT_AUTHORITY_SHA256 = "03c06e4c861bd313d0502ecbc25ee1e18511c7a080b8bc2fa1fb3eaf451c0705"
PARENT_ADJUDICATION_SHA256 = "e18056289473b3979f10ae7377fc74582668e3bd394bff0b3d1e851f4446ea80"
PARENT_FAILURE_SHA256 = "3f2fe224910caf2ed24177d47c1db321cce96740c33c56c5668591cdbd236c9b"

CARRIER_ID = "CSI300_510300"
ECONOMIC_INDEX_ID = "CSI300"
DEVELOPMENT_START = pd.Timestamp("2020-01-02")
DEVELOPMENT_END = pd.Timestamp("2026-06-05")

STATE_FIELDS = (
    "common_iv_shock",
    "downside_price_shock",
    "upside_price_shock",
    "down_tail",
    "up_tail",
    "down_tail_persistence",
    "up_tail_persistence",
    "variance_repair",
    "downside_repair",
    "upside_repair",
    "term_repair",
)

VARIANCE_B2_FEATURES = (
    "log_rv_d1_lag1",
    "log_mean_rv_d5_lag1",
    "log_mean_rv_d22_lag1",
)
VARIANCE_C2_FEATURES = VARIANCE_B2_FEATURES + (
    "log_q_variance_h20",
    *STATE_FIELDS,
)


@dataclass(frozen=True)
class V22LocalArtifacts:
    ledger_path: Path
    score_path: Path
    failure_path: Path
    score: dict[str, Any]


def verify_v2_2_authority_chain(project: Path) -> dict[str, dict[str, str]]:
    expected = {
        AUTHORITY_DOCUMENT: AUTHORITY_SHA256,
        "MATSHIX_V2_2_2_AUTHORITY.md": V222_AUTHORITY_SHA256,
        "MATSHIX_V2_2_2_DEVELOPMENT_ADJUDICATION.md": V222_ADJUDICATION_SHA256,
        "MATSHIX_V2_2_2_FAILURE_LEDGER.json": V222_FAILURE_SHA256,
        "MATSHIX_V2_2_1_AUTHORITY.md": V221_AUTHORITY_SHA256,
        "MATSHIX_V2_2_1_DEVELOPMENT_ADJUDICATION.md": V221_ADJUDICATION_SHA256,
        "MATSHIX_V2_2_1_FAILURE_LEDGER.json": V221_FAILURE_SHA256,
        "MATSHIX_V2_2_AUTHORITY.md": V22_AUTHORITY_SHA256,
        "MATSHIX_V2_2_DEVELOPMENT_ADJUDICATION.md": V22_ADJUDICATION_SHA256,
        "MATSHIX_V2_2_FAILURE_LEDGER.json": V22_FAILURE_SHA256,
        "MATSHIX_V2_2_CONSTRUCTION_PLAN.md": PLAN_SHA256,
        "MATSHIX_V2_2_BASELINE_MANIFEST.json": BASELINE_SHA256,
        "MATSHIX_V2_2_FREEZE.json": FREEZE_SHA256,
        "MATSHIX_V2_1_1_AUTHORITY.md": PARENT_AUTHORITY_SHA256,
        "MATSHIX_V2_1_1_ADJUDICATION.md": PARENT_ADJUDICATION_SHA256,
        "MATSHIX_V2_1_1_FAILURE_LEDGER.json": PARENT_FAILURE_SHA256,
    }
    verified: dict[str, dict[str, str]] = {}
    for relative, digest in expected.items():
        actual = file_hash(project / relative).removeprefix("sha256:")
        if actual != digest:
            raise ValueError(
                f"frozen V2.2 chain mismatch for {relative}: expected {digest}, got {actual}"
            )
        verified[relative] = {"sha256": actual, "status": "VERIFIED"}
    return verified


def _all_finite(frame: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series:
    result = pd.Series(True, index=frame.index, dtype=bool)
    for field in fields:
        result &= pd.to_numeric(frame[field], errors="coerce").notna()
    return result


def _weighted(
    frame: pd.DataFrame,
    components: tuple[tuple[str, float], ...],
    *,
    scale: float,
) -> pd.Series:
    result = pd.Series(0.0, index=frame.index, dtype=float)
    valid = pd.Series(True, index=frame.index, dtype=bool)
    for field, weight in components:
        values = pd.to_numeric(frame[field], errors="coerce")
        result += weight * values.fillna(0.0)
        valid &= values.notna()
    return (scale * result).where(valid)


def add_local_percentiles(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    transforms = {
        "p_positive_etf_return_1d": ("etf_return_1d", 1.0),
        "p_negative_etf_return_5d": ("etf_return_5d", -1.0),
        "p_negative_d5_up_skew25": ("d5_up_skew25", -1.0),
    }
    for output, (source, sign) in transforms.items():
        values = sign * pd.to_numeric(result[source], errors="coerce")
        result[output] = rolling_midrank_percentile(
            values,
            reference_sessions=504,
            minimum_valid=126,
        )
    result["p_negative_etf_return_1d"] = result["p_neg_etf_return_1d"]
    result["p_positive_etf_return_5d"] = result["p_etf_return_5d"]
    result["p_negative_d5_log_iv30"] = result["p_neg_d5_log_iv30"]
    result["p_negative_d5_iv_vol_of_vol20"] = result["p_neg_d5_iv_vol_of_vol20"]
    result["p_negative_d5_fvol_30_90"] = result["p_neg_d5_fvol_30_90"]
    result["p_negative_d5_down_skew25"] = result["p_neg_d5_down_skew25"]
    return result


def build_local_state(features: pd.DataFrame) -> pd.DataFrame:
    result = add_local_percentiles(features)
    result["common_iv_shock"] = _weighted(
        result,
        (
            ("p_d1_log_iv30", 0.45),
            ("p_d5_log_iv30", 0.30),
            ("p_iv_vol_of_vol20", 0.25),
        ),
        scale=100.0,
    )
    downside_return = pd.to_numeric(result["p_negative_etf_return_1d"], errors="coerce")
    upside_return = pd.to_numeric(result["p_positive_etf_return_1d"], errors="coerce")
    common = pd.to_numeric(result["common_iv_shock"], errors="coerce")
    result["downside_price_shock"] = (0.60 * common + 40.0 * downside_return).where(
        common.notna() & downside_return.notna()
    )
    result["upside_price_shock"] = (0.60 * common + 40.0 * upside_return).where(
        common.notna() & upside_return.notna()
    )
    result["down_tail"] = _weighted(
        result,
        (("p_down_skew25", 0.65), ("p_d5_down_skew25", 0.35)),
        scale=100.0,
    )
    result["up_tail"] = _weighted(
        result,
        (("p_up_skew25", 0.65), ("p_d5_up_skew25", 0.35)),
        scale=100.0,
    )
    for side in ("down", "up"):
        tail = pd.to_numeric(result[f"{side}_tail"], errors="coerce")
        active = tail.ge(60.0).astype(float).where(tail.notna())
        result[f"{side}_tail_persistence"] = active.rolling(5, min_periods=5).sum() * 20.0
    result["variance_repair"] = _weighted(
        result,
        (
            ("p_negative_d5_log_iv30", 0.50),
            ("p_negative_d5_iv_vol_of_vol20", 0.30),
            ("p_negative_d5_fvol_30_90", 0.20),
        ),
        scale=100.0,
    )
    result["downside_repair"] = _weighted(
        result,
        (
            ("p_negative_d5_down_skew25", 0.50),
            ("p_positive_etf_return_5d", 0.30),
            ("p_negative_d5_iv_vol_of_vol20", 0.20),
        ),
        scale=100.0,
    )
    result["upside_repair"] = _weighted(
        result,
        (
            ("p_negative_d5_up_skew25", 0.50),
            ("p_negative_etf_return_5d", 0.30),
            ("p_negative_d5_iv_vol_of_vol20", 0.20),
        ),
        scale=100.0,
    )
    result["term_repair"] = 100.0 * pd.to_numeric(
        result["p_negative_d5_fvol_30_90"], errors="coerce"
    )
    result["state_status"] = np.where(_all_finite(result, STATE_FIELDS), "OK", "UNKNOWN")
    result["market_breadth"] = "NOT_APPLICABLE"
    result["primary_phase"] = "NOT_APPLICABLE"
    result["state_definition_version"] = AUTHORITY_VERSION
    return result


def _surface_frame(q: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "forecast_session",
        "carrier_id",
        "economic_index_id",
        "surface_status",
        "input_contracts",
        "eligible_contracts",
        "iv30_mf",
        "iv90_mf",
        "fvol_30_90",
        "term_log_ratio_30_90",
        "down_skew25",
        "up_skew25",
        "issues",
    ]
    frame = q.loc[q["horizon_sessions"].eq(20), fields].copy()
    frame = frame.rename(columns={"forecast_session": "session_date"})
    if frame.duplicated(["session_date", "carrier_id"]).any():
        raise ValueError("V2.2 local surface must be one row per carrier/session")
    return frame


def _daily_predictors(
    daily: pd.DataFrame,
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray],
) -> pd.DataFrame:
    frame = daily.loc[daily["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    frame = frame.sort_values("session_date", kind="stable").reset_index(drop=True)
    up_values: list[float] = []
    down_values: list[float] = []
    for row in frame.to_dict(orient="records"):
        session = pd.Timestamp(row["session_date"]).normalize()
        marks = path_marks.get((CARRIER_ID, session))
        prior = pd.to_numeric(pd.Series([row.get("prior_mark_1500")]), errors="coerce").iloc[0]
        if (
            str(row.get("daily_status")) != "OK"
            or marks is None
            or pd.isna(prior)
            or float(prior) <= 0
        ):
            up_values.append(math.nan)
            down_values.append(math.nan)
            continue
        ratios = np.log(np.asarray(marks, dtype=float) / float(prior))
        up_values.append(max(float(np.max(ratios)), 0.0))
        down_values.append(max(float(-np.min(ratios)), 0.0))
    frame["daily_up_move"] = up_values
    frame["daily_down_move"] = down_values
    overnight = pd.to_numeric(frame["overnight_log_return"], errors="coerce")
    frame["daily_up_overnight"] = overnight.clip(lower=0.0)
    frame["daily_down_overnight"] = (-overnight).clip(lower=0.0)
    daily_variance = pd.to_numeric(frame["daily_total_variance"], errors="coerce")
    frame["log_rv_d1_lag1"] = np.log((252.0 * daily_variance.shift(1)).clip(lower=1e-12))
    frame["log_mean_rv_d5_lag1"] = np.log(
        (252.0 * daily_variance.shift(1).rolling(5, min_periods=5).mean()).clip(lower=1e-12)
    )
    frame["log_mean_rv_d22_lag1"] = np.log(
        (252.0 * daily_variance.shift(1).rolling(22, min_periods=22).mean()).clip(lower=1e-12)
    )
    for side in ("up", "down"):
        moves = pd.to_numeric(frame[f"daily_{side}_move"], errors="coerce").shift(1)
        gaps = pd.to_numeric(frame[f"daily_{side}_overnight"], errors="coerce").shift(1)
        frame[f"past_{side}_max_move_d5_lag1"] = moves.rolling(5, min_periods=5).max()
        frame[f"past_{side}_max_move_d20_lag1"] = moves.rolling(20, min_periods=20).max()
        frame[f"past_{side}_overnight_gap_d20_lag1"] = gaps.rolling(20, min_periods=20).max()
    return frame.rename(columns={"session_date": "forecast_session"})


def _wide_q(q: pd.DataFrame) -> pd.DataFrame:
    output: pd.DataFrame | None = None
    for horizon in (10, 20):
        selected = q.loc[
            q["horizon_sessions"].eq(horizon),
            [
                "forecast_session",
                "q_horizon_status",
                "q_variance",
                "q_total_variance",
                "q_expected_move",
                "known_at",
            ],
        ].copy()
        selected = selected.rename(
            columns={
                field: f"{field}_h{horizon}"
                for field in selected.columns
                if field != "forecast_session"
            }
        )
        output = (
            selected
            if output is None
            else output.merge(selected, on="forecast_session", how="outer", validate="one_to_one")
        )
    assert output is not None
    q10 = pd.to_numeric(output["q_variance_h10"], errors="coerce")
    q20 = pd.to_numeric(output["q_variance_h20"], errors="coerce")
    exact = output["q_horizon_status_h10"].eq("OK") & output["q_horizon_status_h20"].eq("OK")
    output["q_term_log_ratio_h10_h20"] = np.log(q10 / q20).where(exact & q10.gt(0) & q20.gt(0))
    output["log_q_variance_h10"] = np.log(q10).where(q10.gt(0))
    output["log_q_variance_h20"] = np.log(q20).where(q20.gt(0))
    output["known_at"] = output["known_at_h20"]
    return output


def _wide_outcomes(outcomes: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    selected_outcomes = outcomes.loc[
        outcomes["carrier_id"].astype(str).eq(CARRIER_ID)
        & outcomes["horizon_sessions"].isin([10, 20])
    ].copy()
    selected_q = q.loc[q["horizon_sessions"].isin([10, 20])].copy()
    enriched = enrich_outcomes_with_q(selected_outcomes, selected_q)
    h10 = enriched.loc[enriched["horizon_sessions"].eq(10)].copy()
    h10 = h10[
        [
            "forecast_session",
            "target_start_session",
            "target_end_session",
            "outcome_available_at",
            "max_up_log_move_h",
            "max_down_log_move_h",
            "upside_path_breach_h",
            "downside_path_breach_h",
            "q_path_label_status",
            "label_status",
        ]
    ].rename(
        columns={
            "target_start_session": "target_start_session_h10",
            "target_end_session": "target_end_session_h10",
            "outcome_available_at": "outcome_available_at_h10",
            "max_up_log_move_h": "max_up_log_move_h10",
            "max_down_log_move_h": "max_down_log_move_h10",
            "upside_path_breach_h": "upside_path_breach_h10",
            "downside_path_breach_h": "downside_path_breach_h10",
            "q_path_label_status": "q_path_label_status_h10",
            "label_status": "label_status_h10",
        }
    )
    h20 = enriched.loc[enriched["horizon_sessions"].eq(20)].copy()
    h20 = h20[
        [
            "forecast_session",
            "target_start_session",
            "target_end_session",
            "outcome_available_at",
            "rv_variance_h",
            "label_status",
        ]
    ].rename(
        columns={
            "target_start_session": "target_start_session_h20",
            "target_end_session": "target_end_session_h20",
            "outcome_available_at": "outcome_available_at_h20",
            "rv_variance_h": "rv_variance_h20",
            "label_status": "label_status_h20",
        }
    )
    return h10.merge(h20, on="forecast_session", how="outer", validate="one_to_one")


def build_local_feature_ledger(
    q: pd.DataFrame,
    outcomes: pd.DataFrame,
    etf_marks: pd.DataFrame,
    daily: pd.DataFrame,
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray],
) -> pd.DataFrame:
    local_q = q.loc[
        q["carrier_id"].astype(str).eq(CARRIER_ID) & q["horizon_sessions"].isin([10, 20])
    ].copy()
    local_q = local_q.sort_values(
        ["forecast_session", "horizon_sessions"], kind="stable"
    ).reset_index(drop=True)
    if set(local_q["price_proxy"].astype(str)) != {"MINUTE_CLOSE_1456"}:
        raise ValueError("V2.2 historical Q must use MINUTE_CLOSE_1456 only")
    marks = etf_marks.loc[etf_marks["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    features = build_index_feature_history(
        _surface_frame(local_q),
        marks,
        reference_sessions=504,
        minimum_valid=126,
    )
    features = build_local_state(features).rename(columns={"session_date": "forecast_session"})
    daily_features = _daily_predictors(daily, path_marks)
    q_wide = _wide_q(local_q)
    outcome_wide = _wide_outcomes(outcomes, local_q)
    frame = features.merge(
        daily_features,
        on="forecast_session",
        how="left",
        validate="one_to_one",
        suffixes=("", "_daily"),
    )
    frame = frame.merge(q_wide, on="forecast_session", how="left", validate="one_to_one")
    frame = frame.merge(outcome_wide, on="forecast_session", how="left", validate="one_to_one")
    frame["carrier_id"] = CARRIER_ID
    frame["economic_index_id"] = ECONOMIC_INDEX_ID
    frame["authority_version"] = AUTHORITY_VERSION
    frame["q_definition_version"] = AUTHORITY_VERSION
    frame["physical_model_version"] = AUTHORITY_VERSION
    frame["qp_definition_version"] = AUTHORITY_VERSION
    frame["evidence_tier"] = "RESEARCH_ONLY"
    frame["development_era"] = "DEVELOPMENT_ERA"
    return frame.sort_values("forecast_session", kind="stable").reset_index(drop=True)


def _available_training(
    frame: pd.DataFrame,
    position: int,
    *,
    target: str,
    available_at: str,
) -> pd.DataFrame:
    known_at = frame.at[position, "known_at"]
    prior = frame.iloc[:position].copy()
    mask = prior[target].notna() & prior[available_at].notna()
    mask &= prior[available_at].le(known_at)
    return prior.loc[mask].tail(1260)


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
    return x_train, x_current


def _ridge_forecast(
    training: pd.DataFrame,
    current: pd.Series,
    *,
    features: tuple[str, ...],
    target: str,
) -> tuple[float | None, float | None, float | None, str]:
    if len(training) < 252:
        return None, None, None, "INSUFFICIENT_HISTORY"
    prepared = _prepare_design(training, current, features)
    if prepared is None:
        return None, None, None, "UNOBSERVABLE"
    x_train, x_current = prepared
    raw_target = pd.to_numeric(training[target], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(raw_target).all() or np.any(raw_target <= 0):
        return None, None, None, "UNOBSERVABLE"
    y = np.log(np.maximum(raw_target, 1e-12))
    model = Ridge(alpha=1.0)
    model.fit(x_train, y)
    prediction_log = float(model.predict(x_current)[0])
    fitted = model.predict(x_train)
    residuals = y - fitted
    lower_residual, upper_residual = np.quantile(residuals, [0.10, 0.90])
    return (
        math.exp(prediction_log),
        math.exp(prediction_log + float(lower_residual)),
        math.exp(prediction_log + float(upper_residual)),
        "RETROSPECTIVE_SCORE",
    )


def _logistic_score(
    training: pd.DataFrame,
    current: pd.Series,
    *,
    features: tuple[str, ...],
    target: str,
) -> tuple[float | None, str]:
    if len(training) < 252:
        return None, "INSUFFICIENT_HISTORY"
    labels = training[target].astype(bool).to_numpy(dtype=int)
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives < 20 or negatives < 20:
        return None, "INSUFFICIENT_HISTORY"
    prepared = _prepare_design(training, current, features)
    if prepared is None:
        return None, "UNOBSERVABLE"
    x_train, x_current = prepared
    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        class_weight=None,
        max_iter=2000,
    )
    model.fit(x_train, labels)
    return float(model.decision_function(x_current)[0]), "RETROSPECTIVE_SCORE"


def _path_features(side: str, *, challenger: bool) -> tuple[str, ...]:
    base = (
        "log_rv_d1_lag1",
        "log_mean_rv_d5_lag1",
        "log_mean_rv_d22_lag1",
        f"past_{side}_max_move_d5_lag1",
        f"past_{side}_max_move_d20_lag1",
        f"past_{side}_overnight_gap_d20_lag1",
    )
    if not challenger:
        return base
    repair = "upside_repair" if side == "up" else "downside_repair"
    return base + (
        "log_q_variance_h10",
        f"{side}_tail",
        f"{side}_skew25",
        f"{side}_tail_persistence",
        repair,
    )


def add_physical_scores(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    variance_columns = [
        "p_b0_variance_h20",
        "p_b1_variance_h20",
        "p_b2_variance_h20",
        "p_c2_variance_h20",
        "p_c2_interval_low_h20",
        "p_c2_interval_high_h20",
    ]
    for field in variance_columns:
        result[field] = math.nan
    result["p_variance_model_status"] = "INSUFFICIENT_HISTORY"
    result["variance_calendar_opportunity"] = False
    result["variance_horizon_input_ready"] = False
    result["variance_opportunity"] = False
    for side in ("up", "down"):
        result[f"p_{side}_b0_base_rate_h10"] = math.nan
        result[f"p_{side}_b1_raw_score_h10"] = math.nan
        result[f"p_{side}_c2_raw_score_h10"] = math.nan
        result[f"p_{side}_model_status"] = "INSUFFICIENT_HISTORY"
        result[f"{side}_path_calendar_opportunity"] = False
        result[f"{side}_path_horizon_input_ready"] = False
        result[f"{side}_path_opportunity"] = False

    for position in range(len(result)):
        current = result.iloc[position]
        variance_training = _available_training(
            result,
            position,
            target="rv_variance_h20",
            available_at="outcome_available_at_h20",
        )
        observed_current = str(current.get("label_status_h20")) == "OBSERVED" and pd.notna(
            current.get("rv_variance_h20")
        )
        calendar_opportunity = bool(len(variance_training) >= 252 and observed_current)
        result.at[position, "variance_calendar_opportunity"] = calendar_opportunity
        if len(variance_training) >= 252:
            climatology = variance_training.tail(504)
            target_values = pd.to_numeric(climatology["rv_variance_h20"], errors="coerce")
            if target_values.notna().all() and target_values.gt(0).all():
                result.at[position, "p_b0_variance_h20"] = math.exp(
                    float(np.log(target_values.to_numpy(dtype=float)).mean())
                )
            b2, _, _, _ = _ridge_forecast(
                variance_training,
                current,
                features=VARIANCE_B2_FEATURES,
                target="rv_variance_h20",
            )
            if b2 is not None:
                result.at[position, "p_b2_variance_h20"] = b2
        b1 = pd.to_numeric(pd.Series([current.get("rv_forecast30")]), errors="coerce").iloc[0]
        if pd.notna(b1) and float(b1) > 0:
            result.at[position, "p_b1_variance_h20"] = float(b1)
        c2_eligible = bool(
            current.get("q_horizon_status_h20") == "OK" and current.get("state_status") == "OK"
        )
        training_exact = variance_training.loc[
            variance_training["q_horizon_status_h20"].eq("OK")
            & variance_training["state_status"].eq("OK")
        ].copy()
        horizon_input_ready = bool(calendar_opportunity and c2_eligible)
        result.at[position, "variance_horizon_input_ready"] = horizon_input_ready
        result.at[position, "variance_opportunity"] = bool(
            horizon_input_ready and len(training_exact) >= 252
        )
        if c2_eligible:
            c2, low, high, status = _ridge_forecast(
                training_exact,
                current,
                features=VARIANCE_C2_FEATURES,
                target="rv_variance_h20",
            )
            result.at[position, "p_variance_model_status"] = status
            if c2 is not None:
                result.at[position, "p_c2_variance_h20"] = c2
                result.at[position, "p_c2_interval_low_h20"] = low
                result.at[position, "p_c2_interval_high_h20"] = high
        elif len(variance_training) >= 252:
            result.at[position, "p_variance_model_status"] = "UNOBSERVABLE"

        for side in ("up", "down"):
            label = f"{side}side_path_breach_h10"
            training = _available_training(
                result,
                position,
                target=label,
                available_at="outcome_available_at_h10",
            )
            labels = training[label].dropna().astype(bool)
            positives = int(labels.sum())
            negatives = int(len(labels) - positives)
            target_current = current.get(label)
            calendar_opportunity = bool(
                len(training) >= 252
                and positives >= 20
                and negatives >= 20
                and pd.notna(target_current)
            )
            result.at[position, f"{side}_path_calendar_opportunity"] = calendar_opportunity
            if len(training) >= 252:
                base = training.tail(504)[label].dropna().astype(bool)
                if len(base) >= 252:
                    result.at[position, f"p_{side}_b0_base_rate_h10"] = (
                        float(base.sum()) + 1.0
                    ) / (len(base) + 2.0)
                b1_score, _ = _logistic_score(
                    training,
                    current,
                    features=_path_features(side, challenger=False),
                    target=label,
                )
                if b1_score is not None:
                    result.at[position, f"p_{side}_b1_raw_score_h10"] = b1_score
            path_eligible = bool(
                current.get("q_horizon_status_h10") == "OK" and current.get("state_status") == "OK"
            )
            exact_training = training.loc[
                training["q_horizon_status_h10"].eq("OK") & training["state_status"].eq("OK")
            ].copy()
            exact_labels = exact_training[label].dropna().astype(bool)
            exact_positives = int(exact_labels.sum())
            exact_negatives = int(len(exact_labels) - exact_positives)
            horizon_input_ready = bool(calendar_opportunity and path_eligible)
            result.at[position, f"{side}_path_horizon_input_ready"] = horizon_input_ready
            result.at[position, f"{side}_path_opportunity"] = bool(
                horizon_input_ready
                and len(exact_training) >= 252
                and exact_positives >= 20
                and exact_negatives >= 20
            )
            if path_eligible:
                c2_score, status = _logistic_score(
                    exact_training,
                    current,
                    features=_path_features(side, challenger=True),
                    target=label,
                )
                result.at[position, f"p_{side}_model_status"] = status
                if c2_score is not None:
                    result.at[position, f"p_{side}_c2_raw_score_h10"] = c2_score
            elif len(training) >= 252:
                result.at[position, f"p_{side}_model_status"] = "UNOBSERVABLE"

    for side in ("up", "down"):
        raw = pd.to_numeric(result[f"p_{side}_c2_raw_score_h10"], errors="coerce")
        result[f"p_{side}_c2_score_percentile_h10"] = rolling_midrank_percentile(
            raw,
            reference_sessions=504,
            minimum_valid=126,
        )
    variance_raw = pd.to_numeric(result["p_c2_variance_h20"], errors="coerce")
    result["p_variance_hazard_percentile_h20"] = rolling_midrank_percentile(
        variance_raw,
        reference_sessions=504,
        minimum_valid=126,
    )
    return result


def _block_chunks(
    length: int,
    *,
    block_length: int,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    chunks: list[np.ndarray] = []
    selected = 0
    maximum_start = max(length - block_length, 0)
    while selected < length:
        start = int(rng.integers(0, maximum_start + 1))
        width = min(block_length, length - selected, length - start)
        chunk = np.arange(start, start + width, dtype=int)
        chunks.append(chunk)
        selected += len(chunk)
    return chunks


def _spearman(left: pd.Series, right: pd.Series) -> float | None:
    if len(left) < 3 or left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return None
    value = float(spearmanr(left.to_numpy(dtype=float), right.to_numpy(dtype=float)).statistic)
    return value if np.isfinite(value) else None


def _qlike(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    ratio = actual / forecast
    return np.asarray(ratio - np.log(ratio) - 1.0, dtype=float)


def evaluate_variance_gate(frame: pd.DataFrame) -> dict[str, Any]:
    calendar_opportunities = frame.loc[frame["variance_calendar_opportunity"].astype(bool)].copy()
    horizon_input_ready = calendar_opportunities.loc[
        calendar_opportunities["variance_horizon_input_ready"].astype(bool)
    ].copy()
    opportunities = frame.loc[frame["variance_opportunity"].astype(bool)].copy()
    eligible = opportunities.loc[
        pd.to_numeric(opportunities["p_c2_variance_h20"], errors="coerce").notna()
    ].copy()
    coverage = len(eligible) / len(opportunities) if len(opportunities) else 0.0
    input_availability = (
        len(horizon_input_ready) / len(calendar_opportunities)
        if len(calendar_opportunities)
        else 0.0
    )
    paired_fields = (
        "rv_variance_h20",
        "p_c2_variance_h20",
        "p_b1_variance_h20",
        "p_b2_variance_h20",
        "p_c2_interval_low_h20",
        "p_c2_interval_high_h20",
    )
    paired = opportunities.loc[_all_finite(opportunities, paired_fields)].copy()
    if len(paired) < 126 or not len(opportunities):
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "VARIANCE_PAIRED_ROWS_BELOW_126",
            "calendar_opportunity_rows": len(calendar_opportunities),
            "horizon_input_ready_rows": len(horizon_input_ready),
            "raw_horizon_input_availability": input_availability,
            "opportunity_rows": len(opportunities),
            "eligible_rows": len(eligible),
            "paired_rows": len(paired),
            "eligible_coverage": coverage,
        }
    actual = pd.to_numeric(paired["rv_variance_h20"], errors="coerce").to_numpy(dtype=float)
    c2 = pd.to_numeric(paired["p_c2_variance_h20"], errors="coerce").to_numpy(dtype=float)
    b1 = pd.to_numeric(paired["p_b1_variance_h20"], errors="coerce").to_numpy(dtype=float)
    b2 = pd.to_numeric(paired["p_b2_variance_h20"], errors="coerce").to_numpy(dtype=float)
    c2_loss = float(_qlike(actual, c2).mean())
    b1_loss = float(_qlike(actual, b1).mean())
    b2_loss = float(_qlike(actual, b2).mean())
    skill = 1.0 - c2_loss / min(b1_loss, b2_loss)
    rng = np.random.default_rng(2026082301)
    bootstrap: list[float] = []
    for _ in range(2000):
        positions = np.concatenate(_block_chunks(len(paired), block_length=20, rng=rng))
        sample_actual = actual[positions]
        sample_c2 = c2[positions]
        sample_b1 = b1[positions]
        sample_b2 = b2[positions]
        denominator = min(
            float(_qlike(sample_actual, sample_b1).mean()),
            float(_qlike(sample_actual, sample_b2).mean()),
        )
        if denominator > 0:
            bootstrap.append(1.0 - float(_qlike(sample_actual, sample_c2).mean()) / denominator)
    lower = float(np.quantile(bootstrap, 0.05)) if bootstrap else None
    bias = abs(float((c2.mean() - actual.mean()) / actual.mean()))
    low = pd.to_numeric(paired["p_c2_interval_low_h20"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(paired["p_c2_interval_high_h20"], errors="coerce").to_numpy(dtype=float)
    interval_coverage = float(((actual >= low) & (actual <= high)).mean())
    passed = bool(
        skill >= 0.02
        and lower is not None
        and lower > 0.0
        and bias <= 0.20
        and 0.65 <= interval_coverage <= 0.95
        and coverage >= 0.70
        and np.isfinite(c2).all()
        and np.all(c2 > 0)
    )
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "FROZEN_VARIANCE_GATES_PASSED" if passed else "FROZEN_VARIANCE_GATE_FAILED",
        "calendar_opportunity_rows": len(calendar_opportunities),
        "horizon_input_ready_rows": len(horizon_input_ready),
        "raw_horizon_input_availability": input_availability,
        "opportunity_rows": len(opportunities),
        "eligible_rows": len(eligible),
        "paired_rows": len(paired),
        "eligible_coverage": coverage,
        "paired_qlike_skill": skill,
        "bootstrap_skill_lower_90": lower,
        "normalized_bias_abs": bias,
        "interval_80_empirical_coverage": interval_coverage,
        "qlike": {"c2": c2_loss, "b1": b1_loss, "b2": b2_loss},
    }


def _positive_clusters(frame: pd.DataFrame, *, label: str) -> dict[int, int]:
    positive = frame.loc[frame[label].fillna(False).astype(bool)].copy()
    positive = positive.sort_values(
        ["target_start_session_h10", "target_end_session_h10"], kind="stable"
    )
    clusters: dict[int, int] = {}
    cluster_id = -1
    cluster_end: pd.Timestamp | None = None
    for index, row in positive.iterrows():
        start = pd.Timestamp(row["target_start_session_h10"])
        end = pd.Timestamp(row["target_end_session_h10"])
        if cluster_end is None or start > cluster_end:
            cluster_id += 1
            cluster_end = end
        else:
            cluster_end = max(cluster_end, end)
        clusters[int(index)] = cluster_id
    return clusters


def _capture_counts(frame: pd.DataFrame, *, side: str) -> tuple[int, int]:
    label = f"{side}side_path_breach_h10"
    percentile = f"p_{side}_c2_score_percentile_h10"
    clusters = _positive_clusters(frame, label=label)
    if not clusters:
        return 0, 0
    captured: dict[int, bool] = {value: False for value in set(clusters.values())}
    for index, cluster in clusters.items():
        value = pd.to_numeric(pd.Series([frame.at[index, percentile]]), errors="coerce").iloc[0]
        if pd.notna(value) and float(value) >= 0.90:
            captured[cluster] = True
    return sum(captured.values()), len(captured)


def evaluate_path_gate(frame: pd.DataFrame, *, side: str) -> dict[str, Any]:
    label = f"{side}side_path_breach_h10"
    raw = f"p_{side}_c2_raw_score_h10"
    calendar_field = f"{side}_path_calendar_opportunity"
    input_ready_field = f"{side}_path_horizon_input_ready"
    opportunity_field = f"{side}_path_opportunity"
    calendar_opportunities = frame.loc[frame[calendar_field].astype(bool)].copy()
    horizon_input_ready = calendar_opportunities.loc[
        calendar_opportunities[input_ready_field].astype(bool)
    ].copy()
    opportunities = frame.loc[frame[opportunity_field].astype(bool)].copy()
    paired = opportunities.loc[pd.to_numeric(opportunities[raw], errors="coerce").notna()].copy()
    coverage = len(paired) / len(opportunities) if len(opportunities) else 0.0
    input_availability = (
        len(horizon_input_ready) / len(calendar_opportunities)
        if len(calendar_opportunities)
        else 0.0
    )
    positives = int(opportunities[label].fillna(False).astype(bool).sum())
    negatives = int(len(opportunities) - positives)
    if len(paired) < 126 or positives < 20 or negatives < 20:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "PATH_SAMPLE_GATE_NOT_MET",
            "side": side,
            "calendar_opportunity_rows": len(calendar_opportunities),
            "horizon_input_ready_rows": len(horizon_input_ready),
            "raw_horizon_input_availability": input_availability,
            "opportunity_rows": len(opportunities),
            "eligible_rows": len(paired),
            "eligible_coverage": coverage,
            "positives": positives,
            "negatives": negatives,
        }
    raw_values = pd.to_numeric(paired[raw], errors="coerce")
    label_values = paired[label].astype(bool).astype(int)
    correlation = _spearman(raw_values, label_values)
    captured, clusters = _capture_counts(opportunities, side=side)
    capture_rate = captured / clusters if clusters else 0.0
    capture_lift = capture_rate / 0.10

    rng = np.random.default_rng(2026082302 if side == "up" else 2026082303)
    spearman_samples: list[float] = []
    for _ in range(2000):
        positions = np.concatenate(_block_chunks(len(paired), block_length=20, rng=rng))
        sampled = paired.iloc[positions]
        value = _spearman(
            pd.to_numeric(sampled[raw], errors="coerce"),
            sampled[label].astype(bool).astype(int),
        )
        if value is not None:
            spearman_samples.append(value)
    spearman_lower = float(np.quantile(spearman_samples, 0.05)) if spearman_samples else None

    capture_rng = np.random.default_rng(2026082302 if side == "up" else 2026082303)
    lift_samples: list[float] = []
    for _ in range(2000):
        total_captured = 0
        total_clusters = 0
        for chunk in _block_chunks(len(opportunities), block_length=20, rng=capture_rng):
            chunk_frame = opportunities.iloc[chunk].reset_index(drop=True)
            chunk_captured, chunk_clusters = _capture_counts(chunk_frame, side=side)
            total_captured += chunk_captured
            total_clusters += chunk_clusters
        if total_clusters:
            lift_samples.append((total_captured / total_clusters) / 0.10)
    lift_lower = float(np.quantile(lift_samples, 0.05)) if lift_samples else None

    cluster_map = _positive_clusters(paired, label=label)
    leave_one: list[float] = []
    for cluster in sorted(set(cluster_map.values())):
        excluded = [index for index, value in cluster_map.items() if value == cluster]
        fold = paired.drop(index=excluded)
        if len(fold) < 20:
            continue
        value = _spearman(
            pd.to_numeric(fold[raw], errors="coerce"),
            fold[label].astype(bool).astype(int),
        )
        if value is not None:
            leave_one.append(value)
    leave_one_nonnegative = bool(leave_one and min(leave_one) >= 0.0)
    bootstrap_pass = bool(
        (spearman_lower is not None and spearman_lower > 0.0)
        or (lift_lower is not None and lift_lower > 1.0)
    )
    passed = bool(
        correlation is not None
        and correlation > 0.0
        and capture_lift > 1.0
        and bootstrap_pass
        and coverage >= 0.70
        and leave_one_nonnegative
    )
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "FROZEN_PATH_GATES_PASSED" if passed else "FROZEN_PATH_GATE_FAILED",
        "side": side,
        "calendar_opportunity_rows": len(calendar_opportunities),
        "horizon_input_ready_rows": len(horizon_input_ready),
        "raw_horizon_input_availability": input_availability,
        "opportunity_rows": len(opportunities),
        "eligible_rows": len(paired),
        "eligible_coverage": coverage,
        "positives": positives,
        "negatives": negatives,
        "spearman": correlation,
        "spearman_bootstrap_lower_90": spearman_lower,
        "positive_event_clusters": clusters,
        "captured_event_clusters": captured,
        "capture_lift": capture_lift,
        "capture_lift_bootstrap_lower_90": lift_lower,
        "leave_one_cluster_min_spearman": min(leave_one) if leave_one else None,
        "leave_one_cluster_folds": len(leave_one),
    }


def add_qp(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    q = pd.to_numeric(result["q_variance_h20"], errors="coerce")
    p = pd.to_numeric(result["p_c2_variance_h20"], errors="coerce")
    p_low = pd.to_numeric(result["p_c2_interval_low_h20"], errors="coerce")
    p_high = pd.to_numeric(result["p_c2_interval_high_h20"], errors="coerce")
    actual = pd.to_numeric(result["rv_variance_h20"], errors="coerce")
    result["qp_variance_premium_h20"] = q - p
    result["qp_interval_low_h20"] = q - p_high
    result["qp_interval_high_h20"] = q - p_low
    result["ex_post_q_minus_realized_h20"] = q - actual
    result["qp_percentile_h20"] = rolling_midrank_percentile(
        pd.to_numeric(result["qp_variance_premium_h20"], errors="coerce"),
        reference_sessions=504,
        minimum_valid=126,
    )
    low = pd.to_numeric(result["qp_interval_low_h20"], errors="coerce")
    high = pd.to_numeric(result["qp_interval_high_h20"], errors="coerce")
    result["qp_sign_confident_h20"] = ((low > 0) & (high > 0)) | ((low < 0) & (high < 0))
    result.loc[low.isna() | high.isna(), "qp_sign_confident_h20"] = False
    return result


def evaluate_qp_gate(frame: pd.DataFrame) -> dict[str, Any]:
    opportunities = frame.loc[frame["variance_opportunity"].astype(bool)].copy()
    paired = opportunities.loc[
        _all_finite(
            opportunities,
            ("qp_variance_premium_h20", "ex_post_q_minus_realized_h20"),
        )
    ].copy()
    coverage = len(paired) / len(opportunities) if len(opportunities) else 0.0
    if len(paired) < 126:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "QP_PAIRED_ROWS_BELOW_126",
            "opportunity_rows": len(opportunities),
            "eligible_rows": len(paired),
            "eligible_coverage": coverage,
        }
    gap = pd.to_numeric(paired["qp_variance_premium_h20"], errors="coerce")
    ex_post = pd.to_numeric(paired["ex_post_q_minus_realized_h20"], errors="coerce")
    correlation = _spearman(gap, ex_post)
    percentile = pd.to_numeric(paired["qp_percentile_h20"], errors="coerce")
    top = ex_post.loc[percentile >= 0.80]
    bottom = ex_post.loc[percentile <= 0.20]
    difference = float(top.mean() - bottom.mean()) if len(top) and len(bottom) else None
    sign_coverage = float(paired["qp_sign_confident_h20"].astype(bool).mean())

    rng = np.random.default_rng(2026082304)
    correlations: list[float] = []
    differences: list[float] = []
    for _ in range(2000):
        positions = np.concatenate(_block_chunks(len(paired), block_length=20, rng=rng))
        sampled = paired.iloc[positions]
        sample_gap = pd.to_numeric(sampled["qp_variance_premium_h20"], errors="coerce")
        sample_ex_post = pd.to_numeric(sampled["ex_post_q_minus_realized_h20"], errors="coerce")
        value = _spearman(sample_gap, sample_ex_post)
        if value is not None:
            correlations.append(value)
        sample_percentile = pd.to_numeric(sampled["qp_percentile_h20"], errors="coerce")
        sample_top = sample_ex_post.loc[sample_percentile >= 0.80]
        sample_bottom = sample_ex_post.loc[sample_percentile <= 0.20]
        if len(sample_top) and len(sample_bottom):
            differences.append(float(sample_top.mean() - sample_bottom.mean()))
    correlation_lower = float(np.quantile(correlations, 0.05)) if correlations else None
    difference_lower = float(np.quantile(differences, 0.05)) if differences else None
    bootstrap_pass = bool(
        (correlation_lower is not None and correlation_lower > 0.0)
        or (difference_lower is not None and difference_lower > 0.0)
    )
    passed = bool(
        correlation is not None
        and correlation > 0.0
        and difference is not None
        and difference > 0.0
        and bootstrap_pass
        and sign_coverage >= 0.30
        and coverage >= 0.70
    )
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "FROZEN_QP_GATES_PASSED" if passed else "FROZEN_QP_GATE_FAILED",
        "opportunity_rows": len(opportunities),
        "eligible_rows": len(paired),
        "eligible_coverage": coverage,
        "spearman": correlation,
        "top_minus_bottom": difference,
        "spearman_bootstrap_lower_90": correlation_lower,
        "top_minus_bottom_bootstrap_lower_90": difference_lower,
        "sign_confident_coverage": sign_coverage,
    }


def _engineering_gate(frame: pd.DataFrame, q: pd.DataFrame) -> dict[str, Any]:
    local_only = set(frame["carrier_id"].astype(str)) == {CARRIER_ID}
    breadth_na = set(frame["market_breadth"].astype(str)) == {"NOT_APPLICABLE"}
    phase_na = set(frame["primary_phase"].astype(str)) == {"NOT_APPLICABLE"}
    q_local = q.loc[q["carrier_id"].astype(str).eq(CARRIER_ID)]
    unavailable = q_local["q_horizon_status"].ne("OK")
    unknown_preserved = bool(q_local.loc[unavailable, "q_variance"].isna().all())
    prohibited_columns = {
        "pnl",
        "nav",
        "position",
        "leg",
        "exit",
        "strategy_return",
    }
    no_strategy_columns = not bool(prohibited_columns.intersection(map(str.lower, frame.columns)))
    state_ok_rows = int(frame["state_status"].eq("OK").sum())
    passed = bool(
        local_only
        and breadth_na
        and phase_na
        and unknown_preserved
        and no_strategy_columns
        and state_ok_rows >= 126
    )
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "LOCAL_ENGINEERING_GATES_PASSED" if passed else "LOCAL_ENGINEERING_GATE_FAILED",
        "local_carrier_only": local_only,
        "market_breadth_not_applicable": breadth_na,
        "primary_phase_not_applicable": phase_na,
        "q_unknown_preserved": unknown_preserved,
        "strategy_columns_absent": no_strategy_columns,
        "state_ok_rows": state_ok_rows,
    }


def build_and_score_development(
    q: pd.DataFrame,
    outcomes: pd.DataFrame,
    etf_marks: pd.DataFrame,
    daily: pd.DataFrame,
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ledger = build_local_feature_ledger(q, outcomes, etf_marks, daily, path_marks)
    ledger = add_physical_scores(ledger)
    engineering = _engineering_gate(ledger, q)
    variance = evaluate_variance_gate(ledger)
    upside = evaluate_path_gate(ledger, side="up")
    downside = evaluate_path_gate(ledger, side="down")
    if variance["verdict"] == "PASS":
        ledger = add_qp(ledger)
        qp = evaluate_qp_gate(ledger)
    else:
        for field in (
            "qp_variance_premium_h20",
            "qp_interval_low_h20",
            "qp_interval_high_h20",
            "ex_post_q_minus_realized_h20",
            "qp_percentile_h20",
        ):
            ledger[field] = math.nan
        ledger["qp_sign_confident_h20"] = False
        qp = {
            "verdict": "NOT_APPLICABLE",
            "reason": "P_VARIANCE_GATE_NOT_PASS",
        }
    dimensions = {
        "ENGINEERING": engineering,
        "P_VARIANCE_H20": variance,
        "P_UP_PATH_H10": upside,
        "P_DOWN_PATH_H10": downside,
        "Q_MINUS_P_H20": qp,
    }
    verdicts = [str(value["verdict"]) for value in dimensions.values()]
    if all(value == "PASS" for value in verdicts):
        development = "DEVELOPMENT_PASS"
    elif any(value == "FAIL" for value in verdicts):
        development = "DEVELOPMENT_FAIL"
    else:
        development = "INSUFFICIENT_EVIDENCE"
    score = {
        "authority_version": AUTHORITY_VERSION,
        "authority_sha256": AUTHORITY_SHA256,
        "carrier_scope": CARRIER_ID,
        "era": {
            "kind": "DEVELOPMENT_ERA",
            "start_session": DEVELOPMENT_START.date().isoformat(),
            "end_session": DEVELOPMENT_END.date().isoformat(),
            "evidence_tier": "RESEARCH_ONLY",
        },
        "development_verdict": development,
        "top_level_status": "V2_2_LOCAL_RESEARCH_BUILT"
        if engineering["verdict"] == "PASS"
        else "V2_2_LOCAL_NOT_READY",
        "dimensions": dimensions,
        "strategy_inputs_used": False,
        "formal_pit_claimed": False,
        "forward_accepted": False,
    }
    return ledger, score


def _failure_ledger(score: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for dimension, result in score["dimensions"].items():
        if result["verdict"] != "PASS":
            failures.append(
                {
                    "dimension": dimension,
                    "verdict": result["verdict"],
                    "reason": result["reason"],
                }
            )
    return {
        "failure_ledger_version": AUTHORITY_VERSION,
        "carrier_scope": CARRIER_ID,
        "development_verdict": score["development_verdict"],
        "failures": failures,
        "strategy_inputs_used": False,
    }


def build_extended_local_inputs(
    option_prices: pd.DataFrame,
    etf_marks: pd.DataFrame,
    daily: pd.DataFrame,
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    forecast_sessions = exchange_sessions_in_range(DEVELOPMENT_START, DEVELOPMENT_END)
    all_outcomes, _ = build_realized_outcome_ledger(
        daily,
        path_marks,
        forecast_sessions=forecast_sessions,
        listing_dates=EXPECTED_LISTING_DATES,
    )
    outcomes = all_outcomes.loc[
        all_outcomes["carrier_id"].astype(str).eq(CARRIER_ID)
        & all_outcomes["horizon_sessions"].isin([10, 20])
    ].copy()
    metadata = outcomes[
        [
            "forecast_session",
            "input_known_at",
            "target_start_session",
            "target_end_session",
            "carrier_id",
            "economic_index_id",
            "horizon_sessions",
            "coverage_regime",
            "available_carrier_count",
            "listing_age_sessions",
            "data_status",
        ]
    ].copy()
    local_options = option_prices.loc[option_prices["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    local_marks = etf_marks.loc[etf_marks["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    surface_rows, surfaces = _surface_rows(
        local_options,
        local_marks,
        price_proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
        methodology_version="MATSHIX_RESEARCH_MINUTE_CLOSE_V2",
        progress=None,
    )
    q = _build_q_ledger(
        metadata,
        surface_rows,
        surfaces,
        price_proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
        known_at=surface_cutoff,
        liquidity_status="RECONSTRUCTED_ASOF_CLOSE_NO_BID_ASK",
    )
    return (
        q.sort_values(["forecast_session", "horizon_sessions"], kind="stable").reset_index(
            drop=True
        ),
        outcomes.sort_values(["forecast_session", "horizon_sessions"], kind="stable").reset_index(
            drop=True
        ),
    )


def run_v2_2_local_build(*, project_dir: Path, aetf_root: Path) -> V22LocalArtifacts:
    project = project_dir.expanduser().resolve()
    authority_chain = verify_v2_2_authority_chain(project)
    paths = AetfPaths.from_root(aetf_root)
    extraction = extract_history(
        paths,
        start=DEVELOPMENT_START.date().isoformat(),
        end=DEVELOPMENT_END.date().isoformat(),
    )
    minutes = _extract_etf_minutes(paths, start=DEVELOPMENT_START, end=DEVELOPMENT_END)
    minutes = minutes.loc[minutes["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    daily, path_marks = build_daily_realized_inputs(minutes)
    q, outcomes = build_extended_local_inputs(
        extraction.option_prices,
        extraction.etf_marks,
        daily,
        path_marks,
    )
    first_ledger, first_score = build_and_score_development(
        q, outcomes, extraction.etf_marks, daily, path_marks
    )
    replay_ledger, replay_score = build_and_score_development(
        q, outcomes, extraction.etf_marks, daily, path_marks
    )
    pd.testing.assert_frame_equal(first_ledger, replay_ledger, check_exact=True)
    if first_score != replay_score:
        raise AssertionError("V2.2 local score replay mismatch")

    processed = project / "data/processed/v2_2"
    output = project / "outputs/v2_2_local"
    q_path = write_parquet(q, processed / "csi300_local_q_ledger.parquet")
    outcome_path = write_parquet(outcomes, processed / "csi300_local_outcome_ledger.parquet")
    ledger_path = write_parquet(first_ledger, processed / "csi300_local_ledger.parquet")
    score = {
        **first_score,
        "authority_chain": authority_chain,
        "repository": repository_provenance(project),
        "runtime": runtime_provenance(),
        "inputs": {
            "aetf_root": str(Path(aetf_root).expanduser().resolve()),
            "option_contracts_sha256": file_hash(paths.option_contracts),
            "aetf_readme_sha256": file_hash(paths.readme),
            "q_ledger": str(q_path.relative_to(project)),
            "q_ledger_sha256": file_hash(q_path),
            "outcome_ledger": str(outcome_path.relative_to(project)),
            "outcome_ledger_sha256": file_hash(outcome_path),
        },
        "deterministic_replay": True,
        "artifacts": {
            "ledger": str(ledger_path.relative_to(project)),
            "ledger_sha256": file_hash(ledger_path),
        },
    }
    score_path = output / "development_score.json"
    write_json(score_path, score)
    failure_path = output / "failure_ledger.json"
    write_json(failure_path, _failure_ledger(score))
    return V22LocalArtifacts(ledger_path, score_path, failure_path, score)
