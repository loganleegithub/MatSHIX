from __future__ import annotations

import math

import numpy as np
import pandas as pd

from matshix.calendar import exchange_sessions_in_range
from matshix.v3.scoring import (
    _block_positions,
    _moving_date_blocks,
    evaluate_p_core,
    evaluate_qp_construction,
    evaluate_qp_direction,
    qlike,
)


def test_qlike_matches_hand_calculation_and_arithmetic_mean_beats_geometric_constant() -> None:
    actual = np.asarray([1.0, 3.0])
    arithmetic = np.full(2, 2.0)
    geometric = np.full(2, math.sqrt(3.0))
    expected = np.asarray(
        [
            0.5 - math.log(0.5) - 1.0,
            1.5 - math.log(1.5) - 1.0,
        ]
    )
    np.testing.assert_allclose(qlike(actual, arithmetic), expected)
    assert qlike(actual, arithmetic).mean() < qlike(actual, geometric).mean()


def test_moving_date_blocks_preserve_missing_exchange_sessions() -> None:
    calendar = exchange_sessions_in_range("2024-01-02", "2024-03-29")
    paired = pd.Series(calendar[[0, 1, 2, 25, 26, 27]])
    blocks = _moving_date_blocks(paired, block_length=20)
    assert blocks
    assert not any(2 in block and 3 in block for block in blocks)

    first = _block_positions(paired, block_length=20, rng=np.random.default_rng(2026082401))
    second = _block_positions(paired, block_length=20, rng=np.random.default_rng(2026082401))
    np.testing.assert_array_equal(first, second)
    assert len(first) == len(paired)


def _qp_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "forecast_session": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "horizon_sessions": [20, 20],
            "qp_status": ["THICK_COMPENSATION", "UNCERTAIN"],
            "qp_evidence_tier": ["RESEARCH_QP_ESTIMATE", "RESEARCH_QP_ESTIMATE"],
            "qp_unit": ["TOTAL_VARIANCE", "TOTAL_VARIANCE"],
            "q_total_variance_h20": [0.0040, 0.0030],
            "p_primary_total_variance_h20": [0.0030, 0.0030],
            "p_interval_total_low_h20": [0.0025, 0.0025],
            "p_interval_total_high_h20": [0.0035, 0.0035],
            "qp_total_variance_premium_h20": [0.0010, 0.0],
            "qp_total_interval_low_h20": [0.0005, -0.0005],
            "qp_total_interval_high_h20": [0.0015, 0.0005],
            "ex_post_q_total_minus_realized_h20": [0.0008, -0.0001],
            "p_evaluation_opportunity": [True, True],
            "q_status": ["OK", "OK"],
        }
    )


def test_qp_construction_uses_total_variance_identities() -> None:
    result = evaluate_qp_construction(_qp_frame(), p_core_passed=True)
    assert result["verdict"] == "PASS"
    assert all(result["checks"].values())


def test_shared_q_direction_statistic_is_explicitly_not_identifying() -> None:
    result = evaluate_qp_direction(_qp_frame(), p_core_passed=True)
    assert result["verdict"] == "NOT_APPLICABLE"
    assert result["reason"] == "SHARED_Q_OUTCOME_NOT_IDENTIFYING"
    assert result["shared_q_direction_test_executed"] is False
    assert "spearman" not in result


def test_p_core_stops_at_the_frozen_sample_gate() -> None:
    frame = pd.DataFrame(
        {
            "forecast_session": pd.date_range("2024-01-02", periods=10, freq="D"),
            "p_evaluation_opportunity": True,
            "p_primary_variance_h20": 0.04,
            "p_b0_climatology_variance_h20": 0.04,
            "p_b1_ewma94_variance_h20": 0.04,
            "p_interval_low_h20": 0.02,
            "p_interval_high_h20": 0.06,
            "rv_variance_h20": 0.04,
            "is_causal_extreme": False,
        }
    )
    result = evaluate_p_core(frame)
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["reason"] == "P_CORE_SAMPLE_GATE_NOT_MET"
    assert result["paired_point_rows"] == 10
