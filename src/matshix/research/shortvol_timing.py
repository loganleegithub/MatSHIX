from __future__ import annotations

import html
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from scipy.stats import spearmanr

from matshix.research.shortvol import (
    COMMON_START,
    LEG_NAMES,
    MULTIPLIER,
    _atomic_text,
    _date_column,
    _extract_etf_minutes,
    _extract_option_marks,
    _load_signal_calendar,
    _max_loss_per_combo,
    _standard_contracts,
    _surface_map,
    select_condor_candidates,
)
from matshix.serialization import file_hash, write_json

PRIMARY_HORIZON = "TO_7DTE"
HORIZON_LABELS = {
    "H5": "持有 5 个交易日",
    "H10": "持有 10 个交易日",
    PRIMARY_HORIZON: "持有至 7DTE",
}
STATE_CATEGORIES = ("ALLOW", "KNOWN_BLOCK", "ABSTAIN_DATA")
STATE_LABELS = {
    "ALLOW": "允许卖波动率",
    "KNOWN_BLOCK": "已知状态明确禁做",
    "ABSTAIN_DATA": "数据不完整而弃权",
}
STATE_PATH_MODES = ("STATIC_KNOWN_UNIVERSE", "KNOWN_BLOCK_EXIT", "ALL_ZERO_EXIT")
STATE_PATH_LABELS = {
    "STATIC_KNOWN_UNIVERSE": "静态持有（仅完整状态机会）",
    "KNOWN_BLOCK_EXIT": "只在完整状态明确禁做时退出",
    "ALL_ZERO_EXIT": "禁做或数据弃权均退出",
}


@dataclass(frozen=True)
class TimingArtifacts:
    report_path: Path
    panel_path: Path
    market_stress_panel_path: Path
    state_path_ledger_path: Path
    worst_scenarios_path: Path
    html_path: Path
    report: dict[str, Any]


def classify_timing_state(row: pd.Series) -> str:
    """Separate a policy block from an abstention caused by incomplete state data."""
    compensation = str(row.get("insurance_compensation", "UNKNOWN"))
    complete = (
        str(row.get("global_status", "UNKNOWN")) == "OK"
        and str(row.get("local_status", "UNKNOWN")) == "OK"
        and str(row.get("phase", "UNKNOWN")) != "UNKNOWN"
        and compensation not in {"", "UNKNOWN", "nan", "None"}
        and pd.notna(row.get("vrp_ewma94"))
    )
    if not complete:
        return "ABSTAIN_DATA"
    return "ALLOW" if float(row.get("dynamic_unit", 0.0) or 0.0) > 0 else "KNOWN_BLOCK"


def _mark_lookup(frame: pd.DataFrame) -> dict[tuple[pd.Timestamp, str], float]:
    result: dict[tuple[pd.Timestamp, str], float] = {}
    for row in frame.itertuples(index=False):
        settle = pd.to_numeric(pd.Series([getattr(row, "settle", np.nan)]), errors="coerce").iloc[0]
        close = pd.to_numeric(pd.Series([getattr(row, "close", np.nan)]), errors="coerce").iloc[0]
        value = settle if pd.notna(settle) else close
        if pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
            result[(pd.Timestamp(row.session_date), str(row.code))] = float(value)
    return result


def _combo_mark(values: dict[str, float]) -> float:
    return MULTIPLIER * (
        values["short_put"] + values["short_call"] - values["long_put"] - values["long_call"]
    )


def _leg_values(
    date: pd.Timestamp,
    codes: dict[str, str],
    marks: dict[tuple[pd.Timestamp, str], float],
) -> dict[str, float] | None:
    values = {name: marks.get((date, codes[name]), math.nan) for name in LEG_NAMES}
    if not all(np.isfinite(value) and value >= 0 for value in values.values()):
        return None
    return values


def _exit_dates(
    date: pd.Timestamp,
    expiry: pd.Timestamp,
    sessions: pd.DatetimeIndex,
    session_index: dict[pd.Timestamp, int],
) -> dict[str, pd.Timestamp]:
    exits: dict[str, pd.Timestamp] = {}
    index = session_index[date]
    for label, distance in (("H5", 5), ("H10", 10)):
        if index + distance < len(sessions):
            exits[label] = pd.Timestamp(sessions[index + distance])
    target = expiry - pd.Timedelta(days=7)
    target_index = int(sessions.searchsorted(target))
    if target_index < len(sessions) and sessions[target_index] <= expiry:
        exits[PRIMARY_HORIZON] = pd.Timestamp(sessions[target_index])
    return exits


