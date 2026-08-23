from __future__ import annotations

import math
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from matshix.calendar import (
    add_exchange_sessions,
    exchange_decision_as_of,
    surface_cutoff,
)
from matshix.data.aetf import AetfPaths
from matshix.v3.authority import (
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    CARRIER_ID,
    ECONOMIC_INDEX_ID,
    HORIZON_SESSIONS,
    PATH_HORIZON_SESSIONS,
    UNDERLYING_SYMBOL,
)

MORNING_ENDPOINTS = tuple(
    (pd.Timestamp("2000-01-01 09:30") + pd.Timedelta(minutes=5 * value)).strftime("%H:%M:%S")
    for value in range(25)
)
AFTERNOON_ENDPOINTS = tuple(
    (pd.Timestamp("2000-01-01 13:05") + pd.Timedelta(minutes=5 * value)).strftime("%H:%M:%S")
    for value in range(24)
)
EXPECTED_ENDPOINTS = MORNING_ENDPOINTS + AFTERNOON_ENDPOINTS
EXPECTED_INTRADAY_RETURNS = 48


def extract_etf_minutes(
    paths: AetfPaths, *, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Read only the frozen 510300 ETF minute and adjustment inputs."""

    paths.validate()
    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    connection.execute("SET preserve_insertion_order TO false")
    try:
        frame = connection.execute(
            """
            WITH daily AS (
                SELECT code, date, adj_factor
                FROM read_parquet(?, union_by_name=true)
                WHERE date BETWEEN ? AND ?
                  AND code = ?
            )
            SELECT
                m.code AS underlying_symbol,
                m.date AS session_date,
                m.trade_time,
                m.close,
                d.adj_factor
            FROM read_parquet(?, union_by_name=true) AS m
            JOIN daily AS d ON d.code = m.code AND d.date = m.date
            WHERE m.date BETWEEN ? AND ?
              AND m.code = ?
            """,
            [
                paths.etf_daily,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                UNDERLYING_SYMBOL,
                paths.etf_minutes,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                UNDERLYING_SYMBOL,
            ],
        ).fetchdf()
    finally:
        connection.close()
    frame["carrier_id"] = CARRIER_ID
    frame["economic_index_id"] = ECONOMIC_INDEX_ID
    frame["session_date"] = pd.to_datetime(frame["session_date"].astype(str), format="%Y%m%d")
    frame["event_time"] = pd.to_datetime(frame["trade_time"])
    frame["time"] = frame["event_time"].dt.strftime("%H:%M:%S")
    frame["adjusted_mark"] = pd.to_numeric(frame["close"]) * pd.to_numeric(frame["adj_factor"])
    return frame.sort_values(["session_date", "event_time"], kind="stable").reset_index(drop=True)


def build_daily_realized_inputs(
    minutes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, np.ndarray]]:
    """Build daily adjusted variance without Q, H4, weather, or strategy inputs."""

    required = {"session_date", "time", "adjusted_mark", "adj_factor"}
    missing = required - set(minutes.columns)
    if missing:
        raise ValueError(f"minute input missing columns: {sorted(missing)}")
    frame = minutes.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["adjusted_mark"] = pd.to_numeric(frame["adjusted_mark"], errors="coerce")
    frame["adj_factor"] = pd.to_numeric(frame["adj_factor"], errors="coerce")
    if frame.duplicated(["session_date", "time"]).any():
        raise ValueError("duplicate 510300 session/minute rows are not allowed")

    daily_records: list[dict[str, Any]] = []
    path_marks: dict[pd.Timestamp, np.ndarray] = {}
    prior_close: tuple[pd.Timestamp, float, float] | None = None
    for session, group in frame.groupby("session_date", sort=True):
        session_value = pd.Timestamp(session).normalize()
        marks = {
            str(row["time"]): float(row["adjusted_mark"])
            for row in group.to_dict(orient="records")
            if row["adjusted_mark"] is not None
            and np.isfinite(row["adjusted_mark"])
            and float(row["adjusted_mark"]) > 0
        }
        factors = pd.to_numeric(group["adj_factor"], errors="coerce").dropna().unique()
        factor = float(factors[0]) if len(factors) == 1 and factors[0] > 0 else math.nan
        endpoint_values = [marks.get(value) for value in EXPECTED_ENDPOINTS]
        valid_endpoints = all(value is not None and np.isfinite(value) for value in endpoint_values)
        intraday_returns: list[float] = []
        if valid_endpoints:
            morning = [float(marks[value]) for value in MORNING_ENDPOINTS]
            afternoon = [float(marks[value]) for value in AFTERNOON_ENDPOINTS]
            intraday_returns.extend(
                math.log(current / previous)
                for previous, current in zip(morning[:-1], morning[1:], strict=True)
            )
            intraday_returns.append(math.log(afternoon[0] / morning[-1]))
            intraday_returns.extend(
                math.log(current / previous)
                for previous, current in zip(afternoon[:-1], afternoon[1:], strict=True)
            )

        expected_prior = add_exchange_sessions(session_value, -1)
        overnight: float | None = None
        factor_change = False
        if (
            prior_close is not None
            and prior_close[0] == expected_prior
            and "09:30:00" in marks
            and np.isfinite(factor)
        ):
            overnight = math.log(float(marks["09:30:00"]) / prior_close[1])
            factor_change = not math.isclose(factor, prior_close[2], rel_tol=0.0, abs_tol=1e-12)
        valid = bool(
            len(intraday_returns) == EXPECTED_INTRADAY_RETURNS
            and overnight is not None
            and np.isfinite(overnight)
            and np.isfinite(factor)
            and "15:00:00" in marks
        )
        issues: list[str] = []
        if not valid_endpoints:
            issues.append("MISSING_5M_ENDPOINT")
        if overnight is None:
            issues.append("MISSING_OVERNIGHT_INPUT")
        if not np.isfinite(factor):
            issues.append("INVALID_ADJ_FACTOR")
        if "15:00:00" not in marks:
            issues.append("MISSING_1500_MARK")
        intraday_variance = (
            float(np.square(np.asarray(intraday_returns, dtype=float)).sum()) if valid else math.nan
        )
        overnight_variance = (
            float(overnight * overnight) if valid and overnight is not None else math.nan
        )
        daily_records.append(
            {
                "session_date": session_value,
                "carrier_id": CARRIER_ID,
                "economic_index_id": ECONOMIC_INDEX_ID,
                "mark_0930": marks.get("09:30:00"),
                "mark_1456": marks.get("14:56:00"),
                "mark_1500": marks.get("15:00:00"),
                "prior_mark_1500": None if prior_close is None else prior_close[1],
                "adj_factor": factor,
                "prior_adj_factor": None if prior_close is None else prior_close[2],
                "daily_intraday_variance": intraday_variance,
                "daily_overnight_variance": overnight_variance,
                "daily_total_variance": intraday_variance + overnight_variance
                if valid
                else math.nan,
                "overnight_log_return": overnight,
                "valid_bar_count": len(intraday_returns),
                "expected_bar_count": EXPECTED_INTRADAY_RETURNS,
                "corporate_action_status": "ADJUSTED_FACTOR_CHANGE"
                if factor_change
                else "NO_FACTOR_CHANGE",
                "daily_status": "OK" if valid else "CENSORED",
                "issues": "|".join(issues),
                "authority_version": AUTHORITY_VERSION,
                "authority_sha256": AUTHORITY_SHA256,
            }
        )
        if valid_endpoints:
            path_marks[session_value] = np.asarray(endpoint_values, dtype=float)
        close = marks.get("15:00:00")
        if close is not None and np.isfinite(factor):
            prior_close = (session_value, float(close), factor)
    return pd.DataFrame(daily_records), path_marks


def _target_sessions(forecast: pd.Timestamp, horizon: int) -> list[pd.Timestamp]:
    return [add_exchange_sessions(forecast, step) for step in range(1, horizon + 1)]


def build_outcome_ledger(
    daily: pd.DataFrame,
    path_marks: dict[pd.Timestamp, np.ndarray],
    *,
    forecast_sessions: pd.DatetimeIndex,
) -> pd.DataFrame:
    daily_frame = daily.copy()
    daily_frame["session_date"] = pd.to_datetime(daily_frame["session_date"]).dt.normalize()
    by_session = {
        pd.Timestamp(row["session_date"]): row for row in daily_frame.to_dict(orient="records")
    }
    rows: list[dict[str, Any]] = []
    for forecast_value in forecast_sessions:
        forecast = pd.Timestamp(forecast_value).normalize()
        h20_sessions = _target_sessions(forecast, HORIZON_SESSIONS)
        h10_sessions = h20_sessions[:PATH_HORIZON_SESSIONS]
        target_end = h20_sessions[-1]
        base = by_session.get(forecast)
        target_rows = [by_session.get(value) for value in h20_sessions]
        primary_issue: str | None = None
        if base is None or base.get("mark_1500") is None:
            primary_issue = "MISSING_FORECAST_MARK"
        elif any(value is None for value in target_rows):
            primary_issue = "INCOMPLETE_TARGET_WINDOW"
        elif any(value is not None and value.get("daily_status") != "OK" for value in target_rows):
            primary_issue = "CENSORED_TARGET_DAY"

        h10_paths = [path_marks.get(value) for value in h10_sessions]
        path_issue: str | None = None
        if base is None or base.get("mark_1500") is None:
            path_issue = "MISSING_FORECAST_MARK"
        elif any(value is None for value in h10_paths):
            path_issue = "INCOMPLETE_H10_PATH_WINDOW"

        common: dict[str, Any] = {
            "forecast_session": forecast,
            "feature_cutoff_session": add_exchange_sessions(forecast, -1),
            "observation_time": surface_cutoff(forecast),
            "known_at": surface_cutoff(forecast),
            "consumer_decision_as_of": exchange_decision_as_of(forecast),
            "target_start_session": h20_sessions[0],
            "target_end_session": target_end,
            "outcome_available_at": exchange_decision_as_of(target_end),
            "carrier_id": CARRIER_ID,
            "economic_index_id": ECONOMIC_INDEX_ID,
            "horizon_sessions": HORIZON_SESSIONS,
            "unit": "ANNUALIZED_VARIANCE",
            "evidence_kind": "RETROSPECTIVE_DEVELOPMENT",
            "evidence_tier": "RESEARCH_ONLY",
            "authority_version": AUTHORITY_VERSION,
            "authority_sha256": AUTHORITY_SHA256,
        }
        if primary_issue is None:
            complete_rows = [value for value in target_rows if value is not None]
            intraday = sum(float(value["daily_intraday_variance"]) for value in complete_rows)
            overnight = sum(float(value["daily_overnight_variance"]) for value in complete_rows)
            rv_intraday = 252.0 / HORIZON_SESSIONS * intraday
            rv_overnight = 252.0 / HORIZON_SESSIONS * overnight
            variance = rv_intraday + rv_overnight
            primary_status = "OBSERVED"
            valid_bar_count = sum(int(value["valid_bar_count"]) for value in complete_rows)
            action_status = (
                "ADJUSTED_FACTOR_CHANGE"
                if any(
                    value["corporate_action_status"] == "ADJUSTED_FACTOR_CHANGE"
                    for value in complete_rows
                )
                else "NO_FACTOR_CHANGE"
            )
        else:
            rv_intraday = math.nan
            rv_overnight = math.nan
            variance = math.nan
            primary_status = "CENSORED"
            valid_bar_count = 0
            action_status = None

        if path_issue is None:
            assert base is not None
            complete_paths = [value for value in h10_paths if value is not None]
            frozen_mark = float(base["mark_1500"])
            moves = np.log(np.concatenate(complete_paths) / frozen_mark)
            max_up = max(float(moves.max()), 0.0)
            max_down = max(float(-moves.min()), 0.0)
            path_status = "OBSERVED"
        else:
            max_up = math.nan
            max_down = math.nan
            path_status = "CENSORED"
        issues = "|".join(value for value in (primary_issue, path_issue) if value is not None)
        rows.append(
            {
                **common,
                "rv_variance_h20": variance,
                "rv_intraday_h20": rv_intraday,
                "rv_overnight_h20": rv_overnight,
                "max_up_log_move_h10": max_up,
                "max_down_log_move_h10": max_down,
                "valid_bar_count": valid_bar_count,
                "expected_bar_count": HORIZON_SESSIONS * EXPECTED_INTRADAY_RETURNS,
                "corporate_action_status": action_status,
                "outcome_status": primary_status,
                "h10_path_status": path_status,
                "issues": issues,
            }
        )
    return pd.DataFrame(rows).sort_values("forecast_session", kind="stable").reset_index(drop=True)
