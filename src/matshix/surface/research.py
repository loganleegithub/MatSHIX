from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

from matshix.calendar import expiry_timestamp, research_bar_time, year_fraction_act365f
from matshix.surface.black import forward_delta, implied_volatility
from matshix.surface.tenor import (
    ExpiryMeasure,
    TenorResult,
    forward_variance_30_90,
    interpolate_total_variance,
)

RESEARCH_SURFACE_METHOD = "MATSHIX_RESEARCH_MINUTE_CLOSE_V2"


@dataclass(frozen=True)
class ForwardEstimate:
    discount_factor: float
    forward: float
    pair_count: int


@dataclass(frozen=True)
class ResearchExpirySurface:
    expiry: str
    dte: float
    discount_factor: float | None
    forward: float | None
    parity_pair_count: int
    variance: float | None
    atm_iv: float | None
    atm_method: str
    iv_25d_put: float | None
    put25_method: str
    iv_25d_call: float | None
    call25_method: str
    valid_otm_puts: int
    valid_otm_calls: int
    valid_total_strikes: int
    issues: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchCarrierSurface:
    session_date: str
    carrier_id: str
    economic_index_id: str
    evidence_tier: str
    methodology_version: str
    surface_status: str
    input_contracts: int
    standard_contracts: int
    eligible_contracts: int
    adjusted_contracts: int
    iv30_mf: float | None
    iv30_method: str
    iv60_mf: float | None
    iv60_method: str
    iv90_mf: float | None
    iv90_method: str
    fvar_30_90: float | None
    fvol_30_90: float | None
    term_log_ratio_30_90: float | None
    atm_iv30: float | None
    atm_iv30_method: str
    iv_25d_put30: float | None
    iv_25d_put30_method: str
    iv_25d_call30: float | None
    iv_25d_call30_method: str
    rr25: float | None
    down_skew25: float | None
    up_skew25: float | None
    bf25: float | None
    wing_variance_spread: float | None
    pcr_volume: float | None
    pcr_oi: float | None
    pcr_premium: float | None
    expiries: tuple[ResearchExpirySurface, ...]
    issues: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _deduplicate_contracts(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.copy()
    values["open_interest"] = pd.to_numeric(values["open_interest"], errors="coerce").fillna(0.0)
    values["daily_volume"] = pd.to_numeric(values["daily_volume"], errors="coerce").fillna(0.0)
    values = values.sort_values(
        ["strike", "option_type", "open_interest", "daily_volume", "contract_id"],
        ascending=[True, True, False, False, True],
        kind="stable",
    )
    return values.drop_duplicates(["strike", "option_type"], keep="first")


def infer_forward_discount(
    frame: pd.DataFrame,
    *,
    spot: float,
    discount_bounds: tuple[float, float] = (0.94, 1.02),
    forward_spot_bounds: tuple[float, float] = (0.65, 1.35),
) -> ForwardEstimate:
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("ETF_MARK_MISSING")
    pivot = frame.pivot(index="strike", columns="option_type", values="price")
    if "C" not in pivot or "P" not in pivot:
        raise ValueError("PARITY_PAIR_MISSING")
    pairs = pivot.dropna(subset=["C", "P"]).copy()
    pairs = pairs.loc[
        (pairs["C"] > 0)
        & (pairs["P"] > 0)
        & (pairs.index >= forward_spot_bounds[0] * spot)
        & (pairs.index <= forward_spot_bounds[1] * spot)
    ]
    if len(pairs) < 5:
        raise ValueError("PARITY_PAIR_MISSING")
    strikes = pairs.index.to_numpy(dtype=float)
    differences = (pairs["C"] - pairs["P"]).to_numpy(dtype=float)
    slope = float(theilslopes(differences, strikes, method="joint").slope)
    discount = -slope
    if not math.isfinite(discount) or not discount_bounds[0] <= discount <= discount_bounds[1]:
        raise ValueError("PARITY_DISCOUNT_INVALID")
    forwards = strikes + differences / discount
    forward = float(np.median(forwards))
    if (
        not math.isfinite(forward)
        or not forward_spot_bounds[0] * spot <= forward <= forward_spot_bounds[1] * spot
    ):
        raise ValueError("PARITY_FORWARD_INVALID")
    return ForwardEstimate(discount, forward, len(pairs))


def _delta_k(strikes: np.ndarray) -> np.ndarray:
    if len(strikes) < 2 or np.any(np.diff(strikes) <= 0):
        raise ValueError("INSUFFICIENT_STRIKES")
    result = np.empty(len(strikes), dtype=float)
    result[0] = strikes[1] - strikes[0]
    result[-1] = strikes[-1] - strikes[-2]
    if len(strikes) > 2:
        result[1:-1] = (strikes[2:] - strikes[:-2]) / 2.0
    return result


def _model_free_variance(
    frame: pd.DataFrame,
    *,
    forward: float,
    discount_factor: float,
    year_fraction: float,
    minimum_total_strikes: int = 9,
) -> tuple[float | None, int, int, int, list[str]]:
    pivot = frame.pivot(index="strike", columns="option_type", values="price")
    paired = pivot.dropna(subset=["C", "P"])
    below = paired.index.to_numpy(dtype=float)
    below = below[below <= forward]
    if len(below) == 0:
        return None, 0, 0, 0, ["PARITY_PAIR_MISSING"]
    k0 = float(np.max(below))
    points: list[tuple[float, float, str]] = []
    for strike, row in pivot.iterrows():
        strike_value = float(strike)
        if strike_value < k0 and pd.notna(row.get("P")) and float(row["P"]) > 0:
            points.append((strike_value, float(row["P"]), "P"))
        elif strike_value > k0 and pd.notna(row.get("C")) and float(row["C"]) > 0:
            points.append((strike_value, float(row["C"]), "C"))
        elif strike_value == k0 and pd.notna(row.get("C")) and pd.notna(row.get("P")):
            call = float(row["C"])
            put = float(row["P"])
            if call > 0 and put > 0:
                points.append((strike_value, 0.5 * (call + put), "A"))
    points.sort(key=lambda value: value[0])
    put_count = sum(value[2] == "P" for value in points)
    call_count = sum(value[2] == "C" for value in points)
    total = len(points)
    issues: list[str] = []
    if put_count < 4 or call_count < 4 or total < minimum_total_strikes:
        issues.append("INSUFFICIENT_STRIKES")
        return None, put_count, call_count, total, issues
    strikes = np.asarray([value[0] for value in points], dtype=float)
    prices = np.asarray([value[1] for value in points], dtype=float)
    spacing = _delta_k(strikes)
    summation = float(np.sum(spacing / (strikes * strikes) * prices / discount_factor))
    variance = (2.0 / year_fraction) * summation - (1.0 / year_fraction) * (forward / k0 - 1.0) ** 2
    if not math.isfinite(variance) or variance <= 0:
        issues.append("STATIC_ARBITRAGE_VIOLATION")
        return None, put_count, call_count, total, issues
    return variance, put_count, call_count, total, issues


def _linear_bracket(points: list[tuple[float, float, float]], target: float) -> float | None:
    """Interpolate total variance in the first valid target bracket.

    Tuples are ``(coordinate, total_variance, log_moneyness)``.  Multiple
    brackets caused by noisy last prices are resolved by the bracket whose
    interpolated log-moneyness is closest to ATM.
    """

    ordered = sorted(points, key=lambda value: value[0])
    candidates: list[tuple[float, float]] = []
    for left, right in zip(ordered[:-1], ordered[1:], strict=True):
        if not left[0] <= target <= right[0] or right[0] == left[0]:
            continue
        weight = (target - left[0]) / (right[0] - left[0])
        variance = left[1] + weight * (right[1] - left[1])
        x = left[2] + weight * (right[2] - left[2])
        if math.isfinite(variance) and variance > 0:
            candidates.append((abs(x), variance))
    return None if not candidates else min(candidates, key=lambda value: value[0])[1]


def _smile_measures(
    frame: pd.DataFrame,
    *,
    forward: float,
    discount_factor: float,
    year_fraction: float,
    nearest_delta_max_distance: float,
    nearest_atm_log_moneyness: float,
) -> tuple[float | None, str, float | None, str, float | None, str, list[str]]:
    points: list[tuple[float, float, float, str]] = []
    for row in frame.itertuples(index=False):
        strike = float(row.strike)
        kind = str(row.option_type)
        if strike < forward and kind != "P":
            continue
        if strike > forward and kind != "C":
            continue
        try:
            sigma = implied_volatility(
                option_type=kind,
                price=float(row.price),
                forward=forward,
                strike=strike,
                year_fraction=year_fraction,
                discount_factor=discount_factor,
            )
        except ValueError:
            continue
        x = math.log(strike / forward)
        delta = forward_delta(
            option_type=kind,
            forward=forward,
            strike=strike,
            sigma=sigma,
            year_fraction=year_fraction,
        )
        points.append((x, year_fraction * sigma * sigma, delta, kind))
    issues: list[str] = []
    left = [(value[0], value[1], value[0]) for value in points if value[0] <= 0]
    right = [(value[0], value[1], value[0]) for value in points if value[0] >= 0]
    atm_variance: float | None = None
    if left and right:
        left_value = max(left, key=lambda value: value[0])
        right_value = min(right, key=lambda value: value[0])
        if right_value[0] == left_value[0]:
            atm_variance = left_value[1]
        else:
            weight = -left_value[0] / (right_value[0] - left_value[0])
            atm_variance = left_value[1] + weight * (right_value[1] - left_value[1])
    atm_method = "MONEYNESS_INTERPOLATION" if atm_variance is not None else "UNAVAILABLE"
    if atm_variance is None and points:
        nearest_atm = min(points, key=lambda value: abs(value[0]))
        if abs(nearest_atm[0]) <= nearest_atm_log_moneyness:
            atm_variance = nearest_atm[1]
            atm_method = "NEAREST_MONEYNESS_PROXY"
    put_points = [(value[2], value[1], value[0]) for value in points if value[3] == "P"]
    call_points = [(value[2], value[1], value[0]) for value in points if value[3] == "C"]
    put_variance = _linear_bracket(put_points, -0.25)
    call_variance = _linear_bracket(call_points, 0.25)
    put_method = "DELTA_INTERPOLATION" if put_variance is not None else "UNAVAILABLE"
    call_method = "DELTA_INTERPOLATION" if call_variance is not None else "UNAVAILABLE"
    if put_variance is None and put_points:
        nearest_put = min(put_points, key=lambda value: abs(value[0] + 0.25))
        if abs(nearest_put[0] + 0.25) <= nearest_delta_max_distance:
            put_variance = nearest_put[1]
            put_method = "NEAREST_DELTA_PROXY"
    if call_variance is None and call_points:
        nearest_call = min(call_points, key=lambda value: abs(value[0] - 0.25))
        if abs(nearest_call[0] - 0.25) <= nearest_delta_max_distance:
            call_variance = nearest_call[1]
            call_method = "NEAREST_DELTA_PROXY"
    if atm_variance is None:
        issues.append("ATM_NOT_BRACKETED")
    if put_variance is None or call_variance is None:
        issues.append("DELTA_NOT_BRACKETED")

    def to_iv(total_variance: float | None) -> float | None:
        if total_variance is None or total_variance <= 0:
            return None
        return 100.0 * math.sqrt(total_variance / year_fraction)

    return (
        to_iv(atm_variance),
        atm_method,
        to_iv(put_variance),
        put_method,
        to_iv(call_variance),
        call_method,
        issues,
    )


def build_expiry_surface(
    frame: pd.DataFrame,
    *,
    session_date: str,
    expiry: str,
    spot: float,
    minimum_total_strikes: int = 9,
    nearest_delta_max_distance: float = 0.12,
    nearest_atm_log_moneyness: float = 0.08,
    observation_time: datetime | None = None,
) -> ResearchExpirySurface:
    cutoff = observation_time or research_bar_time(session_date)
    year_fraction = year_fraction_act365f(cutoff, expiry_timestamp(expiry))
    dte = year_fraction * 365.0
    if year_fraction <= 0:
        return ResearchExpirySurface(
            expiry=expiry,
            dte=dte,
            discount_factor=None,
            forward=None,
            parity_pair_count=0,
            variance=None,
            atm_iv=None,
            atm_method="UNAVAILABLE",
            iv_25d_put=None,
            put25_method="UNAVAILABLE",
            iv_25d_call=None,
            call25_method="UNAVAILABLE",
            valid_otm_puts=0,
            valid_otm_calls=0,
            valid_total_strikes=0,
            issues=("EXPIRED_CONTRACT",),
        )
    clean = frame.loc[
        np.isfinite(pd.to_numeric(frame["price"], errors="coerce"))
        & (pd.to_numeric(frame["price"], errors="coerce") > 0)
    ].copy()
    clean = _deduplicate_contracts(clean)
    issues: list[str] = []
    try:
        estimate = infer_forward_discount(clean, spot=spot)
    except ValueError as exc:
        return ResearchExpirySurface(
            expiry=expiry,
            dte=dte,
            discount_factor=None,
            forward=None,
            parity_pair_count=0,
            variance=None,
            atm_iv=None,
            atm_method="UNAVAILABLE",
            iv_25d_put=None,
            put25_method="UNAVAILABLE",
            iv_25d_call=None,
            call25_method="UNAVAILABLE",
            valid_otm_puts=0,
            valid_otm_calls=0,
            valid_total_strikes=0,
            issues=(str(exc),),
        )
    variance, put_count, call_count, total, variance_issues = _model_free_variance(
        clean,
        forward=estimate.forward,
        discount_factor=estimate.discount_factor,
        year_fraction=year_fraction,
        minimum_total_strikes=minimum_total_strikes,
    )
    issues.extend(variance_issues)
    atm, atm_method, put25, put_method, call25, call_method, smile_issues = _smile_measures(
        clean,
        forward=estimate.forward,
        discount_factor=estimate.discount_factor,
        year_fraction=year_fraction,
        nearest_delta_max_distance=nearest_delta_max_distance,
        nearest_atm_log_moneyness=nearest_atm_log_moneyness,
    )
    issues.extend(smile_issues)
    return ResearchExpirySurface(
        expiry=expiry,
        dte=dte,
        discount_factor=estimate.discount_factor,
        forward=estimate.forward,
        parity_pair_count=estimate.pair_count,
        variance=variance,
        atm_iv=atm,
        atm_method=atm_method,
        iv_25d_put=put25,
        put25_method=put_method,
        iv_25d_call=call25,
        call25_method=call_method,
        valid_otm_puts=put_count,
        valid_otm_calls=call_count,
        valid_total_strikes=total,
        issues=tuple(dict.fromkeys(issues)),
    )


def _tenor_with_proxy(
    measures: list[ExpiryMeasure], *, target_days: int, max_distance_days: int
) -> tuple[float | None, str, TenorResult]:
    strict = interpolate_total_variance(measures, target_days=target_days)
    if strict.iv_percent is not None:
        return strict.iv_percent, "TOTAL_VARIANCE_INTERPOLATION", strict
    eligible = [value for value in measures if value.dte > 7 and value.variance > 0]
    if eligible:
        nearest = min(eligible, key=lambda value: (abs(value.dte - target_days), value.dte))
        if abs(nearest.dte - target_days) <= max_distance_days:
            return 100.0 * math.sqrt(nearest.variance), "NEAREST_EXPIRY_PROXY", strict
    return None, "UNAVAILABLE", strict


def _fixed_smile(
    expiries: list[ResearchExpirySurface],
    field: str,
    method_field: str,
    *,
    target_days: int = 30,
    max_distance_days: int = 18,
) -> tuple[float | None, str]:
    measures = [
        ExpiryMeasure(
            expiry=value.expiry,
            year_fraction=value.dte / 365.0,
            variance=(float(getattr(value, field)) / 100.0) ** 2,
        )
        for value in expiries
        if getattr(value, field) is not None
    ]
    strict = interpolate_total_variance(measures, target_days=target_days).iv_percent
    if strict is not None:
        methods = {
            str(getattr(value, method_field))
            for value in expiries
            if getattr(value, field) is not None
        }
        suffix = "+NEAREST_DELTA_PROXY" if "NEAREST_DELTA_PROXY" in methods else ""
        return strict, "TOTAL_VARIANCE_INTERPOLATION" + suffix
    eligible = [value for value in expiries if value.dte > 7 and getattr(value, field) is not None]
    if eligible:
        nearest = min(eligible, key=lambda value: (abs(value.dte - target_days), value.dte))
        if abs(nearest.dte - target_days) <= max_distance_days:
            source_method = str(getattr(nearest, method_field))
            return float(getattr(nearest, field)), f"NEAREST_EXPIRY_PROXY+{source_method}"
    return None, "UNAVAILABLE"


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator == 0:
        return None
    return numerator / denominator


def build_carrier_surface(
    frame: pd.DataFrame,
    *,
    session_date: str,
    carrier_id: str,
    economic_index_id: str,
    spot: float,
    minimum_total_strikes: int = 9,
    include_identifiable_adjusted_contracts: bool = True,
    nearest_tenor_max_distance_days: dict[int, int] | None = None,
    nearest_delta_max_distance: float = 0.12,
    nearest_atm_log_moneyness: float = 0.08,
    observation_time: datetime | None = None,
    methodology_version: str = RESEARCH_SURFACE_METHOD,
) -> ResearchCarrierSurface:
    input_contracts = len(frame)
    standard_contracts = int(frame["is_standard"].fillna(False).sum())
    if include_identifiable_adjusted_contracts:
        eligible = frame.loc[
            pd.to_numeric(frame["contract_unit"], errors="coerce").gt(0)
            & frame["option_type"].isin(["C", "P"])
        ].copy()
    else:
        eligible = frame.loc[frame["is_standard"].fillna(False)].copy()
    eligible_contracts = len(eligible)
    adjusted_contracts = int((~eligible["is_standard"].fillna(False)).sum())
    tenor_distances = nearest_tenor_max_distance_days or {30: 18, 60: 35, 90: 45}
    expiry_results = [
        build_expiry_surface(
            group,
            session_date=session_date,
            expiry=pd.Timestamp(expiry).date().isoformat(),
            spot=spot,
            minimum_total_strikes=minimum_total_strikes,
            nearest_delta_max_distance=nearest_delta_max_distance,
            nearest_atm_log_moneyness=nearest_atm_log_moneyness,
            observation_time=observation_time,
        )
        for expiry, group in eligible.groupby("expiry", sort=True)
    ]
    measures = [
        ExpiryMeasure(value.expiry, value.dte / 365.0, value.variance)
        for value in expiry_results
        if value.variance is not None
    ]
    tenor = {
        days: _tenor_with_proxy(
            measures,
            target_days=days,
            max_distance_days=tenor_distances[days],
        )
        for days in (30, 60, 90)
    }
    iv30, iv30_method, _ = tenor[30]
    iv60, iv60_method, _ = tenor[60]
    iv90, iv90_method, _ = tenor[90]
    fvar, fvol, fvar_issue = forward_variance_30_90(iv30, iv90)
    atm, atm_method = _fixed_smile(expiry_results, "atm_iv", "atm_method")
    put25, put25_method = _fixed_smile(expiry_results, "iv_25d_put", "put25_method")
    call25, call25_method = _fixed_smile(expiry_results, "iv_25d_call", "call25_method")
    required = (iv30, iv90, fvol, atm, put25, call25)
    issues = [
        f"IV{days}_{strict.issue}"
        for days, (value, _method, strict) in tenor.items()
        if value is None and strict.issue is not None
    ]
    if fvar_issue is not None:
        issues.append(fvar_issue)
    if atm is None:
        issues.append("ATM30_UNAVAILABLE")
    if put25 is None:
        issues.append("PUT25_30_UNAVAILABLE")
    if call25 is None:
        issues.append("CALL25_30_UNAVAILABLE")
    method_by_field = {
        "IV30": iv30_method,
        "IV60": iv60_method,
        "IV90": iv90_method,
        "ATM30": atm_method,
        "PUT25_30": put25_method,
        "CALL25_30": call25_method,
    }
    issues.extend(
        f"{field}_{method}" for field, method in method_by_field.items() if "PROXY" in method
    )
    if all(value is not None and math.isfinite(value) for value in required):
        status = "VALID"
    elif any(value is not None for value in required):
        status = "DEGRADED"
    else:
        status = "INVALID" if input_contracts else "UNKNOWN"
    put_volume = float(eligible.loc[eligible["option_type"] == "P", "daily_volume"].sum())
    call_volume = float(eligible.loc[eligible["option_type"] == "C", "daily_volume"].sum())
    put_oi = float(eligible.loc[eligible["option_type"] == "P", "open_interest"].sum())
    call_oi = float(eligible.loc[eligible["option_type"] == "C", "open_interest"].sum())
    put_premium = float(eligible.loc[eligible["option_type"] == "P", "daily_amount"].sum())
    call_premium = float(eligible.loc[eligible["option_type"] == "C", "daily_amount"].sum())
    rr25 = None if put25 is None or call25 is None else call25 - put25
    down_skew = None if put25 is None or atm is None else put25 - atm
    up_skew = None if call25 is None or atm is None else call25 - atm
    bf25 = None if put25 is None or call25 is None or atm is None else (put25 + call25) / 2.0 - atm
    wing = None if iv30 is None or atm is None else (iv30 / 100.0) ** 2 - (atm / 100.0) ** 2
    term = None if iv30 is None or iv90 is None else math.log(iv30 / iv90)
    return ResearchCarrierSurface(
        session_date=session_date,
        carrier_id=carrier_id,
        economic_index_id=economic_index_id,
        evidence_tier="RESEARCH_ONLY",
        methodology_version=methodology_version,
        surface_status=status,
        input_contracts=input_contracts,
        standard_contracts=standard_contracts,
        eligible_contracts=eligible_contracts,
        adjusted_contracts=adjusted_contracts,
        iv30_mf=iv30,
        iv30_method=iv30_method,
        iv60_mf=iv60,
        iv60_method=iv60_method,
        iv90_mf=iv90,
        iv90_method=iv90_method,
        fvar_30_90=fvar,
        fvol_30_90=fvol,
        term_log_ratio_30_90=term,
        atm_iv30=atm,
        atm_iv30_method=atm_method,
        iv_25d_put30=put25,
        iv_25d_put30_method=put25_method,
        iv_25d_call30=call25,
        iv_25d_call30_method=call25_method,
        rr25=rr25,
        down_skew25=down_skew,
        up_skew25=up_skew,
        bf25=bf25,
        wing_variance_spread=wing,
        pcr_volume=_safe_ratio(put_volume, call_volume),
        pcr_oi=_safe_ratio(put_oi, call_oi),
        pcr_premium=_safe_ratio(put_premium, call_premium),
        expiries=tuple(expiry_results),
        issues=tuple(dict.fromkeys(issues)),
    )
