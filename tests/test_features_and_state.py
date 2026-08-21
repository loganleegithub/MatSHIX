from __future__ import annotations

import pandas as pd

from matshix.constants import INDEX_ORDER
from matshix.features.percentile import rolling_midrank_percentile
from matshix.narrative import HEADLINES, headline
from matshix.state.scores import build_market_score_history


def _feature_row(session: pd.Timestamp, index: str, position: int) -> dict[str, object]:
    index_number = INDEX_ORDER.index(index)
    return {
        "session_date": session,
        "carrier_id": f"carrier-{index}",
        "economic_index_id": index,
        "surface_status": "VALID",
        "issues": "",
        "p_iv30": 0.5,
        "p_d1_log_iv30": 0.5,
        "p_d5_log_iv30": 0.5,
        "p_iv_vol_of_vol20": 0.5,
        "p_neg_etf_return_1d": 0.5,
        "p_down_skew25": 0.5,
        "p_d5_down_skew25": 0.5,
        "p_up_skew25": 0.5,
        "p_d5_up_skew25": 0.5,
        "p_fvol_30_90": 0.5,
        "p_iv90": 0.5,
        "p_d5_fvol_30_90": 0.5,
        "p_term_log_ratio_30_90": 0.5,
        "p_neg_d5_log_iv30": 0.5,
        "p_neg_d5_down_skew25": 0.5,
        "p_neg_d5_fvol_30_90": 0.5,
        "p_etf_return_5d": 0.5,
        "p_neg_d5_iv_vol_of_vol20": 0.5,
        "d5_fvol_30_90": float((position * (index_number + 1)) % 37 - index_number * 4),
        "etf_return_5d": 0.0,
        "vrp_ewma94": 0.01,
        "vrp_percentile": 0.5,
    }


def test_aggregate_percentile_is_percentile_of_aggregate_raw_series() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=270)
    rows = [
        _feature_row(session, index, position)
        for position, session in enumerate(sessions)
        for index in INDEX_ORDER
    ]
    result = build_market_score_history(
        pd.DataFrame(rows), reference_sessions=252, minimum_valid=252
    )
    expected = rolling_midrank_percentile(
        result["aggregate_d5_fvol30_90"], reference_sessions=252, minimum_valid=252
    )
    pd.testing.assert_series_equal(
        result["aggregate_d5_fvol30_90_percentile"], expected, check_names=False
    )
    assert result["aggregate_d5_fvol30_90_percentile"].notna().sum() == 18


def test_balanced_headline_does_not_claim_fragmentation() -> None:
    state = {"data_status": "OK", "primary_phase": "BALANCED_MARKET"}
    assert headline(state) == HEADLINES["BALANCED_MARKET"]
    assert "分化" not in headline(state)


def test_unknown_headline_distinguishes_history_from_surface_failure() -> None:
    text = headline({"data_status": "OK", "primary_phase": "UNKNOWN"})
    assert "曲面完整" in text
    assert "历史基线" in text
