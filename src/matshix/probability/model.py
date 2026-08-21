from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from matshix.constants import EVENT_HORIZONS, EVENT_SEEDS
from matshix.probability.calibration import (
    apply_platt,
    binary_log_loss,
    brier_score,
    exact_ece_252,
    fit_platt,
    moving_block_skill_ci,
)
from matshix.probability.predictors import PREDICTOR_FIELDS


def _artifact_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_contract_ok() -> bool:
    return version("scikit-learn") == "1.7.2"


def _new_model() -> LogisticRegression:
    return LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        fit_intercept=True,
        class_weight=None,
        tol=1e-8,
        max_iter=1500,
        random_state=0,
    )


def generate_oof_predictions(
    ledger: pd.DataFrame,
    *,
    event_id: str,
    minimum_training_samples: int = 504,
    maximum_training_samples: int = 1260,
    minimum_positive: int = 25,
    minimum_negative: int = 25,
) -> pd.DataFrame:
    event = ledger.loc[ledger["event_id"] == event_id].sort_values("prediction_position").copy()
    fields = list(PREDICTOR_FIELDS[event_id])
    output: list[dict[str, Any]] = []
    for current in event.itertuples(index=False):
        if current.event_status != "ELIGIBLE" or current.label_status not in {
            "OBSERVED_0",
            "OBSERVED_1",
        }:
            continue
        boundary = int(current.prediction_position) - EVENT_HORIZONS[event_id]
        training = event.loc[
            (event["prediction_position"] <= boundary)
            & (event["target_end_position"] <= int(current.prediction_position))
            & (event["event_status"] == "ELIGIBLE")
            & (event["label_status"].isin(["OBSERVED_0", "OBSERVED_1"]))
        ].dropna(subset=fields)
        training = training.tail(maximum_training_samples)
        positives = int(training["label"].sum())
        negatives = len(training) - positives
        if (
            len(training) < minimum_training_samples
            or positives < minimum_positive
            or negatives < minimum_negative
        ):
            continue
        model = _new_model()
        model.fit(training[fields].to_numpy(dtype=float), training["label"].to_numpy(dtype=int))
        current_x = np.asarray([[float(getattr(current, field)) for field in fields]])
        score = float(model.decision_function(current_x)[0])
        base_rows = training.tail(504)
        base_rate = (float(base_rows["label"].sum()) + 1.0) / (len(base_rows) + 2.0)
        artifact = {
            "event_id": event_id,
            "features": fields,
            "training_dates": [str(value) for value in training["prediction_date"]],
            "coef": model.coef_.tolist(),
            "intercept": model.intercept_.tolist(),
            "scikit_learn": version("scikit-learn"),
        }
        output.append(
            {
                "event_id": event_id,
                "prediction_date": current.prediction_date,
                "prediction_position": int(current.prediction_position),
                "target_end_position": int(current.target_end_position),
                "decision_score": score,
                "uncalibrated_probability": float(model.predict_proba(current_x)[0, 1]),
                "base_rate_at_prediction": base_rate,
                "label": int(current.label),
                "training_sample_size": len(training),
                "training_positive_count": positives,
                "model_artifact_id": _artifact_hash(artifact),
                "runtime_contract_ok": runtime_contract_ok(),
            }
        )
    return pd.DataFrame(output)


def sequential_calibration(oof: pd.DataFrame) -> pd.DataFrame:
    if oof.empty:
        return oof.copy()
    frame = oof.sort_values("prediction_position").reset_index(drop=True)
    output: list[dict[str, Any]] = []
    for current in frame.itertuples(index=False):
        prior = frame.loc[
            (frame["prediction_position"] < int(current.prediction_position))
            & (frame["target_end_position"] <= int(current.prediction_position))
        ].tail(252)
        positives = int(prior["label"].sum())
        negatives = len(prior) - positives
        row = current._asdict()
        row.update(
            {
                "calibration_sample_size": len(prior),
                "calibration_positive_count": positives,
                "calibration_success": False,
                "platt_a": None,
                "platt_b": None,
                "calibrated_probability": None,
            }
        )
        if len(prior) == 252 and positives >= 20 and negatives >= 20:
            result = fit_platt(prior["decision_score"].to_numpy(), prior["label"].to_numpy())
            if result.success:
                row.update(
                    {
                        "calibration_success": True,
                        "platt_a": result.a,
                        "platt_b": result.b,
                        "calibrated_probability": apply_platt(
                            float(current.decision_score), result
                        ),
                    }
                )
        output.append(row)
    return pd.DataFrame(output)


