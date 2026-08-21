from __future__ import annotations

import html
import math
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from matshix.serialization import file_hash, write_json
from matshix.surface.black import forward_delta

INITIAL_CAPITAL = 1_000_000.0
MULTIPLIER = 10_000.0
RISK_BUDGET = 0.08
MARGIN_CAP = 0.35
PARTICIPATION_RATE = 0.05
COMMON_START = pd.Timestamp("2024-06-17")
FILL_SCENARIOS = ("VWAP_2TICK", "VWAP_RANGE_25", "BAR_EXTREME")
FEE_SCENARIOS = {
    "OFFICIAL_MINIMUM": 0.0,
    "BROKER_PLUS_2": 2.0,
    "BROKER_PLUS_5": 5.0,
}
STRATEGIES = ("ETF_BH", "SV_STATIC", "SV_MATSHIX")
STRATEGY_LABELS = {
    "ETF_BH": "510300ETF 全仓持有",
    "SV_STATIC": "静态 0.5 风险单位 ShortVol",
    "SV_MATSHIX": "MatSHIX 动态 ShortVol",
}
PHASE_UNITS = {
    "CALM_POSITIVE_VRP": 1.0,
    "BALANCED_MARKET": 0.75,
    "REPAIR_IN_PROGRESS": 0.5,
    "DOWNSIDE_TAIL_RICH": 0.25,
    "UPSIDE_CONVEXITY_PRICED": 0.25,
    "FRAGMENTED_TRANSITION": 0.25,
    "LOCAL_STYLE_PRESSURE": 0.25,
    "BLUE_CHIP_PRESSURE": 0.0,
    "BROAD_PRESSURE": 0.0,
    "BROAD_PERSISTENT_PRESSURE": 0.0,
    "LOCALIZED_ACUTE_STRESS": 0.0,
    "SYSTEMIC_ACUTE_STRESS": 0.0,
    "UNKNOWN": 0.0,
}
LEG_NAMES = ("short_put", "long_put", "short_call", "long_call")


@dataclass(frozen=True)
class BacktestArtifacts:
    report_path: Path
    daily_ledger_path: Path
    trade_ledger_path: Path
    rejection_ledger_path: Path
    html_path: Path
    report: dict[str, Any]


@dataclass
class Position:
    codes: dict[str, str]
    strikes: dict[str, float]
    ticks: dict[str, float]
    expiry: pd.Timestamp
    quantity: int
    entry_date: pd.Timestamp
    entry_cashflow_per_combo: float
    max_loss_per_combo: float
    entry_fees: float
    accumulated_fees: float
    entry_fee_per_combo: float
    risk_unit: float
    stop_pending: bool = False


def _atomic_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _date_column(frame: pd.DataFrame, column: str = "session_date") -> pd.DataFrame:
    result = frame.copy()
    result[column] = pd.to_datetime(result[column]).dt.tz_localize(None).dt.normalize()
    return result


def _decision_date(frame: pd.DataFrame) -> pd.Series:
    value = pd.to_datetime(frame["decision_as_of"], utc=True, errors="coerce")
    return value.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize()


def raw_dynamic_unit(row: pd.Series) -> tuple[float, str]:
    """Frozen MatSHIX phase map plus all hard caps, using only prior-session state."""
    if str(row.get("global_status", "UNKNOWN")) != "OK":
        return 0.0, "GLOBAL_NOT_OK"
    phase = str(row.get("phase", "UNKNOWN"))
    unit = PHASE_UNITS.get(phase, 0.0)
    if unit <= 0:
        return 0.0, f"PHASE_{phase}"
    if str(row.get("local_status", "UNKNOWN")) != "OK":
        return 0.0, "CSI300_NOT_OK"
    compensation = str(row.get("insurance_compensation", "UNKNOWN"))
    if compensation in {"THIN", "UNKNOWN"}:
        return 0.0, f"COMPENSATION_{compensation}"
    vrp = pd.to_numeric(pd.Series([row.get("vrp_ewma94")]), errors="coerce").iloc[0]
    if pd.isna(vrp) or float(vrp) <= 0:
        return 0.0, "VRP_NOT_POSITIVE"

    def finite_or_zero(value: Any) -> float:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        return 0.0 if pd.isna(numeric) else float(numeric)

    pressure = finite_or_zero(row.get("pressure_score"))
    local_axes = [
        finite_or_zero(row.get(name))
        for name in ("index_pressure", "shock", "down_tail", "persistence")
    ]
    if bool(row.get("hard_acute", False)) or pressure >= 85 or max(local_axes) >= 85:
        return 0.0, "ACUTE_CAP_ZERO"
    reasons = ["PHASE_MAP"]
    if compensation == "NORMAL":
        unit = min(unit, 0.5)
        reasons.append("NORMAL_COMP_CAP")
    if str(row.get("direction", "UNKNOWN")) == "RISING" or pressure >= 70:
        unit = min(unit, 0.25)
        reasons.append("GLOBAL_PRESSURE_CAP")
    if local_axes[0] >= 70 or local_axes[1] >= 65 or local_axes[2] >= 75 or local_axes[3] >= 75:
        unit = min(unit, 0.25)
        reasons.append("CSI300_PRESSURE_CAP")
    return unit, "+".join(reasons)


def confirm_risk_increases(raw_units: pd.Series) -> pd.Series:
    """Decrease immediately; require two consecutive decision days for an increase."""
    confirmed: list[float] = []
    current = 0.0
    previous_raw = 0.0
    for value in raw_units.fillna(0.0).astype(float):
        if value <= current:
            current = value
        elif previous_raw >= value:
            current = value
        confirmed.append(current)
        previous_raw = value
    return pd.Series(confirmed, index=raw_units.index, dtype=float)


def option_fill_price(
    *,
    side: Literal["BUY", "SELL"],
    scenario: str,
    vwap: float,
    low: float,
    high: float,
    tick: float,
) -> float:
    if scenario == "VWAP_2TICK":
        adjustment = 2.0 * tick
        return max(tick, vwap + adjustment if side == "BUY" else vwap - adjustment)
    if scenario == "VWAP_RANGE_25":
        adjustment = max(2.0 * tick, 0.25 * max(high - low, 0.0))
        return max(tick, vwap + adjustment if side == "BUY" else vwap - adjustment)
    if scenario == "BAR_EXTREME":
        return max(tick, high if side == "BUY" else low)
    raise ValueError(f"Unknown fill scenario: {scenario}")


