from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from matshix.constants import EVENT_IDS


@dataclass(frozen=True)
class BaseRate:
    value: float | None
    sample_size: int
    positive_count: int


def base_rate_for_position(
    ledger: pd.DataFrame,
    *,
    event_id: str,
    prediction_position: int,
    minimum_samples: int = 252,
    maximum_samples: int = 504,
) -> BaseRate:
    frame = (
        ledger.loc[
            (ledger["event_id"] == event_id)
            & (ledger["event_status"] == "ELIGIBLE")
            & (ledger["label_status"].isin(["OBSERVED_0", "OBSERVED_1"]))
            & (ledger["target_end_position"] <= prediction_position)
            & (ledger["prediction_position"] < prediction_position)
        ]
        .sort_values("prediction_position")
        .tail(maximum_samples)
    )
    count = len(frame)
    positives = int(frame["label"].sum()) if count else 0
    value = None if count < minimum_samples else (positives + 1.0) / (count + 2.0)
    return BaseRate(value, count, positives)


def _empty(event_status: str, interpretation: str) -> dict[str, Any]:
    return {
        "event_status": event_status,
        "model_status": "NOT_RUN",
        "probability_kind": None,
        "probability": None,
        "base_rate": None,
        "uplift": None,
        "target_window_end_session": None,
        "base_rate_sample_size": None,
        "base_rate_positive_count": None,
        "training_sample_size": None,
        "training_positive_count": None,
        "brier_skill": None,
        "ece": None,
        "interpretation": interpretation,
    }


def build_current_judgments(
    ledger: pd.DataFrame,
    *,
    prediction_position: int,
    accepted_models: dict[str, dict[str, Any]] | None = None,
    base_rate_minimum_samples: int = 252,
    base_rate_maximum_samples: int = 504,
) -> dict[str, dict[str, Any]]:
    accepted_models = accepted_models or {}
    output: dict[str, dict[str, Any]] = {}
    for event_id in EVENT_IDS:
        row = ledger.loc[
            (ledger["event_id"] == event_id)
            & (ledger["prediction_position"] == prediction_position)
        ].iloc[0]
        status = str(row["event_status"])
        if status == "NOT_APPLICABLE":
            output[event_id] = _empty(status, "当前状态不适用该转移问题")
            continue
        if status == "UNOBSERVABLE":
            output[event_id] = _empty(status, "当前输入不足，无法观察该问题")
            continue
        base = base_rate_for_position(
            ledger,
            event_id=event_id,
            prediction_position=prediction_position,
            minimum_samples=base_rate_minimum_samples,
            maximum_samples=base_rate_maximum_samples,
        )
        target_end = str(row["target_window_end_session"])
        if base.value is None:
            output[event_id] = {
                "event_status": "ELIGIBLE",
                "model_status": "INSUFFICIENT_HISTORY",
                "probability_kind": None,
                "probability": None,
                "base_rate": None,
                "uplift": None,
                "target_window_end_session": target_end,
                "base_rate_sample_size": base.sample_size,
                "base_rate_positive_count": base.positive_count,
                "training_sample_size": 0,
                "training_positive_count": 0,
                "brier_skill": None,
                "ece": None,
                "interpretation": "同类完整样本不足，暂不发布历史基准",
            }
            continue
        model = accepted_models.get(event_id)
        if model and model.get("accepted") and model.get("probability") is not None:
            probability = float(model["probability"])
            uplift = probability - base.value
            interpretation = (
                "特征条件概率明显高于同类历史基准"
                if uplift >= 0.10
                else "特征条件概率略高于同类历史基准"
                if uplift > 0
                else "特征条件概率低于同类历史基准"
                if uplift < 0
                else "特征条件概率与同类历史基准一致"
            )
            output[event_id] = {
                "event_status": "ELIGIBLE",
                "model_status": "CALIBRATED_MODEL",
                "probability_kind": "FEATURE_CONDITIONAL",
                "probability": probability,
                "base_rate": base.value,
                "uplift": uplift,
                "target_window_end_session": target_end,
                "base_rate_sample_size": base.sample_size,
                "base_rate_positive_count": base.positive_count,
                "training_sample_size": model.get("training_sample_size"),
                "training_positive_count": model.get("training_positive_count"),
                "brier_skill": model.get("brier_skill"),
                "ece": model.get("ece"),
                "interpretation": interpretation,
            }
        else:
            output[event_id] = {
                "event_status": "ELIGIBLE",
                "model_status": "BASE_RATE_ONLY",
                "probability_kind": "HISTORICAL_REFERENCE",
                "probability": base.value,
                "base_rate": base.value,
                "uplift": 0.0,
                "target_window_end_session": target_end,
                "base_rate_sample_size": base.sample_size,
                "base_rate_positive_count": base.positive_count,
                "training_sample_size": None
                if model is None
                else model.get("training_sample_size"),
                "training_positive_count": None
                if model is None
                else model.get("training_positive_count"),
                "brier_skill": None if model is None else model.get("brier_skill"),
                "ece": None if model is None else model.get("ece"),
                "interpretation": "当前仅显示同类历史发生率；特征模型尚无已验收增量判断",
            }
    return output


def determine_outlook(data_status: str, judgments: dict[str, dict[str, Any]]) -> str:
    if data_status != "OK":
        return "UNKNOWN"
    statuses = [judgments[event]["event_status"] for event in EVENT_IDS]
    if not any(value == "ELIGIBLE" for value in statuses) and any(
        value == "UNOBSERVABLE" for value in statuses
    ):
        return "UNKNOWN"
    if all(value == "NOT_APPLICABLE" for value in statuses):
        return "NOT_APPLICABLE"
    calibrated = [
        (event, judgments[event])
        for event in EVENT_IDS
        if judgments[event]["model_status"] == "CALIBRATED_MODEL"
    ]
    if calibrated:
        event, value = max(
            calibrated,
            key=lambda item: (float(item[1]["uplift"]), -EVENT_IDS.index(item[0])),
        )
        return event if float(value["uplift"]) >= 0.10 else "NO_STRONG_EDGE"
    if any(
        judgments[event]["event_status"] == "ELIGIBLE"
        and judgments[event]["model_status"] == "BASE_RATE_ONLY"
        for event in EVENT_IDS
    ):
        return "BASE_RATE_ONLY"
    return "UNKNOWN"