def acceptance_metrics(calibrated: pd.DataFrame, *, event_id: str) -> dict[str, Any]:
    if calibrated.empty or "calibration_success" not in calibrated.columns:
        return {"accepted": False, "samples": 0, "reason": "INSUFFICIENT_CALIBRATED_OOF"}
    frame = calibrated.loc[calibrated["calibration_success"].fillna(False)].tail(252)
    if len(frame) < 252:
        return {"accepted": False, "samples": len(frame), "reason": "INSUFFICIENT_CALIBRATED_OOF"}
    positives = int(frame["label"].sum())
    negatives = len(frame) - positives
    if positives < 20 or negatives < 20:
        return {"accepted": False, "samples": 252, "reason": "INSUFFICIENT_CLASSES"}
    labels = frame["label"].to_numpy(dtype=float)
    model = frame["calibrated_probability"].to_numpy(dtype=float)
    base = frame["base_rate_at_prediction"].to_numpy(dtype=float)
    base_brier = brier_score(labels, base)
    if base_brier <= 0:
        return {"accepted": False, "samples": 252, "reason": "ZERO_BASE_BRIER"}
    model_brier = brier_score(labels, model)
    skill = 1.0 - model_brier / base_brier
    model_logloss = binary_log_loss(labels, model)
    base_logloss = binary_log_loss(labels, base)
    ece = exact_ece_252(labels, model, frame["prediction_date"].to_numpy())
    lower, upper = moving_block_skill_ci(
        labels,
        model,
        base,
        block_length=EVENT_HORIZONS[event_id],
        seed=EVENT_SEEDS[event_id],
    )
    return {
        "accepted": bool(
            skill >= 0.02 and model_logloss <= base_logloss and ece <= 0.08 and lower > -0.02
        ),
        "samples": 252,
        "positives": positives,
        "negatives": negatives,
        "brier_model": model_brier,
        "brier_base": base_brier,
        "brier_skill": skill,
        "log_loss_model": model_logloss,
        "log_loss_base": base_logloss,
        "ece": ece,
        "bootstrap_brier_skill_90ci": [lower, upper],
    }


def fit_current_probability(
    ledger: pd.DataFrame,
    oof: pd.DataFrame,
    metrics: dict[str, Any],
    *,
    event_id: str,
    prediction_position: int,
    minimum_training_samples: int = 504,
    maximum_training_samples: int = 1260,
    minimum_positive: int = 25,
    minimum_negative: int = 25,
) -> dict[str, Any] | None:
    """Fit the current model only after its causal OOF path has passed acceptance."""

    if not metrics.get("accepted") or not runtime_contract_ok():
        return None
    fields = list(PREDICTOR_FIELDS[event_id])
    current_rows = ledger.loc[
        (ledger["event_id"] == event_id)
        & (ledger["prediction_position"] == prediction_position)
        & (ledger["event_status"] == "ELIGIBLE")
    ]
    if len(current_rows) != 1 or current_rows[fields].isna().any(axis=None):
        return None
    event = ledger.loc[
        (ledger["event_id"] == event_id)
        & (ledger["event_status"] == "ELIGIBLE")
        & (ledger["label_status"].isin(["OBSERVED_0", "OBSERVED_1"]))
        & (ledger["target_end_position"] <= prediction_position)
        & (ledger["prediction_position"] < prediction_position)
    ].dropna(subset=fields)
    training = event.sort_values("prediction_position").tail(maximum_training_samples)
    positives = int(training["label"].sum())
    negatives = len(training) - positives
    if (
        len(training) < minimum_training_samples
        or positives < minimum_positive
        or negatives < minimum_negative
    ):
        return None
    calibration = (
        oof.loc[
            (oof["prediction_position"] < prediction_position)
            & (oof["target_end_position"] <= prediction_position)
        ]
        .sort_values("prediction_position")
        .tail(252)
    )
    if len(calibration) != 252:
        return None
    calibration_positive = int(calibration["label"].sum())
    if calibration_positive < 20 or len(calibration) - calibration_positive < 20:
        return None
    platt = fit_platt(
        calibration["decision_score"].to_numpy(dtype=float),
        calibration["label"].to_numpy(dtype=float),
    )
    if not platt.success:
        return None
    model = _new_model()
    model.fit(training[fields].to_numpy(dtype=float), training["label"].to_numpy(dtype=int))
    current = current_rows.iloc[0]
    current_x = current[fields].to_numpy(dtype=float).reshape(1, -1)
    score = float(model.decision_function(current_x)[0])
    probability = apply_platt(score, platt)
    artifact = {
        "event_id": event_id,
        "features": fields,
        "training_first_date": str(training["prediction_date"].iloc[0]),
        "training_last_date": str(training["prediction_date"].iloc[-1]),
        "training_sample_size": len(training),
        "coef": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(),
        "platt_a": platt.a,
        "platt_b": platt.b,
        "scikit_learn": version("scikit-learn"),
    }
    return {
        "accepted": True,
        "probability": probability,
        "training_sample_size": len(training),
        "training_positive_count": positives,
        "brier_skill": metrics.get("brier_skill"),
        "ece": metrics.get("ece"),
        "model_artifact_id": _artifact_hash(artifact),
    }
