from __future__ import annotations

import math

import pandas as pd
import pytest

from matshix.calendar import add_exchange_sessions, exchange_sessions_in_range
from matshix.v3.outcomes import (
    AFTERNOON_ENDPOINTS,
    EXPECTED_INTRADAY_RETURNS,
    MORNING_ENDPOINTS,
    build_daily_realized_inputs,
    build_outcome_ledger,
)


def _minute_day(
    session: pd.Timestamp,
    *,
    start_mark: float,
    step: float,
    factor: float = 1.0,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for position, time in enumerate(MORNING_ENDPOINTS + AFTERNOON_ENDPOINTS):
        rows.append(
            {
                "session_date": session,
                "time": time,
                "adjusted_mark": start_mark * math.exp(step * position),
                "adj_factor": factor,
            }
        )
    rows.append(
        {
            "session_date": session,
            "time": "14:56:00",
            "adjusted_mark": start_mark * math.exp(step * 47),
            "adj_factor": factor,
        }
    )
    return rows


def test_v3_daily_variance_freezes_lunch_overnight_and_adjusted_coordinate() -> None:
    sessions = exchange_sessions_in_range("2023-06-01", "2023-06-02")
    rows = _minute_day(sessions[0], start_mark=1.0, step=0.001, factor=1.0)
    rows += _minute_day(sessions[1], start_mark=1.05, step=0.001, factor=2.0)
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    second = daily.iloc[1]
    expected_overnight = math.log(1.05 / math.exp(0.001 * 48))
    assert second["valid_bar_count"] == EXPECTED_INTRADAY_RETURNS
    assert second["daily_intraday_variance"] == pytest.approx(48 * 0.001**2)
    assert second["daily_overnight_variance"] == pytest.approx(expected_overnight**2)
    assert second["daily_total_variance"] == pytest.approx(
        48 * 0.001**2 + expected_overnight**2
    )
    assert second["corporate_action_status"] == "ADJUSTED_FACTOR_CHANGE"
    assert len(paths[sessions[1]]) == 49


def test_v3_missing_five_minute_endpoint_censors_whole_day() -> None:
    session = pd.Timestamp("2023-06-05")
    rows = _minute_day(session, start_mark=1.0, step=0.001)
    rows = [row for row in rows if row["time"] != "10:00:00"]
    daily, _ = build_daily_realized_inputs(pd.DataFrame(rows))
    assert daily.iloc[0]["daily_status"] == "CENSORED"
    assert pd.isna(daily.iloc[0]["daily_total_variance"])
    assert "MISSING_5M_ENDPOINT" in daily.iloc[0]["issues"]


def _outcome_fixture() -> tuple[pd.DataFrame, dict[pd.Timestamp, object], pd.Timestamp]:
    sessions = exchange_sessions_in_range("2023-05-31", "2023-08-31")
    rows: list[dict[str, object]] = []
    for position, session in enumerate(sessions):
        rows += _minute_day(
            session,
            start_mark=1.0 + 0.0005 * position,
            step=0.00005 * (1 + position % 7),
        )
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    return daily, paths, pd.Timestamp("2023-06-05")


def test_v3_h20_outcome_uses_exchange_sessions_and_has_continuous_h10_facts() -> None:
    daily, paths, forecast = _outcome_fixture()
    ledger = build_outcome_ledger(
        daily,
        paths,
        forecast_sessions=pd.DatetimeIndex([forecast]),
    )
    row = ledger.iloc[0]
    target = [add_exchange_sessions(forecast, step) for step in range(1, 21)]
    assert len(target) == 20
    assert row["target_start_session"] == target[0]
    assert row["target_end_session"] == target[-1]
    assert row["outcome_status"] == "OBSERVED"
    assert row["valid_bar_count"] == 20 * EXPECTED_INTRADAY_RETURNS
    assert row["rv_variance_h20"] > 0
    assert row["max_up_log_move_h10"] >= 0
    assert row["max_down_log_move_h10"] >= 0


def test_data_after_target_end_cannot_change_frozen_v3_outcome() -> None:
    daily, paths, forecast = _outcome_fixture()
    first = build_outcome_ledger(
        daily,
        paths,
        forecast_sessions=pd.DatetimeIndex([forecast]),
    ).iloc[0]
    target_end = pd.Timestamp(first["target_end_session"])
    changed_daily = daily.copy()
    future = pd.to_datetime(changed_daily["session_date"]).gt(target_end)
    changed_daily.loc[future, "daily_total_variance"] = 99.0
    changed_paths = dict(paths)
    for session in list(changed_paths):
        if session > target_end:
            changed_paths[session] = changed_paths[session] * 100.0
    second = build_outcome_ledger(
        changed_daily,
        changed_paths,
        forecast_sessions=pd.DatetimeIndex([forecast]),
    ).iloc[0]
    fields = [
        "rv_variance_h20",
        "rv_intraday_h20",
        "rv_overnight_h20",
        "max_up_log_move_h10",
        "max_down_log_move_h10",
    ]
    assert first[fields].to_dict() == second[fields].to_dict()
