from __future__ import annotations

from typing import Any

import pandas as pd

from matshix.calendar import add_exchange_sessions, exchange_decision_as_of
from matshix.constants import EVENT_HORIZONS, EVENT_IDS
from matshix.logic import Tri, at_least_k_true, tri, tri_and, tri_not
from matshix.probability.predictors import PREDICTOR_FIELDS, predictors_complete


def _score(row: dict[str, Any], name: str) -> float | None:
    value = row.get("scores", {}).get(name)
    return None if value is None or pd.isna(value) else float(value)


def _persistent_atomic(row: dict[str, Any]) -> Tri:
    pressure = row.get("pressure_score")
    persistence = _score(row, "persistence")
    return tri_and(
        None if pressure is None or pd.isna(pressure) else float(pressure) >= 70,
        None if persistence is None else persistence >= 70,
        tri(row.get("breadth_metrics", {}).get("broad_confirmed")),
    )


def _event_onset(row: dict[str, Any], event_id: str) -> Tri:
    shock = _score(row, "shock")
    broad = tri(row.get("breadth_metrics", {}).get("broad_confirmed"))
    if event_id == "cross_market_iv_jump_1d":
        return tri_and(
            None if shock is None else shock < 75,
            tri_not(tri(row.get("cross_market_iv_jump"))),
        )
    if event_id == "broad_pressure_onset_5d":
        return tri_not(broad)
    if event_id == "systemic_acute_stress_5d":
        phase = row.get("primary_phase")
        return None if phase in {None, "UNKNOWN"} else phase != "SYSTEMIC_ACUTE_STRESS"
    if event_id == "persistent_cross_market_stress_20d":
        return tri_not(tri(row.get("persistent_cross_market_now")))
    if event_id == "fast_repair_5d":
        repair = row.get("answers", {}).get("repair")
        if repair == "CONFIRMED":
            return False
        if repair not in {"INACTIVE", "BUILDING"}:
            return None
        pressure = row.get("pressure_score")
        pressure_condition: Tri = (
            None if pressure is None or pd.isna(pressure) else float(pressure) >= 65
        )
        phase = row.get("primary_phase")
        phase_condition: Tri = (
            None
            if phase in {None, "UNKNOWN"}
            else phase
            in {
                "SYSTEMIC_ACUTE_STRESS",
                "LOCALIZED_ACUTE_STRESS",
                "BROAD_PERSISTENT_PRESSURE",
                "BROAD_PRESSURE",
                "LOCAL_STYLE_PRESSURE",
                "BLUE_CHIP_PRESSURE",
            }
        )
        if pressure_condition is True or phase_condition is True:
            return True
        if pressure_condition is False and phase_condition is False:
            return False
        return None
    raise ValueError(event_id)


def _target_predicate(row: dict[str, Any], event_id: str) -> Tri:
    if event_id == "cross_market_iv_jump_1d":
        shock = _score(row, "shock")
        return tri_and(
            tri(row.get("cross_market_iv_jump")),
            None if shock is None else shock >= 75,
        )
    if event_id == "broad_pressure_onset_5d":
        pressure = row.get("pressure_score")
        return tri_and(
            tri(row.get("breadth_metrics", {}).get("broad_confirmed")),
            None if pressure is None or pd.isna(pressure) else float(pressure) >= 65,
        )
    if event_id == "systemic_acute_stress_5d":
        phase = row.get("primary_phase")
        return None if phase in {None, "UNKNOWN"} else phase == "SYSTEMIC_ACUTE_STRESS"
    if event_id == "persistent_cross_market_stress_20d":
        return tri(row.get("persistent_cross_market_day"))
    if event_id == "fast_repair_5d":
        return tri(row.get("repair_confirmed"))
    raise ValueError(event_id)


def _window_label(rows: list[dict[str, Any]], event_id: str) -> Tri:
    predicates = [_target_predicate(row, event_id) for row in rows]
    if event_id != "persistent_cross_market_stress_20d":
        if any(value is True for value in predicates):
            return True
        if all(value is False for value in predicates):
            return False
        return None
    windows = [
        at_least_k_true(predicates[index - 4 : index + 1], 3) for index in range(4, len(predicates))
    ]
    if any(value is True for value in windows):
        return True
    if windows and all(value is False for value in windows):
        return False
    return None


def build_target_ledger(history: pd.DataFrame) -> pd.DataFrame:
    records = history.sort_values("session_date").to_dict(orient="records")
    atomic = [_persistent_atomic(row) for row in records]
    persistent_now = [
        at_least_k_true([None] * max(0, 4 - index) + atomic[max(0, index - 4) : index + 1], 3)
        for index in range(len(records))
    ]
    for row, day, current in zip(records, atomic, persistent_now, strict=True):
        row["persistent_cross_market_day"] = day
        row["persistent_cross_market_now"] = current
    output: list[dict[str, Any]] = []
    for index, row in enumerate(records):
        prediction = pd.Timestamp(row["session_date"]).normalize()
        for event_id in EVENT_IDS:
            horizon = EVENT_HORIZONS[event_id]
            observable = row.get("data_status") == "OK" and predictors_complete(row, event_id)
            onset = _event_onset(row, event_id) if observable else None
            event_status = (
                "UNOBSERVABLE"
                if not observable or onset is None
                else "NOT_APPLICABLE"
                if onset is False
                else "ELIGIBLE"
            )
            target_end = add_exchange_sessions(prediction, horizon)
            future = records[index + 1 : index + horizon + 1]
            expected_dates = [
                add_exchange_sessions(prediction, step) for step in range(1, horizon + 1)
            ]
            actual_dates = [pd.Timestamp(value["session_date"]).normalize() for value in future]
            complete_window = len(future) == horizon and actual_dates == expected_dates
            label_status = "CENSORED"
            label: int | None = None
            if event_status == "NOT_APPLICABLE":
                label_status = "NOT_APPLICABLE"
            elif event_status == "ELIGIBLE" and complete_window:
                truth = _window_label(future, event_id)
                if truth is True:
                    label_status = "OBSERVED_1"
                    label = 1
                elif truth is False:
                    label_status = "OBSERVED_0"
                    label = 0
            record = {
                "prediction_date": prediction,
                "prediction_position": index,
                "decision_as_of": exchange_decision_as_of(prediction).isoformat(),
                "event_id": event_id,
                "horizon": horizon,
                "event_status": event_status,
                "onset": onset,
                "target_window_end_session": target_end.date().isoformat()
                if event_status == "ELIGIBLE"
                else None,
                "target_end_position": index + horizon,
                "label_status": label_status,
                "label": label,
                "outcome_available_at": exchange_decision_as_of(target_end).isoformat()
                if label_status in {"OBSERVED_0", "OBSERVED_1"}
                else None,
                "evidence_tier": "RESEARCH_ONLY",
            }
            for field in PREDICTOR_FIELDS[event_id]:
                record[field] = row.get(field)
            output.append(record)
    return pd.DataFrame(output)
