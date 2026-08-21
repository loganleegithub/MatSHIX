from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_midrank_percentile(
    series: pd.Series,
    *,
    reference_sessions: int = 504,
    minimum_valid: int = 252,
) -> pd.Series:
    """PIT mid-rank percentile over preceding sessions, excluding today."""

    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    result = np.full(len(values), np.nan, dtype=float)
    for position, current in enumerate(values):
        if not np.isfinite(current):
            continue
        start = max(0, position - reference_sessions)
        reference = values[start:position]
        valid = reference[np.isfinite(reference)]
        if len(valid) < minimum_valid:
            continue
        less = int(np.count_nonzero(valid < current))
        equal = int(np.count_nonzero(valid == current))
        result[position] = (less + 0.5 * equal) / len(valid)
    return pd.Series(result, index=series.index, dtype=float)
