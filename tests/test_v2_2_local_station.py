from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matshix.v2.local_station import (
    DEVELOPMENT_START,
    STATE_FIELDS,
    VARIANCE_C2_FEATURES,
    _available_training,
    _logistic_score,
    _path_features,
    _ridge_forecast,
    add_physical_scores,
    build_local_state,
    verify_v2_2_authority_chain,
)


def _state_features(rows: int = 140) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "forecast_session": pd.bdate_range("2025-01-02", periods=rows),
            "etf_return_1d": 0.0,
            "etf_return_5d": 0.0,
            "d5_up_skew25": 0.0,
            "p_d1_log_iv30": 0.60,
            "p_d5_log_iv30": 0.40,
            "p_iv_vol_of_vol20": 0.20,
            "p_neg_etf_return_1d": 0.50,
            "p_down_skew25": 0.80,
            "p_d5_down_skew25": 0.60,
            "p_up_skew25": 0.20,
            "p_d5_up_skew25": 0.40,
            "p_neg_d5_log_iv30": 0.70,
            "p_neg_d5_iv_vol_of_vol20": 0.30,
            "p_neg_d5_fvol_30_90": 0.40,
            "p_neg_d5_down_skew25": 0.70,
            "p_etf_return_5d": 0.50,
        }
    )


def test_v223_authority_chain_matches_frozen_bytes() -> None:
    project = Path(__file__).resolve().parents[1]
    verified = verify_v2_2_authority_chain(project)
    assert verified["MATSHIX_V2_2_3_AUTHORITY.md"]["status"] == "VERIFIED"
    assert verified["MATSHIX_V2_2_2_AUTHORITY.md"]["status"] == "VERIFIED"
    assert verified["MATSHIX_V2_2_1_AUTHORITY.md"]["status"] == "VERIFIED"
    assert verified["MATSHIX_V2_2_AUTHORITY.md"]["status"] == "VERIFIED"
    assert verified["MATSHIX_V2_2_CONSTRUCTION_PLAN.md"]["status"] == "VERIFIED"
    assert DEVELOPMENT_START == pd.Timestamp("2020-01-02")


def test_local_state_uses_frozen_formula_and_no_global_phase() -> None:
    state = build_local_state(_state_features())
    last = state.iloc[-1]
    assert last["common_iv_shock"] == pytest.approx(44.0)
    assert last["downside_price_shock"] == pytest.approx(46.4)
    assert last["upside_price_shock"] == pytest.approx(46.4)
    assert last["down_tail"] == pytest.approx(73.0)
    assert last["up_tail"] == pytest.approx(27.0)
    assert last["down_tail_persistence"] == pytest.approx(100.0)
    assert last["up_tail_persistence"] == pytest.approx(0.0)
    assert last["market_breadth"] == "NOT_APPLICABLE"
    assert last["primary_phase"] == "NOT_APPLICABLE"
    assert last["state_status"] == "OK"


def test_future_feature_mutation_cannot_change_prior_state() -> None:
    original = _state_features()
    changed = original.copy()
    changed.loc[changed.index[-1], "etf_return_1d"] = 10.0
    changed.loc[changed.index[-1], "p_d1_log_iv30"] = 0.0
    first = build_local_state(original)
    second = build_local_state(changed)
    pd.testing.assert_series_equal(
        first.iloc[-2][list(first.columns)],
        second.iloc[-2][list(second.columns)],
        check_names=False,
    )


def test_outcome_not_yet_available_is_purged_from_training() -> None:
    timezone = "Asia/Shanghai"
    frame = pd.DataFrame(
        {
            "known_at": pd.to_datetime(
                [
                    "2026-01-05 14:56:59+08:00",
                    "2026-01-06 14:56:59+08:00",
                    "2026-01-07 14:56:59+08:00",
                ]
            ).tz_convert(timezone),
            "outcome_available_at_h20": pd.to_datetime(
                [
                    "2026-01-06 09:00:00+08:00",
                    "2026-01-08 09:00:00+08:00",
                    "2026-01-09 09:00:00+08:00",
                ]
            ).tz_convert(timezone),
            "rv_variance_h20": [0.1, 0.2, 0.3],
        }
    )
    training = _available_training(
        frame,
        2,
        target="rv_variance_h20",
        available_at="outcome_available_at_h20",
    )
    assert list(training.index) == [0]


def test_local_path_registry_has_no_breadth_feature() -> None:
    up = _path_features("up", challenger=True)
    down = _path_features("down", challenger=True)
    assert "side_tail_breadth" not in up
    assert "side_tail_breadth" not in down
    assert "up_tail_persistence" in up
    assert "down_tail_persistence" in down
    assert "q_term_log_ratio_h10_h20" not in VARIANCE_C2_FEATURES
    assert "q_term_log_ratio_h10_h20" not in up
    assert "q_term_log_ratio_h10_h20" not in down


