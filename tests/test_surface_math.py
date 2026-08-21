from __future__ import annotations

import math
from datetime import timedelta

import pandas as pd
import pytest

from matshix.calendar import expiry_timestamp, research_bar_time, year_fraction_act365f
from matshix.surface.black import black_price, implied_volatility
from matshix.surface.research import build_carrier_surface
from matshix.surface.tenor import ExpiryMeasure, forward_variance_30_90, interpolate_total_variance


def test_black_implied_volatility_round_trip() -> None:
    price = black_price(
        option_type="P",
        forward=3.02,
        strike=3.10,
        sigma=0.235,
        year_fraction=45 / 365,
        discount_factor=0.996,
    )
    recovered = implied_volatility(
        option_type="P",
        price=price,
        forward=3.02,
        strike=3.10,
        year_fraction=45 / 365,
        discount_factor=0.996,
    )
    assert recovered == pytest.approx(0.235, abs=1e-10)


def test_total_variance_interpolation_and_forward_variance() -> None:
    measures = [
        ExpiryMeasure("2026-01-20", 20 / 365, 0.20**2),
        ExpiryMeasure("2026-02-19", 50 / 365, 0.24**2),
        ExpiryMeasure("2026-05-10", 130 / 365, 0.28**2),
    ]
    result = interpolate_total_variance(measures, target_days=30)
    expected = ((20 / 365) * 0.20**2 * (2 / 3) + (50 / 365) * 0.24**2 / 3) / (30 / 365)
    assert result.variance == pytest.approx(expected)
    variance, volatility, issue = forward_variance_30_90(20.0, 25.0)
    assert issue is None
    assert variance is not None and variance > 0
    assert volatility == pytest.approx(100 * math.sqrt(variance))
    assert forward_variance_30_90(40.0, 20.0)[2] == "NEGATIVE_FORWARD_VARIANCE"


def _synthetic_surface_frame(session: str = "2026-01-05") -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cutoff = research_bar_time(session)
    for days, base_sigma in ((20, 0.20), (45, 0.22), (75, 0.24), (120, 0.26)):
        expiry_date = pd.Timestamp(session) + timedelta(days=days)
        expiry = expiry_date.date().isoformat()
        year_fraction = year_fraction_act365f(cutoff, expiry_timestamp(expiry))
        discount = math.exp(-0.018 * year_fraction)
        forward = 3.0 / discount
        for number in range(25):
            strike = 2.4 + 0.05 * number
            sigma = base_sigma + 0.12 * math.log(strike / forward) ** 2
            for kind in ("C", "P"):
                rows.append(
                    {
                        "contract_id": f"{days}-{number}-{kind}",
                        "expiry": expiry_date,
                        "strike": strike,
                        "option_type": kind,
                        "price": black_price(
                            option_type=kind,
                            forward=forward,
                            strike=strike,
                            sigma=sigma,
                            year_fraction=year_fraction,
                            discount_factor=discount,
                        ),
                        "open_interest": 100 + number,
                        "daily_volume": 50 + number,
                        "daily_amount": 1000 + number,
                        "is_standard": True,
                        "contract_unit": 10000,
                    }
                )
    return pd.DataFrame(rows)


def test_research_surface_builds_all_business_tenors() -> None:
    surface = build_carrier_surface(
        _synthetic_surface_frame(),
        session_date="2026-01-05",
        carrier_id="SSE50_510050",
        economic_index_id="SSE50",
        spot=3.0,
    )
    assert surface.surface_status == "VALID"
    assert surface.iv30_mf is not None
    assert surface.iv60_mf is not None
    assert surface.iv90_mf is not None
    assert surface.iv_25d_put30 is not None
    assert surface.iv_25d_call30 is not None
    assert surface.iv30_method == "TOTAL_VARIANCE_INTERPOLATION"
    assert surface.evidence_tier == "RESEARCH_ONLY"


def test_research_tenor_proxy_is_bounded_and_labeled() -> None:
    frame = _synthetic_surface_frame()
    first_expiry = frame["expiry"].min()
    frame = frame.loc[frame["expiry"] == first_expiry].copy()
    surface = build_carrier_surface(
        frame,
        session_date="2026-01-05",
        carrier_id="SSE50_510050",
        economic_index_id="SSE50",
        spot=3.0,
    )
    assert surface.iv30_mf is not None
    assert surface.iv30_method == "NEAREST_EXPIRY_PROXY"
    assert surface.iv90_mf is None
    assert surface.iv90_method == "UNAVAILABLE"
