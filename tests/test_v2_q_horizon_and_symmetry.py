from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from matshix.surface.research import ResearchCarrierSurface, ResearchExpirySurface
from matshix.v2.q_surface import (
    enrich_outcomes_with_q,
    evaluate_q_robustness,
    exact_target_q,
    wing_dominance,
)


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


def test_exact_q_interpolates_total_variance_not_volatility() -> None:
    result = exact_target_q(_surface(), target_year_fraction=30.0 / 365.0)
    expected_total = (2.0 / 3.0) * (20.0 / 365.0) * 0.04 + (1.0 / 3.0) * (50.0 / 365.0) * 0.09
    assert result.q_horizon_status == "OK"
    assert result.method == "TOTAL_VARIANCE_EXACT_BRACKET"
    assert result.q_total_variance == pytest.approx(expected_total)
    assert result.q_variance == pytest.approx(expected_total / (30.0 / 365.0))
    assert result.q_expected_move == pytest.approx(expected_total**0.5)


def test_unbracketed_target_never_uses_nearest_expiry_proxy() -> None:
    result = exact_target_q(_surface(), target_year_fraction=70.0 / 365.0)
    assert result.q_horizon_status == "NO_EXACT_BRACKET"
    assert result.q_variance is None
    assert result.method == "UNAVAILABLE"


def test_put_call_mirror_exchanges_wing_dominance() -> None:
    assert wing_dominance(4.0, 1.0) == "DOWN"
    assert wing_dominance(1.0, 4.0) == "UP"
    assert wing_dominance(2.0, 2.0) == "TIE"


def _q_frame(*, robust: bool, rows: int = 140) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=rows)
    return pd.DataFrame(
        {
            "forecast_session": dates,
            "carrier_id": "CSI300_510300",
            "horizon_sessions": 20,
            "q_horizon_status": "OK",
            "q_variance": 0.0505 if robust else 0.05,
            "wing_dominance": "DOWN",
        }
    )


def test_frozen_q_robustness_gate_passes_only_with_required_pair_count() -> None:
    result = evaluate_q_robustness(_q_frame(robust=False), _q_frame(robust=True))
    assert result["verdict"] == "PASS"
    short = evaluate_q_robustness(_q_frame(robust=False, rows=100), _q_frame(robust=True, rows=100))
    assert short["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_expiry_q_is_unchanged_when_only_wing_fields_change() -> None:
    original = _surface()
    mirrored = replace(original, down_skew25=-1.0, up_skew25=2.0)
    assert exact_target_q(original, target_year_fraction=30 / 365) == exact_target_q(
        mirrored, target_year_fraction=30 / 365
    )


def test_q_enrichment_is_idempotent_and_unknown_is_not_zero() -> None:
    outcome = pd.DataFrame(
        [
            {
                "forecast_session": pd.Timestamp("2026-01-05"),
                "carrier_id": "CSI300_510300",
                "horizon_sessions": 10,
                "label_status": "OBSERVED",
                "max_up_log_move_h": 0.12,
                "max_down_log_move_h": 0.08,
                "q_variance_h": None,
                "q_expected_move_h": None,
                "q_horizon_status": "NOT_BUILT",
                "upside_path_breach_h": None,
                "downside_path_breach_h": None,
            }
        ]
    )
    q = pd.DataFrame(
        [
            {
                "forecast_session": pd.Timestamp("2026-01-05"),
                "carrier_id": "CSI300_510300",
                "horizon_sessions": 10,
                "q_variance": None,
                "q_total_variance": None,
                "q_expected_move": None,
                "q_horizon_status": "NO_EXACT_BRACKET",
                "target_year_fraction": 20 / 365,
                "method": "UNAVAILABLE",
                "lower_expiry": "2026-01-20",
                "upper_expiry": None,
            }
        ]
    )
    first = enrich_outcomes_with_q(outcome, q)
    second = enrich_outcomes_with_q(first, q)
    assert list(first.columns) == list(second.columns)
    assert first.iloc[0]["q_path_label_status"] == "UNKNOWN_Q"
    assert pd.isna(first.iloc[0]["upside_path_breach_h"])
