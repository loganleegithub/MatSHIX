from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from matshix.surface.research import ResearchCarrierSurface, ResearchExpirySurface
from matshix.v3.q_weather import build_q_ledger, exact_target_q


def _expiry(expiry: str, dte: float, variance: float) -> ResearchExpirySurface:
    return ResearchExpirySurface(
        expiry=expiry,
        dte=dte,
        discount_factor=0.99,
        forward=3.0,
        parity_pair_count=8,
        variance=variance,
        atm_iv=20.0,
        atm_method="MONEYNESS_INTERPOLATION",
        iv_25d_put=22.0,
        put25_method="DELTA_INTERPOLATION",
        iv_25d_call=19.0,
        call25_method="DELTA_INTERPOLATION",
        valid_otm_puts=8,
        valid_otm_calls=8,
        valid_total_strikes=16,
        issues=(),
    )


def _surface() -> ResearchCarrierSurface:
    return ResearchCarrierSurface(
        session_date="2026-01-05",
        carrier_id="CSI300_510300",
        economic_index_id="CSI300",
        evidence_tier="RESEARCH_ONLY",
        methodology_version="test",
        surface_status="VALID",
        input_contracts=40,
        standard_contracts=40,
        eligible_contracts=40,
        adjusted_contracts=0,
        iv30_mf=20.0,
        iv30_method="TOTAL_VARIANCE_INTERPOLATION",
        iv60_mf=22.0,
        iv60_method="TOTAL_VARIANCE_INTERPOLATION",
        iv90_mf=24.0,
        iv90_method="TOTAL_VARIANCE_INTERPOLATION",
        fvar_30_90=0.05,
        fvol_30_90=22.0,
        term_log_ratio_30_90=-0.1,
        atm_iv30=20.0,
        atm_iv30_method="TOTAL_VARIANCE_INTERPOLATION",
        iv_25d_put30=22.0,
        iv_25d_put30_method="TOTAL_VARIANCE_INTERPOLATION",
        iv_25d_call30=19.0,
        iv_25d_call30_method="TOTAL_VARIANCE_INTERPOLATION",
        rr25=-3.0,
        down_skew25=2.0,
        up_skew25=-1.0,
        bf25=0.5,
        wing_variance_spread=0.01,
        pcr_volume=1.0,
        pcr_oi=1.0,
        pcr_premium=1.0,
        expiries=(_expiry("2026-01-25", 20.0, 0.04), _expiry("2026-02-24", 50.0, 0.09)),
        issues=(),
    )


def test_v3_exact_h20_q_interpolates_total_variance_and_preserves_identity() -> None:
    result = exact_target_q(_surface(), target_year_fraction=30.0 / 365.0)
    expected_total = (2.0 / 3.0) * (20.0 / 365.0) * 0.04 + (1.0 / 3.0) * (
        50.0 / 365.0
    ) * 0.09
    assert result.q_status == "OK"
    assert result.method == "TOTAL_VARIANCE_EXACT_BRACKET"
    assert result.q_total_variance_h20 == pytest.approx(expected_total)
    assert result.q_variance_h20 == pytest.approx(expected_total / (30.0 / 365.0))
    assert result.q_total_variance_h20 == pytest.approx(
        result.q_variance_h20 * result.target_year_fraction
    )


def test_v3_q_never_uses_nearest_expiry_and_wing_does_not_control_variance() -> None:
    unavailable = exact_target_q(_surface(), target_year_fraction=70.0 / 365.0)
    assert unavailable.q_status == "NO_EXACT_BRACKET"
    assert unavailable.q_variance_h20 is None
    assert unavailable.method == "UNAVAILABLE"
    no_wing = replace(
        _surface(),
        atm_iv30=None,
        iv_25d_put30=None,
        iv_25d_call30=None,
        down_skew25=None,
        up_skew25=None,
    )
    assert exact_target_q(no_wing, target_year_fraction=30.0 / 365.0).q_status == "OK"


def test_v3_q_ledger_is_h20_only_and_has_no_h10_dependency() -> None:
    outcomes = pd.DataFrame(
        [
            {
                "forecast_session": pd.Timestamp("2026-01-05"),
                "target_start_session": pd.Timestamp("2026-01-06"),
                "target_end_session": pd.Timestamp("2026-02-03"),
                "consumer_decision_as_of": pd.Timestamp(
                    "2026-01-06 09:00", tz="Asia/Shanghai"
                ),
            }
        ]
    )
    ledger = build_q_ledger(outcomes, {pd.Timestamp("2026-01-05"): _surface()})
    assert list(ledger["horizon_sessions"]) == [20]
    assert "q_variance_h10" not in ledger.columns
    assert "q_horizon_status_h10" not in ledger.columns
    assert ledger.iloc[0]["q_status"] == "OK"
    assert not bool(ledger.iloc[0]["formal_pit_claimed"])
    assert ledger.iloc[0]["evidence_tier"] == "RESEARCH_MINUTE_CLOSE"