def _physical_model_frame(*, h10_status: str, h20_status: str) -> pd.DataFrame:
    rows = 253
    values = np.arange(rows, dtype=float)
    known_at = pd.bdate_range("2024-01-02", periods=rows, tz="Asia/Shanghai") + pd.Timedelta(
        hours=14, minutes=56
    )
    frame = pd.DataFrame(
        {
            "known_at": known_at,
            "outcome_available_at_h10": known_at,
            "outcome_available_at_h20": known_at,
            "label_status_h20": "OBSERVED",
            "rv_variance_h20": 0.08 + 0.01 * np.sin(values / 9.0),
            "rv_forecast30": 0.09 + 0.01 * np.cos(values / 11.0),
            "upside_path_breach_h10": values.astype(int) % 4 == 0,
            "downside_path_breach_h10": values.astype(int) % 5 == 0,
            "q_horizon_status_h10": h10_status,
            "q_horizon_status_h20": h20_status,
            "state_status": "OK",
            "log_rv_d1_lag1": 0.1 + np.sin(values / 7.0),
            "log_mean_rv_d5_lag1": 0.2 + np.cos(values / 13.0),
            "log_mean_rv_d22_lag1": 0.3 + np.sin(values / 17.0),
            "log_q_variance_h10": -2.0 + 0.1 * np.sin(values / 19.0),
            "log_q_variance_h20": -1.8 + 0.1 * np.cos(values / 23.0),
            "up_skew25": 0.1 + 0.01 * np.sin(values / 5.0),
            "down_skew25": 0.1 + 0.01 * np.cos(values / 5.0),
        }
    )
    for offset, field in enumerate(STATE_FIELDS, start=2):
        frame[field] = 40.0 + offset + np.sin(values / float(offset))
    for side, offset in (("up", 7.0), ("down", 11.0)):
        frame[f"past_{side}_max_move_d5_lag1"] = 0.01 + np.sin(values / offset)
        frame[f"past_{side}_max_move_d20_lag1"] = 0.02 + np.cos(values / offset)
        frame[f"past_{side}_overnight_gap_d20_lag1"] = 0.03 + np.sin(values / (offset + 2.0))
    return frame


def test_horizon_local_models_do_not_require_the_other_q_horizon() -> None:
    h20_only = add_physical_scores(
        _physical_model_frame(h10_status="MISSING_BRACKET", h20_status="OK")
    ).iloc[-1]
    assert bool(h20_only["variance_calendar_opportunity"])
    assert bool(h20_only["variance_horizon_input_ready"])
    assert bool(h20_only["variance_opportunity"])
    assert pd.notna(h20_only["p_c2_variance_h20"])
    assert not bool(h20_only["up_path_horizon_input_ready"])

    h10_only = add_physical_scores(
        _physical_model_frame(h10_status="OK", h20_status="MISSING_BRACKET")
    ).iloc[-1]
    assert bool(h10_only["up_path_calendar_opportunity"])
    assert bool(h10_only["up_path_horizon_input_ready"])
    assert bool(h10_only["up_path_opportunity"])
    assert pd.notna(h10_only["p_up_c2_raw_score_h10"])
    assert pd.notna(h10_only["p_down_c2_raw_score_h10"])
    assert not bool(h10_only["variance_horizon_input_ready"])


def test_frozen_models_are_deterministic_and_emit_raw_score() -> None:
    rows = 300
    x = np.linspace(-2.0, 2.0, rows)
    training = pd.DataFrame(
        {
            "x1": x,
            "x2": np.sin(x),
            "x3": np.cos(x),
            "variance": np.exp(0.2 + 0.3 * x),
            "event": x > 0,
        }
    )
    current = pd.Series({"x1": 0.7, "x2": np.sin(0.7), "x3": np.cos(0.7)})
    first = _ridge_forecast(
        training,
        current,
        features=("x1", "x2", "x3"),
        target="variance",
    )
    second = _ridge_forecast(
        training,
        current,
        features=("x1", "x2", "x3"),
        target="variance",
    )
    assert first == second
    assert first[0] is not None and first[0] > 0
    raw, status = _logistic_score(
        training,
        current,
        features=("x1", "x2", "x3"),
        target="event",
    )
    assert status == "RETROSPECTIVE_SCORE"
    assert raw is not None
    assert raw > 1.0


def test_local_builder_does_not_import_shortvol_runtime() -> None:
    source = (Path(__file__).resolve().parents[1] / "src/matshix/v2/local_station.py").read_text(
        encoding="utf-8"
    )
    assert "matshix.research.shortvol" not in source
    assert "data/processed/v2_1" not in source
