from __future__ import annotations

import math

import pandas as pd
import pytest

from matshix.calendar import exchange_sessions_in_range
from matshix.v2.authority import EXPECTED_LISTING_DATES, coverage_regime
from matshix.v2.outcomes import (
    AFTERNOON_ENDPOINTS,
    EXPECTED_INTRADAY_RETURNS,
    MORNING_ENDPOINTS,
    build_daily_realized_inputs,
    build_realized_outcome_ledger,
)


def _minute_day(
    session: pd.Timestamp,
    carrier: str,
    *,
    start_mark: float,
    step: float,
    factor: float = 1.0,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    endpoints = MORNING_ENDPOINTS + AFTERNOON_ENDPOINTS
    for position, time in enumerate(endpoints):
        mark = start_mark * math.exp(step * position)
        rows.append(
            {
                "session_date": session,
                "carrier_id": carrier,
                "time": time,
                "adjusted_mark": mark,
                "adj_factor": factor,
            }
        )
    rows.append(
        {
            "session_date": session,
            "carrier_id": carrier,
            "time": "14:56:00",
            "adjusted_mark": start_mark * math.exp(step * 47),
            "adj_factor": factor,
        }
    )
    return rows


def test_daily_variance_has_48_intraday_returns_and_one_overnight() -> None:
    sessions = exchange_sessions_in_range("2023-06-01", "2023-06-02")
    rows = _minute_day(sessions[0], "SSE50_510050", start_mark=1.0, step=0.001)
    rows += _minute_day(sessions[1], "SSE50_510050", start_mark=1.05, step=0.001)
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    second = daily.iloc[1]
    expected_overnight = math.log(1.05 / math.exp(0.001 * 48))
    assert second["valid_bar_count"] == EXPECTED_INTRADAY_RETURNS
    assert second["daily_intraday_variance"] == pytest.approx(48 * 0.001**2)
    assert second["daily_overnight_variance"] == pytest.approx(expected_overnight**2)
    assert len(paths[("SSE50_510050", sessions[1])]) == 49


def test_missing_endpoint_censors_daily_input() -> None:
    session = pd.Timestamp("2023-06-05")
    rows = _minute_day(session, "SSE50_510050", start_mark=1.0, step=0.001)
    rows = [row for row in rows if row["time"] != "10:00:00"]
    daily, _ = build_daily_realized_inputs(pd.DataFrame(rows))
    assert daily.iloc[0]["daily_status"] == "CENSORED"
    assert "MISSING_5M_ENDPOINT" in daily.iloc[0]["issues"]


def test_outcome_window_is_exchange_session_based_and_mirrors_path() -> None:
    all_sessions = exchange_sessions_in_range("2023-05-31", "2023-07-14")
    rows: list[dict[str, object]] = []
    for position, session in enumerate(all_sessions):
        rows += _minute_day(
            session,
            "SSE50_510050",
            start_mark=1.0,
            step=0.0001 * (position + 1),
        )
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    forecasts = exchange_sessions_in_range("2023-06-05", "2023-06-05")
    ledger, _ = build_realized_outcome_ledger(
        daily,
        paths,
        forecast_sessions=forecasts,
        listing_dates=EXPECTED_LISTING_DATES,
    )
    h5 = ledger.loc[
        ledger["carrier_id"].eq("SSE50_510050") & ledger["horizon_sessions"].eq(5)
    ].iloc[0]
    expected = exchange_sessions_in_range("2023-06-06", "2023-06-12")
    assert h5["target_start_session"] == expected[0]
    assert h5["target_end_session"] == expected[-1]
    assert h5["max_up_log_move_h"] >= 0
    assert h5["max_down_log_move_h"] >= 0
    assert pd.isna(h5["upside_path_breach_h"])
    assert h5["q_horizon_status"] == "NOT_BUILT"


def test_reciprocal_path_fixture_exchanges_up_and_down() -> None:
    all_sessions = exchange_sessions_in_range("2023-05-31", "2023-07-14")
    rows: list[dict[str, object]] = []
    for position, session in enumerate(all_sessions):
        step = 0.0001 * (position + 1)
        rows += _minute_day(session, "SSE50_510050", start_mark=1.0, step=step)
        rows += _minute_day(session, "CSI300_510300", start_mark=1.0, step=-step)
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    ledger, _ = build_realized_outcome_ledger(
        daily,
        paths,
        forecast_sessions=exchange_sessions_in_range("2023-06-05", "2023-06-05"),
        listing_dates=EXPECTED_LISTING_DATES,
    )
    h5 = ledger.loc[ledger["horizon_sessions"].eq(5)].set_index("carrier_id")
    assert h5.loc["SSE50_510050", "max_up_log_move_h"] == pytest.approx(
        h5.loc["CSI300_510300", "max_down_log_move_h"]
    )
    assert h5.loc["SSE50_510050", "max_down_log_move_h"] == pytest.approx(
        h5.loc["CSI300_510300", "max_up_log_move_h"]
    )


def test_data_after_target_end_cannot_change_frozen_outcome() -> None:
    all_sessions = exchange_sessions_in_range("2023-05-31", "2023-07-31")
    forecast = pd.Timestamp("2023-06-05")
    target_end = pd.Timestamp("2023-06-12")
    base_rows: list[dict[str, object]] = []
    changed_rows: list[dict[str, object]] = []
    for session in all_sessions:
        base_rows += _minute_day(session, "SSE50_510050", start_mark=1.0, step=0.0002)
        changed_rows += _minute_day(
            session,
            "SSE50_510050",
            start_mark=10.0 if session > target_end else 1.0,
            step=0.01 if session > target_end else 0.0002,
        )
    frozen: list[pd.Series] = []
    for rows in (base_rows, changed_rows):
        daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
        ledger, _ = build_realized_outcome_ledger(
            daily,
            paths,
            forecast_sessions=pd.DatetimeIndex([forecast]),
            listing_dates=EXPECTED_LISTING_DATES,
        )
        frozen.append(
            ledger.loc[
                ledger["carrier_id"].eq("SSE50_510050") & ledger["horizon_sessions"].eq(5)
            ].iloc[0]
        )
    fields = [
        "rv_variance_h",
        "rv_intraday_h",
        "rv_overnight_h",
        "max_up_log_move_h",
        "max_down_log_move_h",
        "close_to_close_return_h",
        "overnight_gap_max_h",
    ]
    assert frozen[0][fields].to_dict() == frozen[1][fields].to_dict()


def test_date_and_overlap_clusters_are_deterministic() -> None:
    all_sessions = exchange_sessions_in_range("2023-05-31", "2023-07-31")
    rows: list[dict[str, object]] = []
    for session in all_sessions:
        rows += _minute_day(session, "SSE50_510050", start_mark=1.0, step=0.0002)
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    forecasts = exchange_sessions_in_range("2023-06-05", "2023-06-06")
    first, _ = build_realized_outcome_ledger(
        daily,
        paths,
        forecast_sessions=forecasts,
        listing_dates=EXPECTED_LISTING_DATES,
    )
    second, _ = build_realized_outcome_ledger(
        daily,
        paths,
        forecast_sessions=forecasts,
        listing_dates=EXPECTED_LISTING_DATES,
    )
    pd.testing.assert_series_equal(first["date_cluster_id"], second["date_cluster_id"])
    pd.testing.assert_series_equal(first["overlap_cluster_id"], second["overlap_cluster_id"])
    same_date = first.loc[first["forecast_session"].eq(forecasts[0]), "date_cluster_id"]
    assert same_date.nunique() == 1
    h20 = first.loc[first["carrier_id"].eq("SSE50_510050") & first["horizon_sessions"].eq(20)]
    assert h20["overlap_cluster_id"].nunique() == 1


def test_not_listed_and_incomplete_tail_are_not_zero() -> None:
    sessions = exchange_sessions_in_range("2023-06-01", "2023-06-02")
    rows: list[dict[str, object]] = []
    for session in sessions:
        rows += _minute_day(session, "SSE50_510050", start_mark=1.0, step=0.001)
    daily, paths = build_daily_realized_inputs(pd.DataFrame(rows))
    ledger, _ = build_realized_outcome_ledger(
        daily,
        paths,
        forecast_sessions=exchange_sessions_in_range("2023-06-02", "2023-06-02"),
        listing_dates=EXPECTED_LISTING_DATES,
    )
    star = ledger.loc[ledger["carrier_id"].eq("STAR50_588000")]
    assert set(star["label_status"]) == {"NOT_LISTED"}
    assert star["rv_variance_h"].isna().all()
    sse = ledger.loc[ledger["carrier_id"].eq("SSE50_510050")]
    assert set(sse["label_status"]) == {"CENSORED"}
    assert sse["rv_variance_h"].isna().all()


def test_authority_era_transition_is_exact() -> None:
    assert coverage_regime("2023-06-04") == "ERA_C_50_300_500"
    assert coverage_regime("2023-06-05") == "ERA_D_FOUR_CARRIERS"
