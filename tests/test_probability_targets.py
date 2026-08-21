from __future__ import annotations

import pandas as pd

from matshix.calendar import exchange_sessions_in_range
from matshix.constants import EVENT_IDS
from matshix.probability.model import acceptance_metrics
from matshix.probability.publication import build_current_judgments
from matshix.probability.targets import build_target_ledger


def _history_row(session: pd.Timestamp) -> dict[str, object]:
    return {
        "session_date": session,
        "data_status": "OK",
        "scores": {
            "insurance_level": 50.0,
            "shock": 50.0,
            "down_tail": 50.0,
            "up_tail": 50.0,
            "persistence": 50.0,
            "repair": 50.0,
            "breadth": 0.0,
        },
        "pressure_score": 50.0,
        "primary_phase": "BALANCED_MARKET",
        "cross_market_iv_jump": False,
        "persistent_cross_market_now": False,
        "repair_confirmed": False,
        "breadth_metrics": {"broad_confirmed": False},
        "answers": {"repair": "INACTIVE"},
        "insurance_level_scaled": 0.5,
        "shock_scaled": 0.5,
        "down_tail_scaled": 0.5,
        "breadth_scaled": 0.0,
        "aggregate_iv_vol_of_vol_percentile": 0.5,
        "pressure_change5_scaled": 0.5,
        "persistence_scaled": 0.5,
        "cross_section_pressure_dispersion_scaled": 0.2,
        "segment_iv_jump_true_share": 0.0,
        "aggregate_vrp_percentile": 0.5,
        "repair_scaled": 0.5,
        "inverse_pressure_change5_scaled": 0.5,
    }


def test_missing_exchange_session_censors_future_window() -> None:
    sessions = list(exchange_sessions_in_range("2025-01-02", "2025-03-31")[:35])
    missing = sessions.pop(11)
    history = pd.DataFrame([_history_row(session) for session in sessions])
    ledger = build_target_ledger(history)
    prediction = sessions[10]
    row = ledger.loc[
        (ledger["prediction_date"] == prediction)
        & (ledger["event_id"] == "cross_market_iv_jump_1d")
    ].iloc[0]
    assert missing > prediction
    assert row["event_status"] == "ELIGIBLE"
    assert row["label_status"] == "CENSORED"
    assert pd.isna(row["label"])


def test_base_rate_is_causal_and_laplace_smoothed() -> None:
    rows: list[dict[str, object]] = []
    for position in range(254):
        for event_id in EVENT_IDS:
            rows.append(
                {
                    "event_id": event_id,
                    "prediction_position": position,
                    "target_end_position": position + 1,
                    "event_status": "ELIGIBLE",
                    "label_status": "OBSERVED_1" if position % 4 == 0 else "OBSERVED_0",
                    "label": 1 if position % 4 == 0 else 0,
                    "target_window_end_session": "2026-01-01",
                }
            )
    ledger = pd.DataFrame(rows)
    judgments = build_current_judgments(ledger, prediction_position=252)
    value = judgments["cross_market_iv_jump_1d"]
    assert value["model_status"] == "BASE_RATE_ONLY"
    assert value["base_rate_sample_size"] == 252
    assert value["base_rate"] == (63 + 1) / (252 + 2)


def test_empty_oof_is_an_explicit_non_acceptance_state() -> None:
    result = acceptance_metrics(pd.DataFrame(), event_id="cross_market_iv_jump_1d")
    assert result == {
        "accepted": False,
        "samples": 0,
        "reason": "INSUFFICIENT_CALIBRATED_OOF",
    }
