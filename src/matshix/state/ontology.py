from __future__ import annotations

from typing import Any

import pandas as pd

from matshix.logic import (
    Tri,
    at_least_k_true,
    exactly_one,
    tri,
    tri_and,
    tri_not,
    tri_or,
)


def _score(record: dict[str, Any], name: str) -> float | None:
    value = record.get("scores", {}).get(name)
    return None if value is None or pd.isna(value) else float(value)


def _score_at_least(record: dict[str, Any], name: str, threshold: float) -> Tri:
    value = _score(record, name)
    return None if value is None else value >= threshold


def _enum_equals(value: object, expected: str) -> Tri:
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return None
    return str(value) == expected


def _priority_answer(branches: list[tuple[str, Tri]], default: str) -> str:
    for answer, predicate in branches:
        if predicate is True:
            return answer
        if predicate is None:
            return "UNKNOWN"
    return default


def level_answer(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 35:
        return "CHEAP"
    if value < 60:
        return "NORMAL"
    if value < 85:
        return "RICH"
    return "EXTREME"


def shock_answer(value: float | None, hard_acute: Tri) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 40:
        return "CALM"
    if value < 65:
        return "BUILDING"
    if hard_acute is True:
        return "ACUTE"
    if hard_acute is False:
        return "HIGH"
    return "UNKNOWN"


def tail_answer(down_tail: float | None, up_tail: float | None) -> str:
    if down_tail is None or up_tail is None:
        return "UNKNOWN"
    if down_tail < 60 and up_tail < 60:
        return "NEUTRAL"
    if down_tail >= 75 and up_tail >= 75 and abs(down_tail - up_tail) < 15:
        return "TWO_SIDED_EVENT"
    if down_tail >= 60 and down_tail - up_tail >= 15:
        return "DOWNSIDE_PRICED"
    if up_tail >= 60 and up_tail - down_tail >= 15:
        return "UPSIDE_PRICED"
    return "MIXED"


def term_answer(record: dict[str, Any]) -> str:
    persistence = _score(record, "persistence")
    shock = _score(record, "shock")
    if persistence is None or shock is None:
        return "UNKNOWN"
    d5_forward = record.get("aggregate_d5_fvol30_90")
    percentile = record.get("aggregate_d5_fvol30_90_percentile")
    return _priority_answer(
        [
            ("PERSISTENT", tri(record.get("persistent_now"))),
            (
                "DIFFUSING",
                tri_and(
                    persistence >= 55,
                    None if d5_forward is None or pd.isna(d5_forward) else float(d5_forward) > 0,
                    None
                    if percentile is None or pd.isna(percentile)
                    else float(percentile) >= 0.70,
                ),
            ),
            ("FRONT_LOCALIZED", tri_and(shock >= 65, persistence < 50)),
            ("NORMAL", tri_and(persistence < 55, shock < 65)),
        ],
        "MIXED",
    )


def breadth_answer(record: dict[str, Any]) -> tuple[str, Tri]:
    metrics = record["breadth_metrics"]
    segment = metrics["segment_stressed"]
    broad = tri(metrics["broad_confirmed"])
    systemic = tri(metrics["systemic_confirmed"])
    segment_count = metrics["stressed_segment_count"]
    index_count = metrics["stressed_index_count"]
    large_only = tri_and(segment["large"], tri_not(segment["mid"]), tri_not(segment["tech"]))
    local_only = tri_and(tri_not(segment["large"]), exactly_one([segment["mid"], segment["tech"]]))
    dispersion = record.get("cross_section_pressure_dispersion")
    dispersion_fragmented = tri_and(
        None if dispersion is None or pd.isna(dispersion) else float(dispersion) >= 50,
        tri_not(broad),
    )
    axis_fragmented_values: list[Tri] = []
    for index_state in record["economic_indices"].values():
        state = index_state["state"]
        shock = state.get("shock")
        down_tail = state.get("down_tail")
        axis_fragmented_values.append(
            None
            if shock is None or down_tail is None
            else abs(float(shock) - float(down_tail)) >= 50
        )
    axis_fragmented = tri_and(tri_or(*axis_fragmented_values), tri_not(broad))
    count_fragmented: Tri = (
        None
        if segment_count is None or index_count is None
        else segment_count == 0 and index_count >= 2
    )
    fragmented = tri_or(dispersion_fragmented, axis_fragmented, count_fragmented)
    answer = _priority_answer(
        [
            (
                "NONE",
                None
                if segment_count is None or index_count is None
                else tri_and(index_count == 0, segment_count == 0, tri_not(fragmented)),
            ),
            (
                "ISOLATED",
                None
                if segment_count is None or index_count is None
                else index_count == 1 and segment_count == 0,
            ),
            ("BLUE_CHIP_LOCALIZED", large_only),
            ("LOCAL_STYLE", local_only),
            ("SYSTEMIC", systemic),
            ("BROAD", tri_and(broad, tri_not(systemic))),
            ("FRAGMENTED", tri_and(tri_not(broad), fragmented)),
        ],
        "UNKNOWN",
    )
    return answer, fragmented


def ordered_raw_phase(record: dict[str, Any]) -> str:
    hard_acute = tri(record.get("hard_acute"))
    breadth = record["answers"]["breadth"]
    all_jump = tri(record.get("all_segment_iv_jump"))
    broad = tri(record["breadth_metrics"].get("broad_confirmed"))
    pressure = record.get("pressure_score")
    down_tail = _score(record, "down_tail")
    up_tail = _score(record, "up_tail")
    shock = _score(record, "shock")
    repair = record["answers"]["repair"]
    tail = record["answers"]["tail"]
    aggregate_return = record.get("aggregate_etf_return_5d")
    aggregate_vrp = record.get("aggregate_vrp_value")
    systemic_acute = tri_and(hard_acute, _enum_equals(breadth, "SYSTEMIC"), all_jump)
    localized_acute = tri_and(hard_acute, tri_not(systemic_acute))
    calm_vrp: Tri = False
    if aggregate_vrp is not None and not pd.isna(aggregate_vrp):
        calm_vrp = tri_and(
            None if pressure is None or pd.isna(pressure) else float(pressure) < 35,
            None if shock is None else shock < 40,
            float(aggregate_vrp) > 0,
        )
    branches: list[tuple[str, Tri]] = [
        ("SYSTEMIC_ACUTE_STRESS", systemic_acute),
        ("LOCALIZED_ACUTE_STRESS", localized_acute),
        ("REPAIR_IN_PROGRESS", tri_and(_enum_equals(repair, "CONFIRMED"), tri_not(hard_acute))),
        (
            "BROAD_PERSISTENT_PRESSURE",
            tri_and(tri(record.get("persistent_now")), broad),
        ),
        (
            "BROAD_PRESSURE",
            tri_and(
                broad, None if pressure is None or pd.isna(pressure) else float(pressure) >= 65
            ),
        ),
        (
            "LOCAL_STYLE_PRESSURE",
            tri_and(
                _enum_equals(breadth, "LOCAL_STYLE"),
                None if pressure is None or pd.isna(pressure) else float(pressure) >= 55,
            ),
        ),
        (
            "BLUE_CHIP_PRESSURE",
            tri_and(
                _enum_equals(breadth, "BLUE_CHIP_LOCALIZED"),
                None if pressure is None or pd.isna(pressure) else float(pressure) >= 55,
            ),
        ),
        (
            "DOWNSIDE_TAIL_RICH",
            tri_and(
                None if down_tail is None else down_tail >= 75,
                None if shock is None else shock < 65,
                tri_not(broad),
            ),
        ),
        (
            "UPSIDE_CONVEXITY_PRICED",
            tri_and(
                _enum_equals(tail, "UPSIDE_PRICED"),
                None if up_tail is None else up_tail >= 75,
                None
                if aggregate_return is None or pd.isna(aggregate_return)
                else float(aggregate_return) > 0,
            ),
        ),
        ("FRAGMENTED_TRANSITION", _enum_equals(breadth, "FRAGMENTED")),
        ("CALM_POSITIVE_VRP", calm_vrp),
    ]
    for phase, predicate in branches:
        if predicate is True:
            return phase
        if predicate is None:
            return "UNKNOWN"
    return "BALANCED_MARKET"


def _window_at_least(values: list[Tri], end: int, width: int, k: int) -> Tri:
    window = values[max(0, end - width + 1) : end + 1]
    return at_least_k_true([None] * (width - len(window)) + window, k)


def add_state_ontology(score_history: pd.DataFrame) -> pd.DataFrame:
    records = score_history.sort_values("session_date").to_dict(orient="records")
    persistent_days = [
        tri_and(
            _score_at_least(record, "persistence", 75),
            None
            if record.get("pressure_score") is None or pd.isna(record.get("pressure_score"))
            else float(record["pressure_score"]) >= 65,
        )
        for record in records
    ]
    persistent_now = [
        _window_at_least(persistent_days, index, 5, 3) for index in range(len(records))
    ]
    hard_acute = [
        tri_and(
            _score_at_least(record, "shock", 85),
            tri(record.get("cross_market_iv_jump")),
            tri_or(
                _score_at_least(record, "down_tail", 75),
                tri(record["breadth_metrics"].get("broad_confirmed")),
            ),
        )
        for record in records
    ]
    stress_days = [
        tri_or(
            None
            if record.get("pressure_score") is None or pd.isna(record.get("pressure_score"))
            else float(record["pressure_score"]) >= 70,
            hard_acute[index],
        )
        for index, record in enumerate(records)
    ]
    recent_stress = [_window_at_least(stress_days, index, 10, 1) for index in range(len(records))]
    output: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        current = dict(record)
        current["persistent_day"] = persistent_days[index]
        current["persistent_now"] = persistent_now[index]
        current["hard_acute"] = hard_acute[index]
        current["stress_day"] = stress_days[index]
        current["recent_stress"] = recent_stress[index]
        repair = _score(current, "repair")
        previous = output[-1] if output else None
        previous_repair = None if previous is None else _score(previous, "repair")
        pressure_falling: Tri = None
        breadth_non_increasing: Tri = None
        if previous is not None:
            current_pressure = current.get("pressure_score")
            previous_pressure = previous.get("pressure_score")
            if (
                current_pressure is not None
                and previous_pressure is not None
                and not pd.isna(current_pressure)
                and not pd.isna(previous_pressure)
            ):
                pressure_falling = float(current_pressure) < float(previous_pressure)
            current_breadth = _score(current, "breadth")
            prior_breadth = _score(previous, "breadth")
            if current_breadth is not None and prior_breadth is not None:
                breadth_non_increasing = current_breadth <= prior_breadth
        repair_confirmed = tri_and(
            recent_stress[index],
            None if repair is None else repair >= 70,
            None if previous_repair is None else previous_repair >= 70,
            pressure_falling,
            breadth_non_increasing,
            tri_not(hard_acute[index]),
        )
        current["repair_confirmed"] = repair_confirmed
        breadth_value, fragmented = breadth_answer(current)
        if repair is None:
            repair_value = "UNKNOWN"
        elif repair < 60 or recent_stress[index] is False:
            repair_value = "INACTIVE"
        elif recent_stress[index] is None:
            repair_value = "UNKNOWN"
        elif repair_confirmed is True:
            repair_value = "CONFIRMED"
        elif repair_confirmed is False:
            repair_value = "BUILDING"
        else:
            repair_value = "UNKNOWN"
        current["answers"] = {
            "level": level_answer(_score(current, "insurance_level")),
            "shock": shock_answer(_score(current, "shock"), hard_acute[index]),
            "tail": tail_answer(_score(current, "down_tail"), _score(current, "up_tail")),
            "term": term_answer(current),
            "breadth": breadth_value,
            "repair": repair_value,
        }
        current["fragmented_now"] = fragmented
        pressure = current.get("pressure_score")
        if current["data_status"] != "OK" or pressure is None or pd.isna(pressure):
            current["pressure_level"] = "UNKNOWN"
            current["direction"] = "UNKNOWN"
            current["answers"] = {key: "UNKNOWN" for key in current["answers"]}
            current["raw_phase"] = "UNKNOWN"
        else:
            numeric = float(pressure)
            current["pressure_level"] = (
                "LOW"
                if numeric < 35
                else "WATCH"
                if numeric < 55
                else "ELEVATED"
                if numeric < 70
                else "HIGH"
                if numeric < 85
                else "EXTREME"
            )
            change = current.get("d5_pressure_score")
            current["direction"] = (
                "UNKNOWN"
                if change is None or pd.isna(change)
                else "RISING"
                if float(change) >= 7.5
                else "FALLING"
                if float(change) <= -7.5
                else "STABLE"
            )
            current["raw_phase"] = ordered_raw_phase(current)
        output.append(current)
    return pd.DataFrame(output)
