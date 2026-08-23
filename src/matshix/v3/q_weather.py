from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from matshix.calendar import (
    expiry_timestamp,
    research_bar_time,
    surface_cutoff,
    year_fraction_act365f,
)
from matshix.surface.research import ResearchCarrierSurface, build_carrier_surface
from matshix.v3.authority import (
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    CARRIER_ID,
    ECONOMIC_INDEX_ID,
    HORIZON_SESSIONS,
)


@dataclass(frozen=True)
class ExactQResult:
    q_status: str
    target_year_fraction: float
    target_calendar_days: float
    q_total_variance_h20: float | None
    q_variance_h20: float | None
    lower_expiry: str | None
    upper_expiry: str | None
    exact_target_bracket: bool
    method: str
    parity_forward: float | None
    parity_forward_lower: float | None
    parity_forward_upper: float | None
    parity_pair_count: int | None
    valid_strikes: int | None
    put_count: int | None
    call_count: int | None


def _interpolate(left: float, right: float, weight: float) -> float:
    return (1.0 - weight) * left + weight * right


def exact_target_q(
    surface: ResearchCarrierSurface,
    *,
    target_year_fraction: float,
) -> ExactQResult:
    """Strictly bracket H20 and interpolate total variance, never a nearest expiry."""

    target_days = target_year_fraction * 365.0
    valid = sorted(
        [
            value
            for value in surface.expiries
            if value.variance is not None
            and np.isfinite(value.variance)
            and float(value.variance) > 0
            and value.forward is not None
            and np.isfinite(value.forward)
            and float(value.forward) > 0
            and value.parity_pair_count > 0
            and value.dte > 7
        ],
        key=lambda value: value.dte,
    )
    exact = next(
        (value for value in valid if math.isclose(value.dte, target_days, abs_tol=1e-10)),
        None,
    )
    lower = exact or next((value for value in reversed(valid) if value.dte < target_days), None)
    upper = exact or next((value for value in valid if value.dte > target_days), None)
    if lower is None or upper is None:
        return ExactQResult(
            "NO_EXACT_BRACKET",
            target_year_fraction,
            target_days,
            None,
            None,
            None if lower is None else lower.expiry,
            None if upper is None else upper.expiry,
            False,
            "UNAVAILABLE",
            None,
            None if lower is None else lower.forward,
            None if upper is None else upper.forward,
            None,
            None,
            None,
            None,
        )
    assert lower.variance is not None
    assert upper.variance is not None
    assert lower.forward is not None
    assert upper.forward is not None
    if lower.expiry == upper.expiry:
        total_variance = target_year_fraction * float(lower.variance)
        forward = float(lower.forward)
        method = "EXACT_MATURITY"
    else:
        lower_t = lower.dte / 365.0
        upper_t = upper.dte / 365.0
        weight = (target_year_fraction - lower_t) / (upper_t - lower_t)
        total_variance = _interpolate(
            lower_t * float(lower.variance),
            upper_t * float(upper.variance),
            weight,
        )
        forward = _interpolate(float(lower.forward), float(upper.forward), weight)
        method = "TOTAL_VARIANCE_EXACT_BRACKET"
    q_variance = total_variance / target_year_fraction
    if not all(np.isfinite(value) and value > 0 for value in (total_variance, q_variance, forward)):
        return ExactQResult(
            "STATIC_ARBITRAGE_VIOLATION",
            target_year_fraction,
            target_days,
            None,
            None,
            lower.expiry,
            upper.expiry,
            True,
            method,
            None,
            float(lower.forward),
            float(upper.forward),
            min(lower.parity_pair_count, upper.parity_pair_count),
            None,
            None,
            None,
        )
    return ExactQResult(
        "OK",
        target_year_fraction,
        target_days,
        float(total_variance),
        float(q_variance),
        lower.expiry,
        upper.expiry,
        True,
        method,
        float(forward),
        float(lower.forward),
        float(upper.forward),
        min(lower.parity_pair_count, upper.parity_pair_count),
        min(lower.valid_total_strikes, upper.valid_total_strikes),
        min(lower.valid_otm_puts, upper.valid_otm_puts),
        min(lower.valid_otm_calls, upper.valid_otm_calls),
    )


