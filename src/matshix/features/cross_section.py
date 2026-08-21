from __future__ import annotations

from typing import Any

import numpy as np

from matshix.constants import ECONOMIC_WEIGHTS, INDEX_ORDER, SEGMENT_ORDER
from matshix.logic import Tri, at_least_k_true, count_if_all_known, tri_and, tri_or


def weighted_axis(values: dict[str, float | None]) -> float | None:
    if set(values) != set(INDEX_ORDER):
        raise ValueError("all four economic indices are required")
    total = 0.0
    for index in INDEX_ORDER:
        value = values[index]
        if value is None or not np.isfinite(value):
            return None
        total += ECONOMIC_WEIGHTS[index] * value
    return total


def segment_values(values: dict[str, float | None]) -> dict[str, float | None]:
    sse50 = values.get("SSE50")
    csi300 = values.get("CSI300")
    csi500 = values.get("CSI500")
    star50 = values.get("STAR50")
    return {
        "large": None
        if sse50 is None or csi300 is None
        else 0.5 * float(sse50) + 0.5 * float(csi300),
        "mid": None if csi500 is None else float(csi500),
        "tech": None if star50 is None else float(star50),
    }


def stressed_predicate(
    pressure: float | None,
    shock: float | None,
    down_tail: float | None,
    persistence: float | None,
) -> Tri:
    confirmation = tri_or(
        None if shock is None else shock >= 65,
        None if down_tail is None else down_tail >= 70,
        None if persistence is None else persistence >= 65,
    )
    return tri_and(None if pressure is None else pressure >= 65, confirmation)


def breadth_metrics(
    *,
    index_pressure: dict[str, float | None],
    index_shock: dict[str, float | None],
    index_down_tail: dict[str, float | None],
    index_persistence: dict[str, float | None],
) -> dict[str, Any]:
    index_stressed = {
        index: stressed_predicate(
            index_pressure[index],
            index_shock[index],
            index_down_tail[index],
            index_persistence[index],
        )
        for index in INDEX_ORDER
    }
    pressure = segment_values(index_pressure)
    shock = segment_values(index_shock)
    down_tail = segment_values(index_down_tail)
    persistence = segment_values(index_persistence)
    segment_stressed = {
        segment: stressed_predicate(
            pressure[segment], shock[segment], down_tail[segment], persistence[segment]
        )
        for segment in SEGMENT_ORDER
    }
    segment_list = [segment_stressed[value] for value in SEGMENT_ORDER]
    index_list = [index_stressed[value] for value in INDEX_ORDER]
    segment_count = count_if_all_known(segment_list)
    index_count = count_if_all_known(index_list)
    breadth = None if segment_count is None else 100.0 * segment_count / 3.0
    weighted = None
    if segment_count is not None:
        weighted = 100.0 * (
            0.40 * int(segment_stressed["large"] is True)
            + 0.30 * int(segment_stressed["mid"] is True)
            + 0.30 * int(segment_stressed["tech"] is True)
        )
    return {
        "index_stressed": index_stressed,
        "segment_pressure": pressure,
        "segment_shock": shock,
        "segment_down_tail": down_tail,
        "segment_persistence": persistence,
        "segment_stressed": segment_stressed,
        "stressed_segment_count": segment_count,
        "stressed_index_count": index_count,
        "broad_confirmed": at_least_k_true(segment_list, 2),
        "systemic_confirmed": at_least_k_true(segment_list, 3),
        "breadth_score": breadth,
        "weighted_breadth_score": weighted,
        "nominal_index_breadth": None if index_count is None else index_count / 4.0,
    }
