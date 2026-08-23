from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

SHANGHAI = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=1)
def _xshg() -> Any:
    # Use the calendar package's recorded bounds.  XSHG currently rejects an
    # invented far-future end date, which is preferable to fabricating sessions.
    return xcals.get_calendar("XSHG")


def _naive_session(value: str | date | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).tz_localize(None).normalize()


def surface_cutoff(session_date: str | date | pd.Timestamp) -> datetime:
    session = pd.Timestamp(session_date).date()
    return datetime.combine(session, time(14, 56, 59), tzinfo=SHANGHAI)


def settlement_observation_time(session_date: str | date | pd.Timestamp) -> datetime:
    session = pd.Timestamp(session_date).date()
    return datetime.combine(session, time(15, 0), tzinfo=SHANGHAI)


def settlement_known_at(session_date: str | date | pd.Timestamp) -> datetime:
    session = pd.Timestamp(session_date).date()
    return datetime.combine(session, time(23, 59, 59), tzinfo=SHANGHAI)


def research_bar_time(session_date: str | date | pd.Timestamp) -> datetime:
    session = pd.Timestamp(session_date).date()
    return datetime.combine(session, time(14, 56), tzinfo=SHANGHAI)


def expiry_timestamp(expiry: str | date | pd.Timestamp) -> datetime:
    value = pd.Timestamp(expiry).date()
    return datetime.combine(value, time(15, 0), tzinfo=SHANGHAI)


def year_fraction_act365f(start: datetime, end: datetime) -> float:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("ACT/365F timestamps must be timezone-aware")
    return (end - start).total_seconds() / (365.0 * 24.0 * 3600.0)


def next_session(
    sessions: pd.DatetimeIndex, session: str | pd.Timestamp, steps: int = 1
) -> pd.Timestamp:
    normalized = pd.DatetimeIndex(pd.to_datetime(sessions)).normalize().sort_values().unique()
    current = pd.Timestamp(session).normalize()
    position = normalized.searchsorted(current)
    if position >= len(normalized) or normalized[position] != current:
        raise ValueError(f"session is not in calendar: {current.date()}")
    target = position + steps
    if target < 0 or target >= len(normalized):
        raise IndexError("target session is outside the available calendar")
    return pd.Timestamp(normalized[target])


def decision_as_of(sessions: pd.DatetimeIndex, session: str | pd.Timestamp) -> datetime:
    following = next_session(sessions, session, 1)
    return datetime.combine(following.date(), time(9, 0), tzinfo=SHANGHAI)


def exchange_sessions_in_range(
    start: str | date | pd.Timestamp, end: str | date | pd.Timestamp
) -> pd.DatetimeIndex:
    return _xshg().sessions_in_range(_naive_session(start), _naive_session(end)).tz_localize(None)


def add_exchange_sessions(session: str | date | pd.Timestamp, steps: int) -> pd.Timestamp:
    value = _naive_session(session)
    calendar = _xshg()
    if not calendar.is_session(value):
        value = calendar.date_to_session(value, direction="previous")
    return pd.Timestamp(calendar.session_offset(value, steps)).tz_localize(None)


def next_exchange_session(session: str | date | pd.Timestamp) -> pd.Timestamp:
    return add_exchange_sessions(session, 1)


def exchange_decision_as_of(session: str | date | pd.Timestamp) -> datetime:
    following = next_exchange_session(session)
    return datetime.combine(following.date(), time(9, 0), tzinfo=SHANGHAI)