def wing_dominance(down_tail: object, up_tail: object) -> str | None:
    down = pd.to_numeric(pd.Series([down_tail]), errors="coerce").iloc[0]
    up = pd.to_numeric(pd.Series([up_tail]), errors="coerce").iloc[0]
    if pd.isna(down) or pd.isna(up):
        return None
    if math.isclose(float(down), float(up), rel_tol=0.0, abs_tol=1e-12):
        return "TIE"
    return "DOWN" if float(down) > float(up) else "UP"


def build_q_surfaces(
    option_prices: pd.DataFrame,
    etf_marks: pd.DataFrame,
    *,
    progress: Any | None = None,
) -> dict[pd.Timestamp, ResearchCarrierSurface]:
    local_options = option_prices.loc[option_prices["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    local_marks = etf_marks.loc[etf_marks["carrier_id"].astype(str).eq(CARRIER_ID)].copy()
    spots = {
        pd.Timestamp(row["session_date"]): float(row["etf_mark"])
        for row in local_marks.to_dict(orient="records")
        if row["etf_mark"] is not None and np.isfinite(row["etf_mark"])
    }
    groups = list(local_options.groupby("session_date", sort=True))
    surfaces: dict[pd.Timestamp, ResearchCarrierSurface] = {}
    for position, (session, group) in enumerate(groups, start=1):
        session_value = pd.Timestamp(session).normalize()
        spot = spots.get(session_value)
        if spot is None or spot <= 0:
            continue
        surfaces[session_value] = build_carrier_surface(
            group,
            session_date=session_value.date().isoformat(),
            carrier_id=CARRIER_ID,
            economic_index_id=ECONOMIC_INDEX_ID,
            spot=spot,
            observation_time=surface_cutoff(session_value),
            methodology_version="MATSHIX_V3_RESEARCH_MINUTE_CLOSE_EXACT_H20",
        )
        if progress is not None and (position % 250 == 0 or position == len(groups)):
            progress(f"V3 Q surfaces {position}/{len(groups)}")
    return surfaces


def _empty_q(status: str, target_year_fraction: float) -> ExactQResult:
    return ExactQResult(
        status,
        target_year_fraction,
        target_year_fraction * 365.0,
        None,
        None,
        None,
        None,
        False,
        "UNAVAILABLE",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _tail_fields(surface: ResearchCarrierSurface | None) -> dict[str, Any]:
    if surface is None:
        return {
            "atm_iv": None,
            "put25_iv": None,
            "call25_iv": None,
            "down_tail": None,
            "up_tail": None,
            "wing_coverage": "UNKNOWN",
            "dominant_side": None,
            "atm_method": "UNAVAILABLE",
            "put25_method": "UNAVAILABLE",
            "call25_method": "UNAVAILABLE",
        }
    down = surface.down_skew25
    up = surface.up_skew25
    wing_coverage = "BOTH" if down is not None and up is not None else "PARTIAL_OR_UNKNOWN"
    return {
        "atm_iv": surface.atm_iv30,
        "put25_iv": surface.iv_25d_put30,
        "call25_iv": surface.iv_25d_call30,
        "down_tail": down,
        "up_tail": up,
        "wing_coverage": wing_coverage,
        "dominant_side": wing_dominance(down, up),
        "atm_method": surface.atm_iv30_method,
        "put25_method": surface.iv_25d_put30_method,
        "call25_method": surface.iv_25d_call30_method,
    }


def build_q_ledger(
    outcomes: pd.DataFrame,
    surfaces: dict[pd.Timestamp, ResearchCarrierSurface],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for metadata in outcomes.to_dict(orient="records"):
        session = pd.Timestamp(metadata["forecast_session"]).normalize()
        observed_at = research_bar_time(session)
        known_at = surface_cutoff(session)
        target_end = pd.Timestamp(metadata["target_end_session"])
        target_yf = year_fraction_act365f(known_at, expiry_timestamp(target_end))
        surface = surfaces.get(session)
        result = _empty_q("UNOBSERVABLE", target_yf) if surface is None else exact_target_q(
            surface, target_year_fraction=target_yf
        )
        tail = _tail_fields(surface)
        rows.append(
            {
                "forecast_session": session,
                "target_start_session": metadata["target_start_session"],
                "target_end_session": target_end,
                "carrier_id": CARRIER_ID,
                "economic_index_id": ECONOMIC_INDEX_ID,
                "horizon_sessions": HORIZON_SESSIONS,
                "observation_time": observed_at,
                "known_at": known_at,
                "consumer_decision_as_of": metadata["consumer_decision_as_of"],
                "price_kind": "AETF_1456_MINUTE_CLOSE",
                "evidence_kind": "RETROSPECTIVE_DEVELOPMENT",
                "evidence_tier": "RESEARCH_MINUTE_CLOSE",
                "formal_pit_claimed": False,
                "unit": "ANNUALIZED_VARIANCE",
                **asdict(result),
                **tail,
                "surface_status": None if surface is None else surface.surface_status,
                "surface_methodology": None if surface is None else surface.methodology_version,
                "input_contracts": None if surface is None else surface.input_contracts,
                "eligible_contracts": None if surface is None else surface.eligible_contracts,
                "liquidity_status": "CLOSE_PROXY_NO_BID_ASK",
                "descriptive_q_weather": True,
                "issues": "UNOBSERVABLE_SURFACE"
                if surface is None
                else "|".join(surface.issues),
                "authority_version": AUTHORITY_VERSION,
                "authority_sha256": AUTHORITY_SHA256,
            }
        )
    return pd.DataFrame(rows).sort_values("forecast_session", kind="stable").reset_index(drop=True)


def evaluate_q_integrity(q: pd.DataFrame) -> dict[str, Any]:
    ok = q.loc[q["q_status"].eq("OK")].copy()
    unavailable = q.loc[q["q_status"].ne("OK")].copy()
    identity = (
        pd.to_numeric(ok["q_variance_h20"], errors="coerce")
        * pd.to_numeric(ok["target_year_fraction"], errors="coerce")
        - pd.to_numeric(ok["q_total_variance_h20"], errors="coerce")
    ).abs()
    checks = {
        "h20_only": bool(set(q["horizon_sessions"].astype(int)) == {HORIZON_SESSIONS}),
        "minute_close_only": bool(set(q["price_kind"].astype(str)) == {"AETF_1456_MINUTE_CLOSE"}),
        "formal_pit_not_claimed": bool(~q["formal_pit_claimed"].astype(bool).any()),
        "exact_method_only": bool(
            ok["method"].isin(["EXACT_MATURITY", "TOTAL_VARIANCE_EXACT_BRACKET"]).all()
        ),
        "total_variance_identity": bool(len(ok) > 0 and identity.le(1e-12).all()),
        "positive_finite_q": bool(
            len(ok) > 0
            and pd.to_numeric(ok["q_variance_h20"], errors="coerce").gt(0).all()
            and pd.to_numeric(ok["q_variance_h20"], errors="coerce").notna().all()
        ),
        "unknown_is_null": bool(
            pd.to_numeric(unavailable["q_variance_h20"], errors="coerce").isna().all()
        ),
    }
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "reason": "Q_RESEARCH_INTEGRITY_PASSED"
        if all(checks.values())
        else "Q_RESEARCH_INTEGRITY_FAILED",
        "checks": checks,
        "rows": len(q),
        "exact_h20_rows": len(ok),
        "exact_h20_coverage_disclosed_only": len(ok) / len(q) if len(q) else 0.0,
        "q_status_counts": {
            str(key): int(value) for key, value in q["q_status"].value_counts().items()
        },
        "maximum_total_variance_identity_error": float(identity.max()) if len(identity) else None,
    }