def build_timing_opportunity_panel(
    calendar: pd.DataFrame,
    candidates: pd.DataFrame,
    option_marks: pd.DataFrame,
) -> pd.DataFrame:
    """Mark every selectable iron-condor opportunity without execution or cost assumptions."""
    marks = _mark_lookup(option_marks)
    ordered_calendar = calendar.sort_values("session_date").reset_index(drop=True)
    sessions = pd.DatetimeIndex(ordered_calendar["session_date"])
    session_index = {pd.Timestamp(date): index for index, date in enumerate(sessions)}
    calendar_lookup = ordered_calendar.set_index("session_date")
    spot_lookup = {
        pd.Timestamp(row.session_date): float(row.etf_mark)
        for row in ordered_calendar.itertuples(index=False)
        if pd.notna(row.etf_mark)
    }
    rows: list[dict[str, Any]] = []

    for candidate in candidates.itertuples(index=False):
        date = pd.Timestamp(candidate.session_date)
        expiry = pd.Timestamp(candidate.expiry)
        if date not in calendar_lookup.index or date not in session_index:
            continue
        codes = {name: str(getattr(candidate, f"{name}_code")) for name in LEG_NAMES}
        strikes = {name: float(getattr(candidate, f"{name}_strike")) for name in LEG_NAMES}
        entry_values = _leg_values(date, codes, marks)
        if entry_values is None:
            continue
        entry_credit = _combo_mark(entry_values)
        width = (
            max(
                strikes["short_put"] - strikes["long_put"],
                strikes["long_call"] - strikes["short_call"],
            )
            * MULTIPLIER
        )
        if not (0 < entry_credit < width):
            continue
        maximum_loss = _max_loss_per_combo(strikes, entry_credit)
        state = cast(pd.Series, calendar_lookup.loc[date])
        category = classify_timing_state(state)
        base = {
            "session_date": date,
            "weather_signal_session_date": pd.Timestamp(state["signal_session_date"])
            if pd.notna(state.get("signal_session_date"))
            else pd.NaT,
            "expiry": expiry,
            "dte": int((expiry - date).days),
            "state_category": category,
            "phase": str(state.get("phase", "UNKNOWN")),
            "risk_unit": float(state.get("dynamic_unit", 0.0) or 0.0),
            "raw_risk_unit": float(state.get("raw_dynamic_unit", 0.0) or 0.0),
            "risk_reason": str(state.get("risk_reason", "UNKNOWN")),
            "global_status": str(state.get("global_status", "UNKNOWN")),
            "local_status": str(state.get("local_status", "UNKNOWN")),
            "insurance_compensation": str(state.get("insurance_compensation", "UNKNOWN")),
            "entry_credit": entry_credit,
            "defined_max_loss": maximum_loss,
            "credit_to_max_loss": entry_credit / maximum_loss,
            "spot_entry": float(state.get("etf_mark", math.nan)),
            **{f"{name}_code": code for name, code in codes.items()},
            **{f"{name}_strike": strike for name, strike in strikes.items()},
        }

        for horizon, exit_date in _exit_dates(date, expiry, sessions, session_index).items():
            exit_values = _leg_values(exit_date, codes, marks)
            if exit_values is None:
                continue
            exit_debit = _combo_mark(exit_values)
            pnl = entry_credit - exit_debit
            put_pnl = MULTIPLIER * (
                entry_values["short_put"]
                - exit_values["short_put"]
                + exit_values["long_put"]
                - entry_values["long_put"]
            )
            call_pnl = MULTIPLIER * (
                entry_values["short_call"]
                - exit_values["short_call"]
                + exit_values["long_call"]
                - entry_values["long_call"]
            )
            path_dates = sessions[(sessions >= date) & (sessions <= exit_date)]
            path_returns: list[tuple[pd.Timestamp, float]] = []
            path_spots: list[float] = []
            for path_date in path_dates:
                timestamp = pd.Timestamp(path_date)
                path_values = _leg_values(timestamp, codes, marks)
                if path_values is not None:
                    path_returns.append(
                        (timestamp, (entry_credit - _combo_mark(path_values)) / maximum_loss)
                    )
                spot = spot_lookup.get(timestamp)
                if spot is not None and np.isfinite(spot):
                    path_spots.append(spot)
            worst_date, adverse_excursion = (
                min(path_returns, key=lambda item: item[1]) if path_returns else (pd.NaT, math.nan)
            )
            rows.append(
                {
                    **base,
                    "horizon": horizon,
                    "exit_date": exit_date,
                    "holding_sessions": session_index[exit_date] - session_index[date],
                    "exit_debit": exit_debit,
                    "pnl_per_combo": pnl,
                    "return_on_max_loss": pnl / maximum_loss,
                    "put_side_pnl": put_pnl,
                    "call_side_pnl": call_pnl,
                    "loss_side": "CALL" if call_pnl < put_pnl else "PUT",
                    "max_adverse_excursion": adverse_excursion,
                    "mae_date": worst_date,
                    "path_mark_coverage": len(path_returns) / max(len(path_dates), 1),
                    "path_spot_min": min(path_spots) if path_spots else math.nan,
                    "path_spot_max": max(path_spots) if path_spots else math.nan,
                    "put_short_breached": bool(
                        path_spots and min(path_spots) < strikes["short_put"]
                    ),
                    "call_short_breached": bool(
                        path_spots and max(path_spots) > strikes["short_call"]
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(["horizon", "session_date"]).reset_index(drop=True)


def build_market_stress_panel(
    calendar: pd.DataFrame,
    contracts: pd.DataFrame,
    surface: dict[tuple[pd.Timestamp, pd.Timestamp], float],
) -> pd.DataFrame:
    """Create an option-execution-free check of future realized stress versus lagged IV."""
    ordered = calendar.sort_values("session_date").reset_index(drop=True)
    sessions = pd.DatetimeIndex(ordered["session_date"])
    rows: list[dict[str, Any]] = []
    for index, state in ordered.iterrows():
        if index == 0:
            continue
        date = pd.Timestamp(state["session_date"])
        previous = pd.Timestamp(sessions[index - 1])
        active = contracts.loc[
            contracts["list_date"].le(date)
            & contracts["maturity_date"].ge(date)
            & contracts["call_put"].isin(["C", "P"])
        ].copy()
        if active.empty:
            continue
        active["dte"] = (active["maturity_date"] - date).dt.days
        expiries = active.loc[
            active["dte"].between(25, 45), ["maturity_date", "dte"]
        ].drop_duplicates("maturity_date")
        if expiries.empty:
            continue
        expiries["distance"] = (expiries["dte"] - 35).abs()
        expiry = pd.Timestamp(expiries.sort_values(["distance", "dte"]).iloc[0]["maturity_date"])
        implied_vol = surface.get((previous, expiry))
        if implied_vol is None or not np.isfinite(implied_vol) or implied_vol <= 0:
            continue
        category = classify_timing_state(state)
        for horizon in (5, 10, 20):
            if index + horizon >= len(ordered):
                continue
            path = pd.to_numeric(
                ordered.loc[index : index + horizon, "etf_mark"], errors="coerce"
            ).to_numpy(dtype=float)
            if len(path) != horizon + 1 or not np.all(np.isfinite(path)) or np.any(path <= 0):
                continue
            daily_log_returns = np.diff(np.log(path))
            realized_vol = float(np.std(daily_log_returns, ddof=1) * np.sqrt(252.0))
            cumulative = np.log(path / path[0])
            expected_move = float(implied_vol * np.sqrt(horizon / 252.0))
            rows.append(
                {
                    "session_date": date,
                    "future_end_date": pd.Timestamp(sessions[index + horizon]),
                    "expiry": expiry,
                    "horizon": f"H{horizon}",
                    "state_category": category,
                    "phase": str(state.get("phase", "UNKNOWN")),
                    "risk_unit": float(state.get("dynamic_unit", 0.0) or 0.0),
                    "lagged_atm_iv": float(implied_vol),
                    "future_realized_vol": realized_vol,
                    "realized_to_implied": realized_vol / implied_vol,
                    "expected_move": expected_move,
                    "normalized_max_move": float(np.max(np.abs(cumulative))) / expected_move,
                    "maximum_up_move": float(np.max(cumulative)),
                    "maximum_down_move": float(np.min(cumulative)),
                }
            )
    return pd.DataFrame(rows).sort_values(["horizon", "session_date"]).reset_index(drop=True)


def simulate_settlement_state_paths(
    calendar: pd.DataFrame,
    candidates: pd.DataFrame,
    option_marks: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Run one-combo state paths using settlements so signal exits are not blocked by liquidity."""
    marks = _mark_lookup(option_marks)
    ordered = calendar.sort_values("session_date").reset_index(drop=True)
    candidate_lookup = {
        pd.Timestamp(row.session_date): row for row in candidates.itertuples(index=False)
    }
    rows: list[dict[str, Any]] = []
    runtime: dict[str, dict[str, Any]] = {}
    for mode in STATE_PATH_MODES:
        position: dict[str, Any] | None = None
        exposure_days = 0
        unfilled_state_exits = 0
        for state_row in ordered.itertuples(index=False):
            date = pd.Timestamp(state_row.session_date)
            state = pd.Series(state_row._asdict())
            category = classify_timing_state(state)
            exited = False
            if position is not None:
                exposure_days += 1
                dte = int((cast(pd.Timestamp, position["expiry"]) - date).days)
                exit_reason: str | None = None
                if mode == "KNOWN_BLOCK_EXIT" and category == "KNOWN_BLOCK":
                    exit_reason = "STATE_KNOWN_BLOCK"
                elif mode == "ALL_ZERO_EXIT" and category != "ALLOW":
                    exit_reason = f"STATE_{category}"
                elif dte <= 7:
                    exit_reason = "DTE_7"
                if exit_reason is not None:
                    exit_values = _leg_values(date, cast(dict[str, str], position["codes"]), marks)
                    if exit_values is None:
                        unfilled_state_exits += 1
                    else:
                        exit_debit = _combo_mark(exit_values)
                        pnl = float(position["entry_credit"]) - exit_debit
                        rows.append(
                            {
                                "mode": mode,
                                "entry_date": position["entry_date"],
                                "exit_date": date,
                                "expiry": position["expiry"],
                                "entry_state_category": position["entry_state_category"],
                                "entry_phase": position["entry_phase"],
                                "entry_risk_unit": position["entry_risk_unit"],
                                "exit_state_category": category,
                                "exit_reason": exit_reason,
                                "holding_calendar_days": int(
                                    (date - cast(pd.Timestamp, position["entry_date"])).days
                                ),
                                "entry_credit": position["entry_credit"],
                                "exit_debit": exit_debit,
                                "defined_max_loss": position["defined_max_loss"],
                                "pnl_per_combo": pnl,
                                "return_on_max_loss": pnl / float(position["defined_max_loss"]),
                                **cast(dict[str, str], position["codes"]),
                            }
                        )
                        position = None
                        exited = True

            static_entry = mode == "STATIC_KNOWN_UNIVERSE" and category != "ABSTAIN_DATA"
            dynamic_entry = mode != "STATIC_KNOWN_UNIVERSE" and category == "ALLOW"
            if position is not None or exited or not (static_entry or dynamic_entry):
                continue
            candidate = candidate_lookup.get(date)
            if candidate is None:
                continue
            codes = {name: str(getattr(candidate, f"{name}_code")) for name in LEG_NAMES}
            entry_values = _leg_values(date, codes, marks)
            if entry_values is None:
                continue
            entry_credit = _combo_mark(entry_values)
            strikes = {name: float(getattr(candidate, f"{name}_strike")) for name in LEG_NAMES}
            width = (
                max(
                    strikes["short_put"] - strikes["long_put"],
                    strikes["long_call"] - strikes["short_call"],
                )
                * MULTIPLIER
            )
            if not (0 < entry_credit < width):
                continue
            position = {
                "entry_date": date,
                "expiry": pd.Timestamp(candidate.expiry),
                "codes": codes,
                "entry_credit": entry_credit,
                "defined_max_loss": _max_loss_per_combo(strikes, entry_credit),
                "entry_state_category": category,
                "entry_phase": str(state.get("phase", "UNKNOWN")),
                "entry_risk_unit": float(state.get("dynamic_unit", 0.0) or 0.0),
            }
        runtime[mode] = {
            "exposure_days": exposure_days,
            "unfilled_state_exit_days": unfilled_state_exits,
            "open_position_at_end": position is not None,
        }
    return pd.DataFrame(rows), runtime


def _group_statistics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "n": 0,
            "mean_return_on_max_loss": None,
            "median_return_on_max_loss": None,
            "win_rate": None,
            "mean_max_adverse_excursion": None,
            "worst_return_on_max_loss": None,
        }
    returns = frame["return_on_max_loss"].astype(float)
    return {
        "n": len(frame),
        "mean_return_on_max_loss": float(returns.mean()),
        "median_return_on_max_loss": float(returns.median()),
        "win_rate": float(returns.gt(0).mean()),
        "mean_max_adverse_excursion": float(frame["max_adverse_excursion"].mean()),
        "worst_return_on_max_loss": float(returns.min()),
    }


def _mean_delta(frame: pd.DataFrame) -> float | None:
    allowed = frame.loc[frame["state_category"].eq("ALLOW"), "return_on_max_loss"]
    blocked = frame.loc[frame["state_category"].eq("KNOWN_BLOCK"), "return_on_max_loss"]
    if allowed.empty or blocked.empty:
        return None
    return float(allowed.mean() - blocked.mean())


def _expiry_cluster_bootstrap(
    frame: pd.DataFrame, *, draws: int = 2_000, seed: int = 20260821
) -> dict[str, Any]:
    expiry_groups = [group for _, group in frame.groupby("expiry", sort=True)]
    if len(expiry_groups) < 2 or _mean_delta(frame) is None:
        return {"clusters": len(expiry_groups), "draws": 0, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    for _ in range(draws):
        selections = rng.integers(0, len(expiry_groups), size=len(expiry_groups))
        sample = pd.concat([expiry_groups[int(index)] for index in selections], ignore_index=True)
        delta = _mean_delta(sample)
        if delta is not None:
            deltas.append(delta)
    if not deltas:
        return {"clusters": len(expiry_groups), "draws": 0, "ci95": [None, None]}
    return {
        "clusters": len(expiry_groups),
        "draws": len(deltas),
        "ci95": [float(np.quantile(deltas, 0.025)), float(np.quantile(deltas, 0.975))],
        "probability_allow_better": float(np.mean(np.asarray(deltas) > 0)),
    }


def _spearman(x: pd.Series, y: pd.Series) -> dict[str, float | None]:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 3 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return {"rho": None, "pvalue_naive": None}
    result = spearmanr(valid["x"], valid["y"])
    return {"rho": float(result.statistic), "pvalue_naive": float(result.pvalue)}


def _summarize_horizon(frame: pd.DataFrame) -> dict[str, Any]:
    known = frame.loc[frame["state_category"].ne("ABSTAIN_DATA")].copy()
    by_category = {
        category: _group_statistics(frame.loc[frame["state_category"].eq(category)])
        for category in STATE_CATEGORIES
    }
    by_risk_unit = [
        {"risk_unit": float(unit), **_group_statistics(group)}
        for unit, group in known.groupby("risk_unit", sort=True)
    ]
    by_phase = [
        {"phase": str(phase), **_group_statistics(group)}
        for phase, group in known.groupby("phase", sort=True)
    ]
    by_phase.sort(
        key=lambda item: (
            math.inf
            if item["mean_return_on_max_loss"] is None
            else float(cast(float, item["mean_return_on_max_loss"]))
        )
    )
    if known.empty:
        tail: dict[str, Any] = {
            "threshold": None,
            "bad_opportunity_days": 0,
            "blocked_bad_opportunity_days": 0,
            "block_capture_rate": None,
            "baseline_block_rate": None,
            "capture_lift": None,
            "bad_expiry_clusters": 0,
            "loss_side_counts": {},
            "phase_counts": {},
            "expiry_counts": {},
        }
    else:
        threshold = float(known["return_on_max_loss"].quantile(0.10))
        bad = known.loc[known["return_on_max_loss"].le(threshold)].copy()
        capture = float(bad["state_category"].eq("KNOWN_BLOCK").mean()) if len(bad) else math.nan
        baseline = float(known["state_category"].eq("KNOWN_BLOCK").mean())
        tail = {
            "threshold": threshold,
            "bad_opportunity_days": len(bad),
            "blocked_bad_opportunity_days": int(bad["state_category"].eq("KNOWN_BLOCK").sum()),
            "allowed_bad_opportunity_days": int(bad["state_category"].eq("ALLOW").sum()),
            "block_capture_rate": capture,
            "baseline_block_rate": baseline,
            "capture_lift": capture / baseline if baseline > 0 else None,
            "bad_expiry_clusters": int(bad["expiry"].nunique()),
            "allowed_bad_rate": float(
                bad["state_category"].eq("ALLOW").sum()
                / max(known["state_category"].eq("ALLOW").sum(), 1)
            ),
            "blocked_bad_rate": float(
                bad["state_category"].eq("KNOWN_BLOCK").sum()
                / max(known["state_category"].eq("KNOWN_BLOCK").sum(), 1)
            ),
            "loss_side_counts": {
                str(side): int(count) for side, count in bad["loss_side"].value_counts().items()
            },
            "phase_counts": {
                str(phase): int(count) for phase, count in bad["phase"].value_counts().items()
            },
            "expiry_counts": {
                pd.Timestamp(expiry).date().isoformat(): int(count)
                for expiry, count in bad["expiry"].value_counts().sort_index().items()
            },
        }

    delta = _mean_delta(known)
    category_expiry = (
        known.groupby(["expiry", "state_category"], as_index=False)["return_on_max_loss"]
        .mean()
        .rename(columns={"return_on_max_loss": "expiry_mean_return"})
    )
    allowed_expiry = category_expiry.loc[
        category_expiry["state_category"].eq("ALLOW"), "expiry_mean_return"
    ]
    blocked_expiry = category_expiry.loc[
        category_expiry["state_category"].eq("KNOWN_BLOCK"), "expiry_mean_return"
    ]
    expiry_balanced_delta = (
        float(allowed_expiry.mean() - blocked_expiry.mean())
        if not allowed_expiry.empty and not blocked_expiry.empty
        else None
    )
    worst_allowed_expiry: pd.Timestamp | None = None
    delta_without_worst: float | None = None
    allowed = known.loc[known["state_category"].eq("ALLOW")]
    if not allowed.empty:
        worst_allowed_expiry = pd.Timestamp(
            allowed.groupby("expiry")["return_on_max_loss"].mean().idxmin()
        )
        delta_without_worst = _mean_delta(known.loc[known["expiry"].ne(worst_allowed_expiry)])

    return {
        "all_opportunities": _group_statistics(frame),
        "known_opportunities": _group_statistics(known),
        "state_counts": {
            category: int(frame["state_category"].eq(category).sum())
            for category in STATE_CATEGORIES
        },
        "by_category": by_category,
        "by_risk_unit": by_risk_unit,
        "by_phase": by_phase,
        "tail": tail,
        "allow_minus_block_mean": delta,
        "expiry_balanced_allow_minus_block_mean": expiry_balanced_delta,
        "expiry_cluster_bootstrap": _expiry_cluster_bootstrap(known),
        "risk_unit_spearman_to_return": _spearman(known["risk_unit"], known["return_on_max_loss"]),
        "risk_unit_spearman_to_mae": _spearman(known["risk_unit"], known["max_adverse_excursion"]),
        "worst_allowed_expiry": worst_allowed_expiry,
        "allow_minus_block_without_worst_expiry": delta_without_worst,
    }


def summarize_timing_panel(panel: pd.DataFrame) -> dict[str, Any]:
    horizons = {
        horizon: _summarize_horizon(panel.loc[panel["horizon"].eq(horizon)].copy())
        for horizon in HORIZON_LABELS
    }
    primary = horizons[PRIMARY_HORIZON]
    delta = primary["allow_minus_block_mean"]
    capture_lift = cast(dict[str, Any], primary["tail"])["capture_lift"]
    if delta is not None and delta < 0 and capture_lift is not None and capture_lift < 1:
        conclusion = "IN_SAMPLE_TIMING_NOT_SUPPORTED"
    elif delta is not None and delta > 0 and capture_lift is not None and capture_lift > 1:
        conclusion = "IN_SAMPLE_TIMING_SUPPORTED"
    else:
        conclusion = "IN_SAMPLE_TIMING_INCONCLUSIVE"
    primary_frame = panel.loc[panel["horizon"].eq(PRIMARY_HORIZON)].copy()
    known_primary = primary_frame.loc[primary_frame["state_category"].ne("ABSTAIN_DATA")].copy()
    worst = known_primary.nsmallest(20, "return_on_max_loss")
    worst_rows = worst[
        [
            "session_date",
            "expiry",
            "exit_date",
            "state_category",
            "risk_unit",
            "phase",
            "risk_reason",
            "return_on_max_loss",
            "max_adverse_excursion",
            "loss_side",
            "put_side_pnl",
            "call_side_pnl",
        ]
    ].to_dict(orient="records")
    return {
        "research_status": "CAUSAL_STATE_HINDSIGHT_OUTCOME_DIAGNOSTIC",
        "conclusion": conclusion,
        "primary_horizon": PRIMARY_HORIZON,
        "horizons": horizons,
        "worst_known_opportunities": worst_rows,
    }


def _stress_group_statistics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "n": 0,
            "mean_realized_to_implied": None,
            "median_realized_to_implied": None,
            "mean_normalized_max_move": None,
            "expected_move_breach_rate": None,
        }
    return {
        "n": len(frame),
        "mean_realized_to_implied": float(frame["realized_to_implied"].mean()),
        "median_realized_to_implied": float(frame["realized_to_implied"].median()),
        "mean_normalized_max_move": float(frame["normalized_max_move"].mean()),
        "expected_move_breach_rate": float(frame["normalized_max_move"].ge(1.0).mean()),
    }


def summarize_market_stress_panel(panel: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for horizon in ("H5", "H10", "H20"):
        frame = panel.loc[panel["horizon"].eq(horizon)].copy()
        known = frame.loc[frame["state_category"].ne("ABSTAIN_DATA")].copy()
        by_category = {
            category: _stress_group_statistics(frame.loc[frame["state_category"].eq(category)])
            for category in STATE_CATEGORIES
        }
        if known.empty:
            tail: dict[str, Any] = {
                "threshold": None,
                "tail_days": 0,
                "blocked_tail_days": 0,
                "block_capture_rate": None,
                "baseline_block_rate": None,
                "capture_lift": None,
            }
        else:
            threshold = float(known["realized_to_implied"].quantile(0.90))
            tail_frame = known.loc[known["realized_to_implied"].ge(threshold)]
            capture = float(tail_frame["state_category"].eq("KNOWN_BLOCK").mean())
            baseline = float(known["state_category"].eq("KNOWN_BLOCK").mean())
            tail = {
                "threshold": threshold,
                "tail_days": len(tail_frame),
                "blocked_tail_days": int(tail_frame["state_category"].eq("KNOWN_BLOCK").sum()),
                "block_capture_rate": capture,
                "baseline_block_rate": baseline,
                "capture_lift": capture / baseline if baseline > 0 else None,
            }
        allowed_mean = by_category["ALLOW"]["mean_realized_to_implied"]
        blocked_mean = by_category["KNOWN_BLOCK"]["mean_realized_to_implied"]
        result[horizon] = {
            "known_days": len(known),
            "by_category": by_category,
            "allow_minus_block_realized_to_implied": (
                float(allowed_mean - blocked_mean)
                if allowed_mean is not None and blocked_mean is not None
                else None
            ),
            "tail": tail,
            "risk_unit_spearman_to_realized_to_implied": _spearman(
                known["risk_unit"], known["realized_to_implied"]
            ),
            "risk_unit_spearman_to_normalized_max_move": _spearman(
                known["risk_unit"], known["normalized_max_move"]
            ),
        }
    return result


def summarize_settlement_state_paths(
    ledger: pd.DataFrame,
    opportunity_panel: pd.DataFrame,
    runtime: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fixed = opportunity_panel.loc[
        opportunity_panel["horizon"].eq(PRIMARY_HORIZON),
        ["session_date", "pnl_per_combo", "return_on_max_loss", "defined_max_loss"],
    ].drop_duplicates("session_date", keep="last")
    fixed = fixed.rename(
        columns={
            "session_date": "entry_date",
            "pnl_per_combo": "fixed_to_7dte_pnl",
            "return_on_max_loss": "fixed_to_7dte_return_on_max_loss",
            "defined_max_loss": "fixed_defined_max_loss",
        }
    )
    result: dict[str, Any] = {}
    for mode in STATE_PATH_MODES:
        frame = ledger.loc[ledger["mode"].eq(mode)].copy()
        total_risk = float(frame["defined_max_loss"].sum()) if len(frame) else 0.0
        item: dict[str, Any] = {
            "label": STATE_PATH_LABELS[mode],
            "closed_cycles": len(frame),
            "total_pnl_per_one_combo_cycles": float(frame["pnl_per_combo"].sum())
            if len(frame)
            else 0.0,
            "sum_defined_max_loss": total_risk,
            "pnl_over_sum_defined_max_loss": float(frame["pnl_per_combo"].sum()) / total_risk
            if total_risk > 0
            else None,
            "mean_return_on_max_loss": float(frame["return_on_max_loss"].mean())
            if len(frame)
            else None,
            "median_return_on_max_loss": float(frame["return_on_max_loss"].median())
            if len(frame)
            else None,
            "win_rate": float(frame["pnl_per_combo"].gt(0).mean()) if len(frame) else None,
            "worst_return_on_max_loss": float(frame["return_on_max_loss"].min())
            if len(frame)
            else None,
            "average_holding_calendar_days": float(frame["holding_calendar_days"].mean())
            if len(frame)
            else None,
            "exit_reason_counts": {
                str(reason): int(count)
                for reason, count in frame["exit_reason"].value_counts().items()
            }
            if len(frame)
            else {},
            **runtime[mode],
        }
        if mode != "STATIC_KNOWN_UNIVERSE" and len(frame):
            matched = frame.merge(fixed, on="entry_date", how="inner", validate="one_to_one")
            matched_risk = float(matched["defined_max_loss"].sum())
            state_pnl = float(matched["pnl_per_combo"].sum())
            fixed_pnl = float(matched["fixed_to_7dte_pnl"].sum())
            item["matched_entry_exit_value"] = {
                "matched_cycles": len(matched),
                "state_exit_total_pnl": state_pnl,
                "fixed_to_7dte_total_pnl": fixed_pnl,
                "state_exit_minus_fixed_pnl": state_pnl - fixed_pnl,
                "state_exit_pnl_over_sum_defined_loss": state_pnl / matched_risk
                if matched_risk > 0
                else None,
                "fixed_pnl_over_sum_defined_loss": fixed_pnl / matched_risk
                if matched_risk > 0
                else None,
                "state_exit_worst_return_on_max_loss": float(matched["return_on_max_loss"].min())
                if len(matched)
                else None,
                "fixed_worst_return_on_max_loss": float(
                    matched["fixed_to_7dte_return_on_max_loss"].min()
                )
                if len(matched)
                else None,
            }
        result[mode] = item
    return result


def _percent(value: Any, digits: int = 1) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _money(value: Any) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    amount = float(value)
    return f"-¥{abs(amount):,.0f}" if amount < 0 else f"¥{amount:,.0f}"


def _category_table(primary: dict[str, Any]) -> str:
    rows = []
    by_category = cast(dict[str, dict[str, Any]], primary["by_category"])
    for category in STATE_CATEGORIES:
        item = by_category[category]
        rows.append(
            "<tr>"
            f"<th>{html.escape(STATE_LABELS[category])}</th>"
            f"<td>{int(item['n'])}</td>"
            f"<td>{_percent(item['mean_return_on_max_loss'])}</td>"
            f"<td>{_percent(item['median_return_on_max_loss'])}</td>"
            f"<td>{_percent(item['win_rate'])}</td>"
            f"<td>{_percent(item['mean_max_adverse_excursion'])}</td>"
            "</tr>"
        )
    return "".join(rows)


def _risk_table(primary: dict[str, Any]) -> str:
    rows = []
    for item in cast(list[dict[str, Any]], primary["by_risk_unit"]):
        rows.append(
            "<tr>"
            f"<th>{float(item['risk_unit']):.2f}</th><td>{int(item['n'])}</td>"
            f"<td>{_percent(item['mean_return_on_max_loss'])}</td>"
            f"<td>{_percent(item['median_return_on_max_loss'])}</td>"
            f"<td>{_percent(item['win_rate'])}</td>"
            f"<td>{_percent(item['mean_max_adverse_excursion'])}</td>"
            "</tr>"
        )
    return "".join(rows)


def _horizon_table(horizons: dict[str, Any]) -> str:
    rows = []
    for horizon in HORIZON_LABELS:
        item = cast(dict[str, Any], horizons[horizon])
        tail = cast(dict[str, Any], item["tail"])
        rho = cast(dict[str, Any], item["risk_unit_spearman_to_return"])["rho"]
        rows.append(
            "<tr>"
            f"<th>{html.escape(HORIZON_LABELS[horizon])}</th>"
            f"<td>{int(cast(dict[str, Any], item['known_opportunities'])['n'])}</td>"
            f"<td>{_percent(item['allow_minus_block_mean'])}</td>"
            f"<td>{_percent(tail['block_capture_rate'])}</td>"
            f"<td>{_percent(tail['baseline_block_rate'])}</td>"
            f"<td>{'—' if rho is None else f'{float(rho):.3f}'}</td>"
            "</tr>"
        )
    return "".join(rows)


def _stress_table(stress: dict[str, Any]) -> str:
    rows = []
    for horizon, label in (("H5", "未来 5 日"), ("H10", "未来 10 日"), ("H20", "未来 20 日")):
        item = cast(dict[str, Any], stress[horizon])
        categories = cast(dict[str, dict[str, Any]], item["by_category"])
        tail = cast(dict[str, Any], item["tail"])
        rows.append(
            "<tr>"
            f"<th>{label}</th><td>{int(item['known_days'])}</td>"
            f"<td>{float(categories['ALLOW']['mean_realized_to_implied']):.3f}</td>"
            f"<td>{float(categories['KNOWN_BLOCK']['mean_realized_to_implied']):.3f}</td>"
            f"<td>{_percent(tail['block_capture_rate'])}</td>"
            f"<td>{_percent(tail['baseline_block_rate'])}</td>"
            "</tr>"
        )
    return "".join(rows)


def _state_path_table(paths: dict[str, Any]) -> str:
    rows = []
    for mode in STATE_PATH_MODES:
        item = cast(dict[str, Any], paths[mode])
        rows.append(
            "<tr>"
            f"<th>{html.escape(str(item['label']))}</th>"
            f"<td>{int(item['closed_cycles'])}</td>"
            f"<td>{_money(item['total_pnl_per_one_combo_cycles'])}</td>"
            f"<td>{_percent(item['pnl_over_sum_defined_max_loss'])}</td>"
            f"<td>{_percent(item['win_rate'])}</td>"
            f"<td>{_percent(item['worst_return_on_max_loss'])}</td>"
            f"<td>{float(item['average_holding_calendar_days']):.1f}</td>"
            "</tr>"
        )
    return "".join(rows)


def _worst_table(rows: list[dict[str, Any]]) -> str:
    rendered = []
    for item in rows[:15]:
        rendered.append(
            "<tr>"
            f"<th>{pd.Timestamp(item['session_date']).date().isoformat()}</th>"
            f"<td>{pd.Timestamp(item['expiry']).date().isoformat()}</td>"
            f"<td>{html.escape(STATE_LABELS[str(item['state_category'])])}</td>"
            f"<td>{float(item['risk_unit']):.2f}</td>"
            f"<td>{html.escape(str(item['phase']))}</td>"
            f"<td>{_percent(item['return_on_max_loss'])}</td>"
            f"<td>{_percent(item['max_adverse_excursion'])}</td>"
            f"<td>{html.escape(str(item['loss_side']))}</td>"
            "</tr>"
        )
    return "".join(rendered)


def render_timing_report_html(report: dict[str, Any], panel: pd.DataFrame) -> str:
    primary = cast(dict[str, Any], cast(dict[str, Any], report["horizons"])[PRIMARY_HORIZON])
    by_category = cast(dict[str, dict[str, Any]], primary["by_category"])
    tail = cast(dict[str, Any], primary["tail"])
    stress = cast(dict[str, Any], report["market_stress"])
    paths = cast(dict[str, Any], report["state_path_experiment"])
    known_exit = cast(dict[str, Any], paths["KNOWN_BLOCK_EXIT"])
    matched_exit = cast(dict[str, Any], known_exit["matched_entry_exit_value"])
    all_zero_exit = cast(dict[str, Any], paths["ALL_ZERO_EXIT"])
    bootstrap = cast(dict[str, Any], primary["expiry_cluster_bootstrap"])
    scatter_frame = panel.loc[
        panel["horizon"].eq(PRIMARY_HORIZON) & panel["state_category"].ne("ABSTAIN_DATA")
    ].copy()
    colors = {"ALLOW": "#ffad5a", "KNOWN_BLOCK": "#5dd6a8"}
    figure = go.Figure()
    for category in ("ALLOW", "KNOWN_BLOCK"):
        group = scatter_frame.loc[scatter_frame["state_category"].eq(category)]
        custom = (
            np.stack(
                [
                    group["phase"].astype(str).to_numpy(),
                    group["expiry"].dt.strftime("%Y-%m-%d").to_numpy(),
                    group["risk_unit"].to_numpy(),
                    group["loss_side"].astype(str).to_numpy(),
                ],
                axis=1,
            )
            if len(group)
            else np.empty((0, 4))
        )
        figure.add_trace(
            go.Scatter(
                x=group["session_date"],
                y=group["return_on_max_loss"] * 100,
                mode="markers",
                name=STATE_LABELS[category],
                marker={"color": colors[category], "size": 9, "opacity": 0.82},
                customdata=custom,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>定义损失收益 %{y:.1f}%"
                    "<br>Phase %{customdata[0]}<br>到期日 %{customdata[1]}"
                    "<br>风险单位 %{customdata[2]}<br>主要亏损侧 %{customdata[3]}"
                    "<extra>%{fullData.name}</extra>"
                ),
            )
        )
    figure.add_hline(y=0, line_width=1, line_dash="dash", line_color="#718096")
    figure.update_layout(
        template="plotly_dark",
        height=500,
        margin={"l": 58, "r": 24, "t": 28, "b": 48},
        paper_bgcolor="#101722",
        plot_bgcolor="#101722",
        legend={"orientation": "h", "y": 1.10},
        xaxis_title="机会日",
        yaxis_title="持有至 7DTE 的收益 / 建仓定义最大损失（%）",
    )
    scatter_html = pio.to_html(figure, include_plotlyjs=True, full_html=False)
    judgement = (
        "建仓择时未通过；完整状态禁做退出没有增值，只有把数据弃权也当退出才压低最差损失。"
        if report["conclusion"] == "IN_SAMPLE_TIMING_NOT_SUPPORTED"
        else "当前样本尚未形成单向结论。"
    )
    allowed = by_category["ALLOW"]
    blocked = by_category["KNOWN_BLOCK"]
    ci = cast(list[Any], bootstrap["ci95"])
    ci_text = f"[{_percent(ci[0])}, {_percent(ci[1])}]" if ci[0] is not None else "—"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatSHIX ShortVol 择时能力诊断</title><style>
:root{{--bg:#090d13;--panel:#101722;--line:#273548;--text:#eef4fb;--muted:#94a5ba;--green:#5dd6a8;--amber:#ffad5a;--red:#ff7474}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1240px;margin:auto;padding:34px 24px 70px}}h1{{font-size:32px;margin:0 0 8px}}h2{{margin:34px 0 14px;font-size:21px}}.sub,.note{{color:var(--muted)}}
.verdict{{margin:20px 0;padding:17px 19px;border:1px solid #7e3535;border-radius:12px;background:#271417;color:#ffd0d0;font-size:18px;font-weight:750}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;overflow:auto}}
.card b{{display:block;font-size:27px;margin-top:5px}}.card span{{color:var(--muted)}}table{{border-collapse:collapse;width:100%;min-width:780px}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}code{{color:#b8d6ff}}@media(max-width:900px){{.cards{{grid-template-columns:1fr 1fr}}.grid{{grid-template-columns:1fr}}}}@media(max-width:560px){{.cards{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>MatSHIX × 510300 铁鹰：择时能力诊断</h1>
<div class="sub">标准化机会日 · t 时点状态只看未来结果 · 官方日结算标记 · 不计成交滑点、费用和仓位复利</div>
<div class="verdict">{html.escape(judgement)}</div>
<section class="cards"><div class="card"><span>允许区平均收益 / 最大损失</span><b style="color:var(--amber)">{_percent(allowed["mean_return_on_max_loss"])}</b></div>
<div class="card"><span>明确禁做区平均收益 / 最大损失</span><b style="color:var(--green)">{_percent(blocked["mean_return_on_max_loss"])}</b></div>
<div class="card"><span>最差 10% 被明确禁做捕获</span><b>{int(tail["blocked_bad_opportunity_days"])}/{int(tail["bad_opportunity_days"])}</b></div>
<div class="card"><span>风险单位与未来收益 Spearman</span><b>{float(cast(dict[str, Any], primary["risk_unit_spearman_to_return"])["rho"]):.3f}</b></div></section>
<h2>核心分组（持有至 7DTE）</h2><section class="panel"><table><thead><tr><th>t 时点分类</th><th>机会日</th><th>平均收益/最大损失</th><th>中位数</th><th>胜率</th><th>平均最大不利波动</th></tr></thead><tbody>{_category_table(primary)}</tbody></table></section>
<h2>每个已知机会日的事后结果</h2><section class="panel">{scatter_html}</section>
<h2>三个观察窗是否一致</h2><section class="panel"><table><thead><tr><th>结果窗</th><th>已知机会日</th><th>允许减禁做的平均差</th><th>坏日捕获率</th><th>平时禁做率</th><th>风险单位 Spearman</th></tr></thead><tbody>{_horizon_table(cast(dict[str, Any], report["horizons"]))}</tbody></table></section>
<h2>市场层复核：气象站是否至少识别了未来波动</h2><div class="sub">用 t-1 ATM IV 对未来 ETF 实现波动率归一化；小于 1 表示未来实现波动低于当时隐含波动。若允许区更低、最高 10% 更多落在禁做区，方向才正确。</div><section class="panel"><table><thead><tr><th>观察窗</th><th>已知状态日</th><th>允许区 RV/IV</th><th>禁做区 RV/IV</th><th>最高 10% RV 捕获</th><th>平时禁做率</th></tr></thead><tbody>{_stress_table(stress)}</tbody></table></section>
<h2>每日状态退出能不能救回来</h2><div class="sub">每次只持有 1 组铁鹰，用官方日结算价理想化开平仓；没有费用，也没有流动性阻断。静态控制组也只在状态数据完整的机会日建仓。</div><section class="panel"><table><thead><tr><th>状态路径</th><th>闭合周期</th><th>每周期 1 组累计 P&amp;L</th><th>P&amp;L / 累计定义损失</th><th>胜率</th><th>最差周期</th><th>平均持有自然日</th></tr></thead><tbody>{_state_path_table(paths)}</tbody></table><p class="note">同一批允许建仓日期中，完整状态禁做退出相对固定持有至 7DTE 的累计 P&amp;L 差额为 {_money(matched_exit["state_exit_minus_fixed_pnl"])}，最差周期没有改善。只有把 <code>ABSTAIN_DATA</code> 也当退出时，最差周期才压到 {_percent(all_zero_exit["worst_return_on_max_loss"])}，但收益效率进一步降至 {_percent(all_zero_exit["pnl_over_sum_defined_max_loss"])}；这属于安全弃权效果，不是已知气象状态的择时命中。</p></section>
<h2>风险单位是否有单调性</h2><section class="panel"><table><thead><tr><th>风险单位</th><th>机会日</th><th>平均收益/最大损失</th><th>中位数</th><th>胜率</th><th>平均最大不利波动</th></tr></thead><tbody>{_risk_table(primary)}</tbody></table></section>
<h2>最差已知机会日</h2><section class="panel"><table><thead><tr><th>机会日</th><th>到期日</th><th>t 时点分类</th><th>风险单位</th><th>Phase</th><th>最终收益/最大损失</th><th>最大不利波动</th><th>亏损侧</th></tr></thead><tbody>{_worst_table(cast(list[dict[str, Any]], report["worst_known_opportunities"]))}</tbody></table></section>
<h2>如何读这个结果</h2><div class="grid"><section class="panel"><strong>它回答什么</strong><p class="note">对每个当时可选出的同规则铁鹰，用建仓日与未来日的四腿官方结算价标记。若气象站有择时能力，允许区应优于明确禁做区，最差机会应更集中在禁做区。</p></section>
<section class="panel"><strong>相关性去重检查</strong><p class="note">机会日会重叠，所以另外按到期月份整簇 bootstrap。允许减禁做的 95% 区间为 {ci_text}，共 {int(bootstrap["clusters"])} 个到期簇；朴素逐日 p 值不作为主结论。</p></section>
<section class="panel"><strong>尾部来自哪里</strong><p class="note">最差 10% 共 {int(tail["bad_opportunity_days"])} 个重叠机会日、{int(tail["bad_expiry_clusters"])} 个到期簇；主要亏损侧分布为 {html.escape(str(tail["loss_side_counts"]))}。这避免把同一轮行情误称为多个独立事件。</p></section>
<section class="panel"><strong>数据弃权不记功</strong><p class="note"><code>ABSTAIN_DATA</code> 只表示状态输入不完整，不算气象站成功避险。主比较只在 <code>ALLOW</code> 与 <code>KNOWN_BLOCK</code> 之间进行。</p></section>
<section class="panel"><strong>执行是第二问题</strong><p class="note">本诊断刻意不声称这些结算价可以真实成交；它先回答状态方向是否正确。成交、费用、四腿流动性和仓位路径应在方向成立后作为二级压力测试。</p></section></div>
</main></body></html>"""


def run_shortvol_timing_diagnostic(
    project_dir: Path,
    aetf_root: Path,
    *,
    output_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> TimingArtifacts:
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
        raise FileNotFoundError(f"Timing diagnostic inputs are missing: {missing}")

    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    connection.execute("SET memory_limit = '8GB'")
    notify("构造 2023 年以来的 510300 标准化机会日")
    etf_minutes = _extract_etf_minutes(connection, source)
    etf_marks = pd.read_parquet(processed / "etf_mark.parquet")
    etf_marks = etf_marks.loc[
        etf_marks["underlying_symbol"].eq("510300.SH"),
        ["session_date", "etf_mark", "tr_mark"],
    ]
    etf_marks = _date_column(etf_marks).drop_duplicates("session_date", keep="last")
    calendar = etf_minutes.merge(etf_marks, on="session_date", how="inner").sort_values(
        "session_date"
    )
    calendar = calendar.loc[
        calendar["session_date"].between("2023-01-03", "2026-06-05")
    ].reset_index(drop=True)
    signals = _load_signal_calendar(processed, pd.DatetimeIndex(calendar["session_date"]))
    calendar = calendar.merge(signals, on="session_date", how="left", validate="one_to_one")
    contracts = _standard_contracts(source)
    surface = _surface_map(processed)
    candidates, selection_rejects = select_condor_candidates(calendar, contracts, surface)
    if candidates.empty:
        connection.close()
        raise ValueError("No valid iron-condor timing opportunities were selected")
    codes = pd.DataFrame(
        {"code": pd.unique(candidates[[f"{name}_code" for name in LEG_NAMES]].to_numpy().ravel())}
    )
    notify(f"提取 {len(codes)} 个标准合约的官方日结算标记")
    option_marks = _extract_option_marks(connection, source, codes)
    connection.close()

    notify("计算 5 日、10 日与持有至 7DTE 的无成本事后结果")
    panel = build_timing_opportunity_panel(calendar, candidates, option_marks)
    if panel.empty:
        raise ValueError("No complete four-leg settlement outcomes were available")
    notify("用未来 ETF 实现波动复核气象站的纯市场分类方向")
    market_stress_panel = build_market_stress_panel(calendar, contracts, surface)
    if market_stress_panel.empty:
        raise ValueError("No lagged-IV market stress outcomes were available")
    notify("用日结算价运行无流动性阻断的状态退出路径")
    state_path_ledger, state_path_runtime = simulate_settlement_state_paths(
        calendar, candidates, option_marks
    )
    if state_path_ledger.empty:
        raise ValueError("No settlement-only state paths were closed")
    state_path_summary = summarize_settlement_state_paths(
        state_path_ledger, panel, state_path_runtime
    )
    report = summarize_timing_panel(panel)
    static_path = state_path_summary["STATIC_KNOWN_UNIVERSE"]
    known_exit_path = state_path_summary["KNOWN_BLOCK_EXIT"]
    matched_exit = cast(dict[str, Any], known_exit_path["matched_entry_exit_value"])
    exit_reduces_loss = float(matched_exit["state_exit_minus_fixed_pnl"]) > 0
    return_edge = float(known_exit_path["pnl_over_sum_defined_max_loss"]) > float(
        static_path["pnl_over_sum_defined_max_loss"]
    )
    if report["conclusion"] == "IN_SAMPLE_TIMING_NOT_SUPPORTED" and exit_reduces_loss:
        overall = (
            "ENTRY_TIMING_NOT_SUPPORTED_EXIT_RISK_REDUCTION_WITH_RETURN_EDGE"
            if return_edge
            else "ENTRY_TIMING_NOT_SUPPORTED_EXIT_RISK_REDUCTION_WITHOUT_RETURN_EDGE"
        )
    else:
        overall = str(report["conclusion"])
    report.update(
        {
            "overall_interpretation": overall,
            "market_stress": summarize_market_stress_panel(market_stress_panel),
            "state_path_experiment": state_path_summary,
            "period": {
                "source_start": pd.Timestamp(calendar["session_date"].min()),
                "source_end": pd.Timestamp(calendar["session_date"].max()),
                "first_known_opportunity": pd.Timestamp(
                    panel.loc[panel["state_category"].ne("ABSTAIN_DATA"), "session_date"].min()
                ),
                "common_state_start": COMMON_START,
            },
            "universe": {
                "sessions": len(calendar),
                "selected_candidate_sessions": len(candidates),
                "selection_rejections": len(selection_rejects),
                "option_codes": len(codes),
                "opportunity_outcomes": len(panel),
                "market_stress_outcomes": len(market_stress_panel),
                "state_path_closed_cycles": len(state_path_ledger),
            },
            "integrity_checks": {
                "weather_signal_on_or_after_opportunity": int(
                    panel["weather_signal_session_date"]
                    .ge(panel["session_date"])
                    .fillna(False)
                    .sum()
                ),
                "minimum_primary_path_mark_coverage": float(
                    panel.loc[panel["horizon"].eq(PRIMARY_HORIZON), "path_mark_coverage"].min()
                ),
                "nonpositive_entry_credit_rows": int(panel["entry_credit"].le(0).sum()),
                "exit_after_expiry_rows": int(panel["exit_date"].gt(panel["expiry"]).sum()),
            },
            "methodology": {
                "entry_state": "MatSHIX state available before the opportunity session",
                "option_selection": "Same frozen 25-45 DTE, nearest-35, 20-delta iron-condor selector",
                "marking": "Four-leg official daily settle, close only when settle is absent",
                "costs": "None; this isolates state discrimination from execution",
                "normalization": "PnL per combo divided by entry defined maximum loss",
                "primary_outcome": "Entry settle to first exchange session at or after 7 calendar DTE",
                "tail_definition": "Bottom decile among known-state opportunity days",
                "dependence_control": "Resample complete expiry clusters, not individual opportunity days",
                "state_path_experiment": "One combo, daily settle, no costs or liquidity blocks; static entries are restricted to complete-state opportunity days",
            },
            "limitations": [
                "Opportunity days sharing an expiry are overlapping labels, not independent trades.",
                "Daily settlement marks test direction and classification, not executable bid/ask fills.",
                "The selector uses a lagged ATM-IV delta approximation and standard-contract history only.",
                "This is an in-sample policy audit; changing the map after reading outcomes requires a new version and forward test.",
                "ABSTAIN_DATA is excluded from timing credit and from the known-state comparison.",
            ],
            "sources": {
                "aetf_root": str(source),
                "opt_basic_sha256": file_hash(source / "OPTION/opt_basic.parquet"),
                "state_sha256": file_hash(processed / "daily_market_state.parquet"),
            },
        }
    )

    target = (output_dir or root / "outputs/backtest/510300_shortvol_timing").resolve()
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "report.json"
    write_json(report_path, report)
    panel_path = target / "opportunity_panel.parquet"
    panel.to_parquet(panel_path, index=False, compression="zstd")
    market_panel_path = target / "market_stress_panel.parquet"
    market_stress_panel.to_parquet(market_panel_path, index=False, compression="zstd")
    state_path_path = _atomic_text(
        target / "state_path_ledger.csv",
        state_path_ledger.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n"),
    )
    worst_frame = panel.loc[
        panel["horizon"].eq(PRIMARY_HORIZON) & panel["state_category"].ne("ABSTAIN_DATA")
    ].nsmallest(30, "return_on_max_loss")
    worst_path = _atomic_text(
        target / "worst_scenarios.csv",
        worst_frame.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n"),
    )
    html_path = _atomic_text(target / "report.html", render_timing_report_html(report, panel))
    return TimingArtifacts(
        report_path,
        panel_path,
        market_panel_path,
        state_path_path,
        worst_path,
        html_path,
        report,
    )
