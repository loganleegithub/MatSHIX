from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ExpiryMeasure:
    expiry: str
    year_fraction: float
    variance: float

    @property
    def dte(self) -> float:
        return self.year_fraction * 365.0


@dataclass(frozen=True)
class TenorResult:
    target_days: int
    variance: float | None
    lower_expiry: str | None
    upper_expiry: str | None
    issue: str | None

    @property
    def iv_percent(self) -> float | None:
        return None if self.variance is None else 100.0 * math.sqrt(self.variance)


def interpolate_total_variance(
    measures: list[ExpiryMeasure], *, target_days: int, minimum_expiry_dte: float = 7.0
) -> TenorResult:
    eligible = sorted(
        [value for value in measures if value.dte > minimum_expiry_dte and value.variance > 0],
        key=lambda value: value.year_fraction,
    )
    lower: ExpiryMeasure | None = None
    upper: ExpiryMeasure | None = None
    for value in eligible:
        if value.dte <= target_days:
            lower = value
        elif lower is not None:
            upper = value
            break
    if lower is None or upper is None or upper.year_fraction <= lower.year_fraction:
        return TenorResult(target_days, None, None, None, "UNBRACKETED_TENOR")
    target = target_days / 365.0
    lower_weight = (upper.year_fraction - target) / (upper.year_fraction - lower.year_fraction)
    upper_weight = 1.0 - lower_weight
    total_variance = (
        lower_weight * lower.year_fraction * lower.variance
        + upper_weight * upper.year_fraction * upper.variance
    )
    variance = total_variance / target
    if not math.isfinite(variance) or variance <= 0:
        return TenorResult(
            target_days,
            None,
            lower.expiry,
            upper.expiry,
            "STATIC_ARBITRAGE_VIOLATION",
        )
    return TenorResult(target_days, variance, lower.expiry, upper.expiry, None)


def forward_variance_30_90(
    iv30_percent: float | None, iv90_percent: float | None
) -> tuple[float | None, float | None, str | None]:
    if iv30_percent is None or iv90_percent is None or min(iv30_percent, iv90_percent) <= 0:
        return None, None, "UNBRACKETED_TENOR"
    t30 = 30.0 / 365.0
    t90 = 90.0 / 365.0
    q30 = (iv30_percent / 100.0) ** 2
    q90 = (iv90_percent / 100.0) ** 2
    variance = (t90 * q90 - t30 * q30) / (t90 - t30)
    if not math.isfinite(variance) or variance < 0:
        return None, None, "NEGATIVE_FORWARD_VARIANCE"
    return variance, 100.0 * math.sqrt(variance), None