def _load_signal_calendar(processed: Path, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    states = pd.read_parquet(processed / "daily_market_state.parquet")
    states["decision_date"] = _decision_date(states)
    states = states.rename(
        columns={
            "data_status": "global_status",
            "primary_phase": "phase",
            "session_date": "signal_session_date",
        }
    )
    state_cols = [
        "decision_date",
        "signal_session_date",
        "global_status",
        "phase",
        "pressure_level",
        "direction",
        "pressure_score",
        "hard_acute",
    ]
    states = states[state_cols].drop_duplicates("decision_date", keep="last")

    features = pd.read_parquet(processed / "economic_index_feature.parquet")
    features = features.loc[features["economic_index_id"].eq("CSI300")].copy()
    features["decision_date"] = _decision_date(features)
    features = features[["decision_date", "insurance_compensation", "vrp_ewma94"]].drop_duplicates(
        "decision_date", keep="last"
    )

    local = pd.read_parquet(processed / "economic_index_state.parquet")
    local = local.loc[local["economic_index_id"].eq("CSI300")].copy()
    local["decision_date"] = _decision_date(local)
    local = local.rename(columns={"data_status": "local_status"})
    local = local[
        [
            "decision_date",
            "local_status",
            "index_pressure",
            "shock",
            "down_tail",
            "persistence",
        ]
    ].drop_duplicates("decision_date", keep="last")

    calendar = pd.DataFrame({"session_date": sessions})
    calendar = calendar.merge(
        states, left_on="session_date", right_on="decision_date", how="left"
    ).drop(columns="decision_date")
    calendar = calendar.merge(
        features, left_on="session_date", right_on="decision_date", how="left"
    ).drop(columns="decision_date")
    calendar = calendar.merge(
        local, left_on="session_date", right_on="decision_date", how="left"
    ).drop(columns="decision_date")
    pairs = calendar.apply(raw_dynamic_unit, axis=1)
    calendar["raw_dynamic_unit"] = [item[0] for item in pairs]
    calendar["risk_reason"] = [item[1] for item in pairs]
    calendar["dynamic_unit"] = confirm_risk_increases(calendar["raw_dynamic_unit"])
    calendar["static_unit"] = 0.5
    calendar["phase"] = calendar["phase"].fillna("UNKNOWN")
    calendar["global_status"] = calendar["global_status"].fillna("UNKNOWN")
    calendar["local_status"] = calendar["local_status"].fillna("UNKNOWN")
    return calendar


def _extract_etf_minutes(connection: duckdb.DuckDBPyConnection, aetf_root: Path) -> pd.DataFrame:
    glob = str(aetf_root / "ETF/1m_etf/*/*.parquet")
    query = f"""
        SELECT strptime(date, '%Y%m%d')::DATE AS session_date,
               max(close) FILTER (WHERE right(trade_time, 8) = '09:35:00') AS spot_0935,
               sum(amount) FILTER (WHERE right(trade_time, 8) BETWEEN '09:36:00' AND '09:45:00')
                 / nullif(sum(vol) FILTER (WHERE right(trade_time, 8) BETWEEN '09:36:00' AND '09:45:00'), 0) AS entry_vwap,
               max(high) FILTER (WHERE right(trade_time, 8) BETWEEN '09:36:00' AND '09:45:00') AS entry_high,
               min(low) FILTER (WHERE right(trade_time, 8) BETWEEN '09:36:00' AND '09:45:00') AS entry_low
        FROM read_parquet('{glob}', union_by_name=true)
        WHERE code = '510300.SH' AND date BETWEEN '20230103' AND '20260605'
        GROUP BY date ORDER BY session_date
    """
    frame = connection.execute(query).fetchdf()
    return _date_column(frame)


def _standard_contracts(aetf_root: Path) -> pd.DataFrame:
    frame = pd.read_parquet(aetf_root / "OPTION/opt_basic.parquet")
    frame = frame.loc[
        frame["opt_code"].eq("OP510300.SH")
        & frame["per_unit"].eq(MULTIPLIER)
        & frame["opt_multiplier"].eq(MULTIPLIER)
        & ~frame["symbol"].astype(str).str.contains("A", regex=False)
    ].copy()
    for column in ("list_date", "maturity_date", "delist_date"):
        frame[column] = pd.to_datetime(
            frame[column], format="%Y%m%d", errors="coerce"
        ).dt.normalize()
    frame["exercise_price"] = pd.to_numeric(frame["exercise_price"], errors="coerce")
    frame["min_price_chg"] = pd.to_numeric(frame["min_price_chg"], errors="coerce")
    frame = frame.dropna(
        subset=["code", "call_put", "exercise_price", "list_date", "maturity_date"]
    )
    return frame


def _surface_map(processed: Path) -> dict[tuple[pd.Timestamp, pd.Timestamp], float]:
    frame = pd.read_parquet(processed / "carrier_expiry_surface.parquet")
    frame = frame.loc[frame["economic_index_id"].eq("CSI300")].copy()
    frame = _date_column(frame)
    frame["expiry"] = pd.to_datetime(frame["expiry"]).dt.normalize()
    frame["atm_iv"] = pd.to_numeric(frame["atm_iv"], errors="coerce") / 100.0
    frame = frame.loc[frame["atm_iv"].between(0.01, 3.0)]
    return {
        (cast(pd.Timestamp, row.session_date), cast(pd.Timestamp, row.expiry)): float(row.atm_iv)
        for row in frame.itertuples(index=False)
    }


def select_condor_candidates(
    sessions: pd.DataFrame,
    contracts: pd.DataFrame,
    surface: dict[tuple[pd.Timestamp, pd.Timestamp], float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    session_dates = pd.DatetimeIndex(sessions["session_date"])
    for index, row in enumerate(sessions.itertuples(index=False)):
        date = pd.Timestamp(row.session_date)
        spot = float(row.spot_0935) if pd.notna(row.spot_0935) else math.nan
        if index == 0 or not np.isfinite(spot) or spot <= 0:
            rejects.append(
                {"session_date": date, "stage": "SELECTION", "reason": "NO_LAGGED_SURFACE_OR_SPOT"}
            )
            continue
        previous = pd.Timestamp(session_dates[index - 1])
        active = contracts.loc[
            contracts["list_date"].le(date)
            & contracts["maturity_date"].ge(date)
            & contracts["call_put"].isin(["C", "P"])
        ].copy()
        if active.empty:
            rejects.append(
                {"session_date": date, "stage": "SELECTION", "reason": "NO_STANDARD_CONTRACT"}
            )
            continue
        active["dte"] = (active["maturity_date"] - date).dt.days
        expiries = active.loc[active["dte"].between(25, 45), ["maturity_date", "dte"]]
        if expiries.empty:
            rejects.append({"session_date": date, "stage": "SELECTION", "reason": "NO_25_45_DTE"})
            continue
        expiry_rows = expiries.drop_duplicates("maturity_date").copy()
        expiry_rows["distance"] = (expiry_rows["dte"] - 35).abs()
        expiry = pd.Timestamp(expiry_rows.sort_values(["distance", "dte"]).iloc[0]["maturity_date"])
        sigma = surface.get((previous, expiry))
        if sigma is None or not np.isfinite(sigma):
            rejects.append(
                {"session_date": date, "stage": "SELECTION", "reason": "NO_PRIOR_EXPIRY_IV"}
            )
            continue
        chain = active.loc[active["maturity_date"].eq(expiry)].copy()
        year_fraction = max((expiry - date).days / 365.2425, 1.0 / 365.2425)
        chain["delta"] = [
            forward_delta(
                option_type=str(kind),
                forward=spot,
                strike=float(strike),
                sigma=float(sigma),
                year_fraction=year_fraction,
            )
            for kind, strike in zip(chain["call_put"], chain["exercise_price"], strict=True)
        ]
        calls = chain.loc[
            chain["call_put"].eq("C")
            & chain["exercise_price"].gt(spot)
            & chain["delta"].abs().between(0.15, 0.25)
        ].sort_values("exercise_price")
        puts = chain.loc[
            chain["call_put"].eq("P")
            & chain["exercise_price"].lt(spot)
            & chain["delta"].abs().between(0.15, 0.25)
        ].sort_values("exercise_price")
        if calls.empty or puts.empty:
            rejects.append(
                {"session_date": date, "stage": "SELECTION", "reason": "NO_15_25_DELTA_SHORT"}
            )
            continue
        short_call = calls.iloc[(calls["delta"].abs() - 0.20).abs().argmin()]
        short_put = puts.iloc[(puts["delta"].abs() - 0.20).abs().argmin()]
        call_wings = chain.loc[
            chain["call_put"].eq("C")
            & chain["exercise_price"].gt(float(short_call["exercise_price"]))
        ].sort_values("exercise_price")
        put_wings = chain.loc[
            chain["call_put"].eq("P")
            & chain["exercise_price"].lt(float(short_put["exercise_price"]))
        ].sort_values("exercise_price", ascending=False)
        if len(call_wings) < 2 or len(put_wings) < 2:
            rejects.append(
                {
                    "session_date": date,
                    "stage": "SELECTION",
                    "reason": "FEWER_THAN_TWO_WING_STRIKES",
                }
            )
            continue
        long_call = call_wings.iloc[1]
        long_put = put_wings.iloc[1]
        net_delta = (
            -float(short_call["delta"])
            + float(long_call["delta"])
            - float(short_put["delta"])
            + float(long_put["delta"])
        )
        if abs(net_delta) > 0.10:
            rejects.append(
                {
                    "session_date": date,
                    "stage": "SELECTION",
                    "reason": "NET_DELTA_GT_0_10",
                    "value": net_delta,
                }
            )
            continue
        selected = {
            "short_put": short_put,
            "long_put": long_put,
            "short_call": short_call,
            "long_call": long_call,
        }
        result: dict[str, Any] = {
            "session_date": date,
            "signal_session_date": previous,
            "spot_0935": spot,
            "expiry": expiry,
            "dte": int((expiry - date).days),
            "lagged_atm_iv": sigma,
            "net_delta": net_delta,
        }
        for name, leg in selected.items():
            result[f"{name}_code"] = str(leg["code"])
            result[f"{name}_strike"] = float(leg["exercise_price"])
            result[f"{name}_delta"] = float(leg["delta"])
            result[f"{name}_tick"] = float(leg["min_price_chg"] or 0.0001)
        rows.append(result)
    return pd.DataFrame(rows), pd.DataFrame(rejects)


def _extract_option_windows(
    connection: duckdb.DuckDBPyConnection,
    aetf_root: Path,
    codes: pd.DataFrame,
) -> pd.DataFrame:
    connection.register("selected_codes", codes[["code"]].drop_duplicates())
    glob = str(aetf_root / "OPTION/1m_opt/*/*.parquet")
    query = f"""
        WITH bars AS (
          SELECT strptime(o.date, '%Y%m%d')::DATE AS session_date, o.code,
                 CASE
                   WHEN right(o.trade_time, 8) BETWEEN '09:36:00' AND '09:45:00' THEN 'OPEN_AM'
                   WHEN right(o.trade_time, 8) BETWEEN '13:31:00' AND '13:40:00' THEN 'EXIT_PM1'
                   WHEN right(o.trade_time, 8) BETWEEN '14:46:00' AND '14:55:00' THEN 'EXIT_PM2'
                 END AS fill_window,
                 o.high, o.low, o.vol, o.amount
          FROM read_parquet('{glob}', union_by_name=true) o
          INNER JOIN selected_codes c USING(code)
          WHERE o.date BETWEEN '20230103' AND '20260605'
            AND ((right(o.trade_time, 8) BETWEEN '09:36:00' AND '09:45:00')
              OR (right(o.trade_time, 8) BETWEEN '13:31:00' AND '13:40:00')
              OR (right(o.trade_time, 8) BETWEEN '14:46:00' AND '14:55:00'))
        )
        SELECT session_date, code, fill_window,
               count(*) FILTER (WHERE vol > 0) AS positive_minutes,
               sum(vol) FILTER (WHERE vol > 0) AS volume,
               sum(amount) FILTER (WHERE vol > 0) / nullif(sum(vol) FILTER (WHERE vol > 0), 0) / {MULTIPLIER} AS vwap,
               max(high) AS high, min(low) AS low
        FROM bars GROUP BY session_date, code, fill_window
        ORDER BY session_date, code, fill_window
    """
    frame = connection.execute(query).fetchdf()
    return _date_column(frame)


def _extract_option_marks(
    connection: duckdb.DuckDBPyConnection,
    aetf_root: Path,
    codes: pd.DataFrame,
) -> pd.DataFrame:
    connection.register("mark_codes", codes[["code"]].drop_duplicates())
    glob = str(aetf_root / "OPTION/1d_opt_price/*/*.parquet")
    query = f"""
        SELECT strptime(o.date, '%Y%m%d')::DATE AS session_date, o.code,
               o.settle, o.close
        FROM read_parquet('{glob}', union_by_name=true) o
        INNER JOIN mark_codes c USING(code)
        WHERE o.date BETWEEN '20230103' AND '20260605'
    """
    return _date_column(connection.execute(query).fetchdf())


def _window_lookup(frame: pd.DataFrame) -> dict[tuple[pd.Timestamp, str, str], dict[str, float]]:
    result: dict[tuple[pd.Timestamp, str, str], dict[str, float]] = {}
    for row in frame.itertuples(index=False):
        result[(pd.Timestamp(row.session_date), str(row.code), str(row.fill_window))] = {
            "positive_minutes": float(row.positive_minutes or 0.0),
            "volume": float(row.volume or 0.0),
            "vwap": float(row.vwap) if pd.notna(row.vwap) else math.nan,
            "high": float(row.high) if pd.notna(row.high) else math.nan,
            "low": float(row.low) if pd.notna(row.low) else math.nan,
        }
    return result


def _combo_fills(
    date: pd.Timestamp,
    codes: dict[str, str],
    ticks: dict[str, float],
    windows: dict[tuple[pd.Timestamp, str, str], dict[str, float]],
    *,
    window: str,
    scenario: str,
    action: Literal["OPEN", "CLOSE"],
) -> tuple[dict[str, float] | None, int, str | None]:
    prices: dict[str, float] = {}
    participation = math.inf
    for name in LEG_NAMES:
        bar = windows.get((date, codes[name], window))
        if bar is None:
            return None, 0, f"{window}_{name}_NO_BAR"
        if bar["positive_minutes"] < 2 or bar["volume"] < 20:
            return None, 0, f"{window}_{name}_LIQUIDITY"
        if not (
            np.isfinite(bar["vwap"])
            and np.isfinite(bar["low"])
            and np.isfinite(bar["high"])
            and bar["low"] - ticks[name] <= bar["vwap"] <= bar["high"] + ticks[name]
        ):
            return None, 0, f"{window}_{name}_VWAP_RANGE"
        is_long = name.startswith("long")
        side: Literal["BUY", "SELL"]
        if action == "OPEN":
            side = "BUY" if is_long else "SELL"
        else:
            side = "SELL" if is_long else "BUY"
        prices[name] = option_fill_price(
            side=side,
            scenario=scenario,
            vwap=bar["vwap"],
            low=bar["low"],
            high=bar["high"],
            tick=ticks[name],
        )
        participation = min(participation, math.floor(bar["volume"] * PARTICIPATION_RATE))
    return prices, int(participation), None


def _net_open_cashflow(prices: dict[str, float]) -> float:
    return MULTIPLIER * (
        prices["short_put"] + prices["short_call"] - prices["long_put"] - prices["long_call"]
    )


def _net_close_cashflow(prices: dict[str, float]) -> float:
    return MULTIPLIER * (
        prices["long_put"] + prices["long_call"] - prices["short_put"] - prices["short_call"]
    )


def _max_loss_per_combo(strikes: dict[str, float], credit: float) -> float:
    put_width = strikes["short_put"] - strikes["long_put"]
    call_width = strikes["long_call"] - strikes["short_call"]
    return max(max(put_width, call_width) * MULTIPLIER - credit, 1.0)


def _fees(quantity: int, *, action: Literal["OPEN", "CLOSE"], broker_fee: float) -> float:
    exchange_clearing = 1.6
    official_legs = 2 if action == "OPEN" else 4
    return quantity * (official_legs * exchange_clearing + 4 * broker_fee)


def _position_mark(
    position: Position,
    date: pd.Timestamp,
    marks: dict[tuple[pd.Timestamp, str], float],
    spot: float,
) -> tuple[float, str]:
    values: dict[str, float] = {}
    sources: list[str] = []
    for name in LEG_NAMES:
        value = marks.get((date, position.codes[name]))
        if value is not None and np.isfinite(value) and value >= 0:
            values[name] = value
            sources.append("SETTLE")
        else:
            strike = position.strikes[name]
            values[name] = (
                max(spot - strike, 0.0) if name.endswith("call") else max(strike - spot, 0.0)
            )
            sources.append("INTRINSIC_FALLBACK")
    liability = (
        MULTIPLIER
        * position.quantity
        * (values["long_put"] + values["long_call"] - values["short_put"] - values["short_call"])
    )
    source = "SETTLE" if set(sources) == {"SETTLE"} else "INTRINSIC_FALLBACK"
    return liability, source


def _candidate_record(row: pd.Series) -> tuple[dict[str, str], dict[str, float], dict[str, float]]:
    codes = {name: str(row[f"{name}_code"]) for name in LEG_NAMES}
    strikes = {name: float(row[f"{name}_strike"]) for name in LEG_NAMES}
    ticks = {name: float(row[f"{name}_tick"]) for name in LEG_NAMES}
    return codes, strikes, ticks


def simulate_shortvol(
    calendar: pd.DataFrame,
    candidates: pd.DataFrame,
    windows_frame: pd.DataFrame,
    marks_frame: pd.DataFrame,
    *,
    strategy: Literal["SV_STATIC", "SV_MATSHIX"],
    fill_scenario: str,
    broker_fee: float,
    risk_budget: float = RISK_BUDGET,
    initial_capital: float = INITIAL_CAPITAL,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidate_map = {
        pd.Timestamp(row.session_date): pd.Series(row._asdict())
        for row in candidates.itertuples(index=False)
    }
    windows = _window_lookup(windows_frame)
    marks = {
        (pd.Timestamp(row.session_date), str(row.code)): float(row.settle)
        if pd.notna(row.settle)
        else float(row.close)
        for row in marks_frame.itertuples(index=False)
        if pd.notna(row.settle) or pd.notna(row.close)
    }
    cash = float(initial_capital)
    position: Position | None = None
    daily: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    previous_nav = initial_capital
    total_fees = 0.0
    for calendar_row in calendar.itertuples(index=False):
        date = pd.Timestamp(calendar_row.session_date)
        target_unit = float(
            calendar_row.static_unit if strategy == "SV_STATIC" else calendar_row.dynamic_unit
        )
        action = "HOLD_CASH"
        exit_reason: str | None = None

        if position is not None:
            dte = (position.expiry - date).days
            if position.stop_pending:
                exit_reason = "RISK_STOP"
            elif dte <= 7:
                exit_reason = "DTE_7"
            elif target_unit <= 0:
                exit_reason = "RISK_UNIT_ZERO"
            elif not math.isclose(target_unit, position.risk_unit):
                exit_reason = "RISK_REBALANCE"
            if exit_reason is not None:
                exit_fill: dict[str, float] | None = None
                exit_window: str | None = None
                exit_quantity = 0
                last_error: str | None = None
                for window_name, scenario_name in (
                    ("OPEN_AM", fill_scenario),
                    ("EXIT_PM1", fill_scenario),
                    ("EXIT_PM2", "BAR_EXTREME"),
                ):
                    prices, capacity, error = _combo_fills(
                        date,
                        position.codes,
                        position.ticks,
                        windows,
                        window=window_name,
                        scenario=scenario_name,
                        action="CLOSE",
                    )
                    last_error = error
                    if prices is not None and capacity >= 1:
                        exit_fill, exit_window = prices, window_name
                        exit_quantity = min(position.quantity, capacity)
                        break
                if exit_fill is None and dte <= 0:
                    spot = float(calendar_row.etf_mark)
                    exit_fill = {
                        name: max(spot - position.strikes[name], 0.0)
                        if name.endswith("call")
                        else max(position.strikes[name] - spot, 0.0)
                        for name in LEG_NAMES
                    }
                    exit_window = "EXPIRY_INTRINSIC_SETTLEMENT"
                    exit_quantity = position.quantity
                if exit_fill is not None:
                    close_cashflow = _net_close_cashflow(exit_fill) * exit_quantity
                    fee = _fees(exit_quantity, action="CLOSE", broker_fee=broker_fee)
                    cash += close_cashflow - fee
                    total_fees += fee
                    realized = (
                        position.entry_cashflow_per_combo * exit_quantity
                        + close_cashflow
                        - position.entry_fee_per_combo * exit_quantity
                        - fee
                    )
                    trades.append(
                        {
                            "strategy": strategy,
                            "fill_scenario": fill_scenario,
                            "fee_scenario": broker_fee,
                            "entry_date": position.entry_date,
                            "exit_date": date,
                            "expiry": position.expiry,
                            "quantity": exit_quantity,
                            "exit_reason": exit_reason,
                            "exit_window": exit_window,
                            "gross_credit": position.entry_cashflow_per_combo * exit_quantity,
                            "realized_pnl": realized,
                            "fees": position.entry_fee_per_combo * exit_quantity + fee,
                            **position.codes,
                        }
                    )
                    position.quantity -= exit_quantity
                    position.accumulated_fees = position.entry_fee_per_combo * position.quantity
                    if position.quantity == 0:
                        action = f"EXIT_{exit_reason}"
                        position = None
                    else:
                        action = f"PARTIAL_EXIT_{exit_reason}"
                else:
                    action = "EXIT_UNFILLED"
                    rejects.append(
                        {
                            "session_date": date,
                            "strategy": strategy,
                            "stage": "EXIT",
                            "reason": last_error or "EXIT_UNFILLED",
                        }
                    )

        if position is None and target_unit > 0 and action != "EXIT_UNFILLED":
            candidate = candidate_map.get(date)
            if candidate is None:
                rejects.append(
                    {
                        "session_date": date,
                        "strategy": strategy,
                        "stage": "ENTRY",
                        "reason": "NO_CANDIDATE",
                    }
                )
            else:
                codes, strikes, ticks = _candidate_record(candidate)
                prices, capacity, error = _combo_fills(
                    date,
                    codes,
                    ticks,
                    windows,
                    window="OPEN_AM",
                    scenario=fill_scenario,
                    action="OPEN",
                )
                if prices is None:
                    rejects.append(
                        {
                            "session_date": date,
                            "strategy": strategy,
                            "stage": "ENTRY",
                            "reason": error,
                        }
                    )
                else:
                    credit = _net_open_cashflow(prices)
                    max_loss = _max_loss_per_combo(strikes, credit)
                    risk_quantity = math.floor(previous_nav * risk_budget * target_unit / max_loss)
                    margin_quantity = math.floor(previous_nav * MARGIN_CAP / max_loss)
                    quantity = max(0, min(risk_quantity, margin_quantity, capacity))
                    if credit <= 0 or quantity <= 0:
                        rejects.append(
                            {
                                "session_date": date,
                                "strategy": strategy,
                                "stage": "ENTRY",
                                "reason": "NONPOSITIVE_CREDIT_OR_ZERO_SIZE",
                            }
                        )
                    else:
                        fee = _fees(quantity, action="OPEN", broker_fee=broker_fee)
                        cash += credit * quantity - fee
                        total_fees += fee
                        position = Position(
                            codes=codes,
                            strikes=strikes,
                            ticks=ticks,
                            expiry=pd.Timestamp(candidate["expiry"]),
                            quantity=quantity,
                            entry_date=date,
                            entry_cashflow_per_combo=credit,
                            max_loss_per_combo=max_loss,
                            entry_fees=fee,
                            accumulated_fees=fee,
                            entry_fee_per_combo=fee / quantity,
                            risk_unit=target_unit,
                        )
                        action = "OPEN"

        mark_value = 0.0
        mark_source = "CASH"
        if position is not None:
            spot = float(calendar_row.etf_mark)
            mark_value, mark_source = _position_mark(position, date, marks, spot)
        nav = cash + mark_value
        daily_return = nav / previous_nav - 1.0 if previous_nav > 0 else math.nan
        if position is not None:
            open_pnl = (
                position.entry_cashflow_per_combo * position.quantity
                + mark_value
                - position.accumulated_fees
            )
            position.stop_pending = (
                open_pnl <= -0.5 * position.max_loss_per_combo * position.quantity
            )
        else:
            open_pnl = 0.0
        daily.append(
            {
                "session_date": date,
                "strategy": strategy,
                "fill_scenario": fill_scenario,
                "broker_fee_per_contract": broker_fee,
                "risk_budget": risk_budget,
                "nav": nav,
                "daily_return": daily_return,
                "cash": cash,
                "position_mark": mark_value,
                "position_quantity": position.quantity if position else 0,
                "risk_unit": target_unit,
                "phase": str(calendar_row.phase),
                "action": action,
                "mark_source": mark_source,
                "open_pnl": open_pnl,
                "fees_cumulative": total_fees,
            }
        )
        previous_nav = nav
    return pd.DataFrame(daily), pd.DataFrame(trades), pd.DataFrame(rejects)


def build_etf_benchmark(
    calendar: pd.DataFrame,
    *,
    initial_capital: float = INITIAL_CAPITAL,
) -> pd.DataFrame:
    valid = calendar.loc[calendar["tr_mark"].gt(0)].copy()
    if valid.empty:
        raise ValueError("No valid 510300 total-return marks")
    first = valid.iloc[0]
    entry_price = float(first["entry_vwap"]) + 0.002
    if not np.isfinite(entry_price) or entry_price <= 0:
        raise ValueError("No valid 510300 opening execution price")
    shares = math.floor(initial_capital / entry_price / 100.0) * 100
    purchase_value = shares * entry_price
    commission = max(5.0, purchase_value * 0.0003)
    while purchase_value + commission > initial_capital and shares >= 100:
        shares -= 100
        purchase_value = shares * entry_price
        commission = max(5.0, purchase_value * 0.0003)
    cash = initial_capital - purchase_value - commission
    adjusted_factor = float(first["tr_mark"]) / float(first["etf_mark"])
    adjusted_entry = entry_price * adjusted_factor
    valid["nav"] = cash + purchase_value * valid["tr_mark"] / adjusted_entry
    valid["daily_return"] = valid["nav"].pct_change().fillna(0.0)
    valid.loc[valid.index[0], "daily_return"] = valid.iloc[0]["nav"] / initial_capital - 1.0
    valid["strategy"] = "ETF_BH"
    valid["fill_scenario"] = "VWAP_2TICK"
    valid["broker_fee_per_contract"] = 2.0
    valid["risk_budget"] = RISK_BUDGET
    valid["position_quantity"] = float(shares)
    valid["risk_unit"] = 1.0
    valid["action"] = "BUY_AND_HOLD"
    valid["fees_cumulative"] = commission
    return valid[
        [
            "session_date",
            "strategy",
            "fill_scenario",
            "broker_fee_per_contract",
            "risk_budget",
            "nav",
            "daily_return",
            "position_quantity",
            "risk_unit",
            "phase",
            "action",
            "fees_cumulative",
        ]
    ]


def path_metrics(frame: pd.DataFrame, initial_capital: float = INITIAL_CAPITAL) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Cannot measure an empty path")
    ordered = frame.sort_values("session_date").reset_index(drop=True)
    returns = ordered["daily_return"].fillna(0.0).astype(float)
    nav = ordered["nav"].astype(float)
    years = max(
        (ordered["session_date"].iloc[-1] - ordered["session_date"].iloc[0]).days / 365.2425,
        1 / 365.2425,
    )
    running_peak = nav.cummax()
    drawdown = nav / running_peak - 1.0
    daily_std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    rolling_20 = (1.0 + returns).rolling(20).apply(np.prod, raw=True) - 1.0
    losses = returns.loc[returns <= returns.quantile(0.05)]
    ending = float(nav.iloc[-1])
    return {
        "start": pd.Timestamp(ordered["session_date"].iloc[0]).date().isoformat(),
        "end": pd.Timestamp(ordered["session_date"].iloc[-1]).date().isoformat(),
        "sessions": len(ordered),
        "ending_value": ending,
        "total_return": ending / initial_capital - 1.0,
        "cagr": (ending / initial_capital) ** (1.0 / years) - 1.0,
        "annualized_volatility": daily_std * math.sqrt(252),
        "sharpe_zero_cash_rate": float(returns.mean() / daily_std * math.sqrt(252))
        if daily_std
        else None,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_date": pd.Timestamp(ordered.loc[drawdown.idxmin(), "session_date"])
        .date()
        .isoformat(),
        "worst_session_return": float(returns.min()),
        "worst_20_session_return": float(rolling_20.min()) if rolling_20.notna().any() else None,
        "expected_shortfall_95": float(losses.mean()) if not losses.empty else None,
        "positive_session_rate": float(returns.gt(0).mean()),
        "average_risk_unit": float(ordered["risk_unit"].mean()),
        "invested_session_rate": float(ordered["position_quantity"].gt(0).mean()),
        "fees": float(ordered["fees_cumulative"].iloc[-1]),
    }


def _period_metrics(frame: pd.DataFrame, start: pd.Timestamp | None = None) -> dict[str, Any]:
    selected = (
        frame.loc[frame["session_date"].ge(start)].copy() if start is not None else frame.copy()
    )
    if selected.empty:
        return {}
    if start is not None:
        base = float(selected.iloc[0]["nav"])
        fee_base = float(selected.iloc[0]["fees_cumulative"])
        selected["nav"] = INITIAL_CAPITAL * selected["nav"] / base
        selected["daily_return"] = selected["nav"].pct_change().fillna(0.0)
        selected["fees_cumulative"] = selected["fees_cumulative"] - fee_base
    return path_metrics(selected)


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


def _money(value: Any) -> str:
    return "—" if value is None else f"¥{float(value):,.0f}"


def _metric_rows(metrics: dict[str, dict[str, Any]]) -> str:
    rows = []
    for strategy in STRATEGIES:
        item = metrics[strategy]
        sharpe = item["sharpe_zero_cash_rate"]
        sharpe_text = "—" if sharpe is None else f"{float(sharpe):.2f}"
        rows.append(
            "<tr>"
            f"<th>{html.escape(STRATEGY_LABELS[strategy])}</th>"
            f"<td>{_money(item['ending_value'])}</td><td>{_percent(item['total_return'])}</td>"
            f"<td>{_percent(item['cagr'])}</td><td>{_percent(item['annualized_volatility'])}</td>"
            f"<td>{sharpe_text}</td>"
            f"<td>{_percent(item['max_drawdown'])}</td><td>{_percent(item['worst_session_return'])}</td>"
            f"<td>{_percent(item['invested_session_rate'])}</td><td>{_money(item['fees'])}</td></tr>"
        )
    return "".join(rows)


def render_report_html(report: dict[str, Any], ledger: pd.DataFrame) -> str:
    primary = ledger.loc[
        ledger["fill_scenario"].eq("VWAP_2TICK")
        & ledger["broker_fee_per_contract"].eq(2.0)
        & ledger["risk_budget"].eq(RISK_BUDGET)
    ].copy()
    colors = {"ETF_BH": "#66a3ff", "SV_STATIC": "#f5a742", "SV_MATSHIX": "#45d39a"}
    equity = go.Figure()
    drawdown = go.Figure()
    for strategy in STRATEGIES:
        path = primary.loc[primary["strategy"].eq(strategy)].sort_values("session_date")
        equity.add_trace(
            go.Scatter(
                x=path["session_date"],
                y=path["nav"],
                name=STRATEGY_LABELS[strategy],
                line={"color": colors[strategy], "width": 2.3},
                hovertemplate="%{x|%Y-%m-%d}<br>¥%{y:,.0f}<extra>%{fullData.name}</extra>",
            )
        )
        dd = path["nav"] / path["nav"].cummax() - 1.0
        drawdown.add_trace(
            go.Scatter(
                x=path["session_date"],
                y=dd * 100,
                name=STRATEGY_LABELS[strategy],
                line={"color": colors[strategy], "width": 2.0},
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}%<extra>%{fullData.name}</extra>",
            )
        )
    for figure, ytitle, height in (
        (equity, "组合净值（元）", 500),
        (drawdown, "距历史高点（%）", 400),
    ):
        figure.update_layout(
            template="plotly_dark",
            height=height,
            margin={"l": 58, "r": 25, "t": 25, "b": 45},
            paper_bgcolor="#10151e",
            plot_bgcolor="#10151e",
            hovermode="x unified",
            legend={"orientation": "h", "y": 1.10},
            yaxis_title=ytitle,
        )
    equity_html = pio.to_html(equity, include_plotlyjs=True, full_html=False)
    drawdown_html = pio.to_html(drawdown, include_plotlyjs=False, full_html=False)

    common = cast(dict[str, dict[str, Any]], report["periods"]["common_period"])
    full = cast(dict[str, dict[str, Any]], report["periods"]["full_period"])
    sensitivity_rows = []
    for row in cast(list[dict[str, Any]], report["sensitivity"]):
        sensitivity_rows.append(
            f"<tr><th>{html.escape(str(row['fill_scenario']))}</th><td>{html.escape(str(row['fee_scenario']))}</td>"
            f"<td>{_money(row['static_ending_value'])}</td><td>{_money(row['dynamic_ending_value'])}</td>"
            f"<td>{_percent(row['dynamic_max_drawdown'])}</td></tr>"
        )
    risk_rows = []
    for row in cast(list[dict[str, Any]], report["risk_budget_sensitivity"]):
        risk_rows.append(
            f"<tr><th>{float(row['risk_budget']) * 100:.0f}%</th>"
            f"<td>{_money(row['static_ending_value'])}</td><td>{_percent(row['static_max_drawdown'])}</td>"
            f"<td>{_money(row['dynamic_ending_value'])}</td><td>{_percent(row['dynamic_max_drawdown'])}</td></tr>"
        )
    annual_rows = []
    for row in cast(list[dict[str, Any]], report["annual_returns"]):
        annual_rows.append(
            f"<tr><th>{int(row['year'])}</th><td>{_percent(row['ETF_BH'])}</td>"
            f"<td>{_percent(row['SV_STATIC'])}</td><td>{_percent(row['SV_MATSHIX'])}</td></tr>"
        )
    execution_rows = []
    for strategy in ("SV_STATIC", "SV_MATSHIX"):
        item = cast(dict[str, Any], report["execution_diagnostics"][strategy])
        execution_rows.append(
            f"<tr><th>{html.escape(STRATEGY_LABELS[strategy])}</th>"
            f"<td>{int(item['exit_fill_rows'])}</td><td>{int(item['contracts_closed'])}</td>"
            f"<td>{int(item['expiry_settlement_rows'])}</td><td>{int(item['expiry_settlement_contracts'])}</td>"
            f"<td>{_money(item['realized_pnl'])}</td></tr>"
        )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatSHIX 510300 ShortVol 分钟代理回测</title><style>
:root{{--bg:#0a0e14;--panel:#101722;--line:#253247;--text:#eef4fb;--muted:#94a5ba;--green:#45d39a;--amber:#f5a742}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1240px;margin:auto;padding:34px 24px 70px}}h1{{font-size:32px;margin:0 0 8px}}h2{{margin:34px 0 14px;font-size:21px}}.sub,.note{{color:var(--muted)}}
.badge{{display:inline-block;margin:16px 0;padding:7px 11px;border:1px solid #7a5d1b;border-radius:999px;background:#261d0c;color:#ffd991;font-weight:700}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:780px}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}code{{color:#b8d6ff}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>MatSHIX × 510300 期权动态 ShortVol</h1>
<div class="sub">2023-01-03 至 2026-06-05 · 初始本金 ¥1,000,000 · 主情景 VWAP±2 tick + 券商每张每腿 ¥2</div>
<div class="badge">MINUTE_EXECUTION_PROXY · 研究代理，不是 bid/ask 成交回放</div>
<h2>完整区间</h2><section class="panel"><table><thead><tr><th>策略</th><th>期末净值</th><th>累计收益</th><th>CAGR</th><th>年化波动</th><th>Sharpe</th><th>最大回撤</th><th>最差单日</th><th>持仓日占比</th><th>费用</th></tr></thead><tbody>{_metric_rows(full)}</tbody></table></section>
<h2>共同可比较区间（2024-06-17 起）</h2><section class="panel"><table><thead><tr><th>策略</th><th>期末净值</th><th>累计收益</th><th>CAGR</th><th>年化波动</th><th>Sharpe</th><th>最大回撤</th><th>最差单日</th><th>持仓日占比</th><th>费用</th></tr></thead><tbody>{_metric_rows(common)}</tbody></table></section>
<h2>主情景成交诊断</h2><div class="sub">退出记录包含部分成交；到期内在价值结算表示 7DTE 后仍无法在参与率约束内完全平仓的剩余合约。</div><section class="panel"><table><thead><tr><th>策略</th><th>退出成交记录</th><th>平仓合约</th><th>到期结算记录</th><th>到期结算合约</th><th>已实现 P&amp;L</th></tr></thead><tbody>{"".join(execution_rows)}</tbody></table></section>
<h2>净值曲线</h2><section class="panel">{equity_html}</section><h2>回撤曲线</h2><section class="panel">{drawdown_html}</section>
<h2>年度收益</h2><section class="panel"><table><thead><tr><th>年份</th><th>510300ETF</th><th>静态 ShortVol</th><th>MatSHIX 动态</th></tr></thead><tbody>{"".join(annual_rows)}</tbody></table></section>
<h2>成交与费用敏感性</h2><section class="panel"><table><thead><tr><th>成交模型</th><th>费用模型</th><th>静态期末净值</th><th>动态期末净值</th><th>动态最大回撤</th></tr></thead><tbody>{"".join(sensitivity_rows)}</tbody></table></section>
<h2>单次定义损失预算敏感性</h2><section class="panel"><table><thead><tr><th>NAV 风险预算</th><th>静态期末净值</th><th>静态最大回撤</th><th>动态期末净值</th><th>动态最大回撤</th></tr></thead><tbody>{"".join(risk_rows)}</tbody></table></section>
<h2>证据边界</h2><div class="grid"><section class="panel"><strong>交易链</strong><p class="note">t 日气象站 → t+1 09:35 标的已知价选腿 → 09:36–09:45 四腿分钟 VWAP 成交代理 → 日结算价盯市 → 费用/P&amp;L/NAV。</p></section>
<section class="panel"><strong>不能证明</strong><p class="note">没有逐笔 bid/ask、订单队列、组合保证金与真实券商回报。本报告只能评价规则在分钟级保守代理下的研究表现。</p></section></div>
</main></body></html>"""


def _assemble_report(
    ledger: pd.DataFrame,
    trades: pd.DataFrame,
    rejects: pd.DataFrame,
    selection_rejects: pd.DataFrame,
    *,
    sources: dict[str, Any],
) -> dict[str, Any]:
    primary = ledger.loc[
        ledger["fill_scenario"].eq("VWAP_2TICK")
        & ledger["broker_fee_per_contract"].eq(2.0)
        & ledger["risk_budget"].eq(RISK_BUDGET)
    ]
    full: dict[str, dict[str, Any]] = {}
    common: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        frame = primary.loc[primary["strategy"].eq(strategy)].sort_values("session_date")
        full[strategy] = _period_metrics(frame)
        common[strategy] = _period_metrics(frame, COMMON_START)

    sensitivity = []
    for fill in FILL_SCENARIOS:
        for fee_name, fee in FEE_SCENARIOS.items():
            item: dict[str, Any] = {"fill_scenario": fill, "fee_scenario": fee_name}
            for strategy, prefix in (("SV_STATIC", "static"), ("SV_MATSHIX", "dynamic")):
                frame = ledger.loc[
                    ledger["strategy"].eq(strategy)
                    & ledger["fill_scenario"].eq(fill)
                    & ledger["broker_fee_per_contract"].eq(fee)
                    & ledger["risk_budget"].eq(RISK_BUDGET)
                ]
                metrics = _period_metrics(frame)
                item[f"{prefix}_ending_value"] = metrics["ending_value"]
                item[f"{prefix}_total_return"] = metrics["total_return"]
                item[f"{prefix}_max_drawdown"] = metrics["max_drawdown"]
            sensitivity.append(item)

    risk_budget_sensitivity = []
    for risk_budget in (0.05, 0.08, 0.12):
        item = {"risk_budget": risk_budget}
        for strategy, prefix in (("SV_STATIC", "static"), ("SV_MATSHIX", "dynamic")):
            frame = ledger.loc[
                ledger["strategy"].eq(strategy)
                & ledger["fill_scenario"].eq("VWAP_2TICK")
                & ledger["broker_fee_per_contract"].eq(2.0)
                & ledger["risk_budget"].eq(risk_budget)
            ]
            metrics = _period_metrics(frame)
            item[f"{prefix}_ending_value"] = metrics["ending_value"]
            item[f"{prefix}_total_return"] = metrics["total_return"]
            item[f"{prefix}_max_drawdown"] = metrics["max_drawdown"]
        risk_budget_sensitivity.append(item)

    annual_rows: list[dict[str, Any]] = []
    primary = primary.copy()
    primary["year"] = primary["session_date"].dt.year
    for year in sorted(primary["year"].unique()):
        row: dict[str, Any] = {"year": int(year)}
        for strategy in STRATEGIES:
            returns = primary.loc[
                primary["strategy"].eq(strategy) & primary["year"].eq(year), "daily_return"
            ]
            row[strategy] = float((1.0 + returns.fillna(0.0)).prod() - 1.0)
        annual_rows.append(row)
    primary_trades = trades.loc[
        trades["fill_scenario"].eq("VWAP_2TICK")
        & trades["fee_scenario"].eq("BROKER_PLUS_2")
        & trades["risk_budget"].eq(RISK_BUDGET)
    ]
    primary_rejects = rejects.loc[
        rejects["fee_scenario"].eq("BROKER_PLUS_2") & rejects["risk_budget"].eq(RISK_BUDGET)
    ]
    execution_diagnostics: dict[str, dict[str, Any]] = {}
    for strategy in ("SV_STATIC", "SV_MATSHIX"):
        frame = primary_trades.loc[primary_trades["strategy"].eq(strategy)]
        expiry = frame.loc[frame["exit_window"].eq("EXPIRY_INTRINSIC_SETTLEMENT")]
        execution_diagnostics[strategy] = {
            "exit_fill_rows": len(frame),
            "contracts_closed": int(frame["quantity"].sum()),
            "expiry_settlement_rows": len(expiry),
            "expiry_settlement_contracts": int(expiry["quantity"].sum()),
            "realized_pnl": float(frame["realized_pnl"].sum()),
            "fees": float(frame["fees"].sum()),
        }
    return {
        "research_status": "MINUTE_EXECUTION_PROXY",
        "initial_capital_cny": INITIAL_CAPITAL,
        "periods": {"full_period": full, "common_period": common},
        "primary_scenario": {"fill": "VWAP_2TICK", "fee": "BROKER_PLUS_2"},
        "annual_returns": annual_rows,
        "sensitivity": sensitivity,
        "risk_budget_sensitivity": risk_budget_sensitivity,
        "activity": {
            "closed_trade_lots_primary": int(len(primary_trades)),
            "execution_rejections_primary": int(len(primary_rejects)),
            "selection_rejections": int(len(selection_rejects)),
        },
        "execution_diagnostics": execution_diagnostics,
        "methodology": {
            "signal_lag": "t state only changes t+1 decisions",
            "selection": "25-45 DTE nearest 35; 15-25 absolute delta nearest 20; two listed-strike wings",
            "entry_window": "09:36-09:45",
            "participation_cap": PARTICIPATION_RATE,
            "defined_loss_budget": RISK_BUDGET,
            "margin_cap": MARGIN_CAP,
            "cash_rate": 0.0,
            "etf_entry": "09:36-09:45 VWAP + 2 ticks; 100-share lots; 3 bp commission with CNY 5 minimum",
        },
        "limitations": [
            "No historical bid/ask or queue position; minute OHLCV/amount creates an execution proxy.",
            "Margin is conservatively proxied by defined maximum loss, not a broker portfolio-margin engine.",
            "ETF benchmark uses the local adjusted total-return mark; options use standard-contract multiplier 10,000.",
            "All unavailable/partial MatSHIX states map dynamic risk to cash; no signal is backfilled.",
            "Exchange/clearing and broker fees are frozen scenario inputs; historical account-specific fee schedules are not reconstructed.",
        ],
        "sources": sources,
    }


def run_shortvol_backtest(
    project_dir: Path,
    aetf_root: Path,
    *,
    output_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> BacktestArtifacts:
    root = project_dir.expanduser().resolve()
    source = aetf_root.expanduser().resolve()
    processed = root / "data/processed/research"
    notify = progress or (lambda _message: None)
    required = [
        processed / "daily_market_state.parquet",
        processed / "economic_index_feature.parquet",
        processed / "economic_index_state.parquet",
        processed / "etf_mark.parquet",
        processed / "carrier_expiry_surface.parquet",
        source / "OPTION/opt_basic.parquet",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Backtest inputs are missing: {missing}")

    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    connection.execute("SET memory_limit = '8GB'")
    notify("提取 510300 ETF 分钟开盘锚点")
    etf_minutes = _extract_etf_minutes(connection, source)
    marks = pd.read_parquet(processed / "etf_mark.parquet")
    marks = marks.loc[
        marks["underlying_symbol"].eq("510300.SH"), ["session_date", "etf_mark", "tr_mark"]
    ]
    marks = _date_column(marks).drop_duplicates("session_date", keep="last")
    calendar = etf_minutes.merge(marks, on="session_date", how="inner").sort_values("session_date")
    calendar = calendar.loc[
        calendar["session_date"].between("2023-01-03", "2026-06-05")
    ].reset_index(drop=True)
    signals = _load_signal_calendar(processed, pd.DatetimeIndex(calendar["session_date"]))
    calendar = calendar.merge(signals, on="session_date", how="left", validate="one_to_one")

    notify("按 t-1 波动率曲面选择 20-delta 铁鹰四腿")
    candidates, selection_rejects = select_condor_candidates(
        calendar, _standard_contracts(source), _surface_map(processed)
    )
    if candidates.empty:
        raise ValueError("No valid iron-condor candidates were selected")
    codes = pd.DataFrame(
        {"code": pd.unique(candidates[[f"{name}_code" for name in LEG_NAMES]].to_numpy().ravel())}
    )
    notify(f"扫描 {len(codes)} 个入选标准合约的分钟成交窗口")
    option_windows = _extract_option_windows(connection, source, codes)
    notify("提取入选合约的日结算价")
    option_marks = _extract_option_marks(connection, source, codes)
    connection.close()

    all_ledgers = [build_etf_benchmark(calendar)]
    all_trades: list[pd.DataFrame] = []
    all_rejects: list[pd.DataFrame] = []
    shortvol_strategies: tuple[
        Literal["SV_STATIC", "SV_MATSHIX"], Literal["SV_STATIC", "SV_MATSHIX"]
    ] = ("SV_STATIC", "SV_MATSHIX")
    for fill in FILL_SCENARIOS:
        for fee_name, broker_fee in FEE_SCENARIOS.items():
            notify(f"运行 {fill} / {fee_name}")
            for strategy in shortvol_strategies:
                daily, trades, rejects = simulate_shortvol(
                    calendar,
                    candidates,
                    option_windows,
                    option_marks,
                    strategy=strategy,
                    fill_scenario=fill,
                    broker_fee=broker_fee,
                    risk_budget=RISK_BUDGET,
                )
                daily["fee_scenario"] = fee_name
                trades["fee_scenario"] = fee_name
                rejects["fee_scenario"] = fee_name
                trades["risk_budget"] = RISK_BUDGET
                rejects["risk_budget"] = RISK_BUDGET
                all_ledgers.append(daily)
                all_trades.append(trades)
                all_rejects.append(rejects)
    for risk_budget in (0.05, 0.12):
        notify(f"运行定义损失预算 {risk_budget:.0%} 敏感性")
        for strategy in shortvol_strategies:
            daily, trades, rejects = simulate_shortvol(
                calendar,
                candidates,
                option_windows,
                option_marks,
                strategy=strategy,
                fill_scenario="VWAP_2TICK",
                broker_fee=2.0,
                risk_budget=risk_budget,
            )
            daily["fee_scenario"] = "BROKER_PLUS_2"
            trades["fee_scenario"] = "BROKER_PLUS_2"
            rejects["fee_scenario"] = "BROKER_PLUS_2"
            trades["risk_budget"] = risk_budget
            rejects["risk_budget"] = risk_budget
            all_ledgers.append(daily)
            all_trades.append(trades)
            all_rejects.append(rejects)
    ledger = pd.concat(all_ledgers, ignore_index=True, sort=False)
    trades = pd.concat(all_trades, ignore_index=True, sort=False)
    rejections = pd.concat(all_rejects, ignore_index=True, sort=False)
    sources = {
        "aetf_root": str(source),
        "opt_basic_sha256": file_hash(source / "OPTION/opt_basic.parquet"),
        "state_sha256": file_hash(processed / "daily_market_state.parquet"),
        "candidate_sessions": len(candidates),
        "option_codes_scanned": len(codes),
        "option_window_rows": len(option_windows),
        "first_session": pd.Timestamp(calendar["session_date"].min()).date().isoformat(),
        "last_session": pd.Timestamp(calendar["session_date"].max()).date().isoformat(),
    }
    report = _assemble_report(ledger, trades, rejections, selection_rejects, sources=sources)

    target = (output_dir or root / "outputs/backtest/510300_shortvol").resolve()
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "report.json"
    write_json(report_path, report)
    daily_path = target / "daily_ledger.parquet"
    ledger.to_parquet(daily_path, index=False, compression="zstd")
    trade_path = _atomic_text(
        target / "trade_ledger.csv",
        trades.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n"),
    )
    rejection_path = _atomic_text(
        target / "rejection_ledger.csv",
        pd.concat(
            [selection_rejects.assign(strategy="ALL", fee_scenario="ALL"), rejections],
            ignore_index=True,
            sort=False,
        ).to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n"),
    )
    html_path = _atomic_text(target / "report.html", render_report_html(report, ledger))
    return BacktestArtifacts(report_path, daily_path, trade_path, rejection_path, html_path, report)
