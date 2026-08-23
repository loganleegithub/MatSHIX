from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from matshix.calendar import (
    add_exchange_sessions,
    exchange_decision_as_of,
    exchange_sessions_in_range,
    settlement_known_at,
    settlement_observation_time,
)
from matshix.constants import CARRIER_TO_INDEX, CARRIER_TO_UNDERLYING
from matshix.data.aetf import AetfPaths, contract_master
from matshix.serialization import canonical_json_bytes, file_hash, write_json
from matshix.storage import write_parquet
from matshix.v2.authority import (
    AUTHORITY_DOCUMENT,
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    CONSTRUCTION_PLAN_SHA256,
    ERA_DEFINITION_VERSION,
    ERA_REGISTRY,
    EXPECTED_LISTING_DATES,
    HORIZONS,
    OUTCOME_DEFINITION_VERSION,
    PARENT_ADJUDICATION_SHA256,
    PARENT_AUTHORITY_SHA256,
    ROOT_V2_AUTHORITY_SHA256,
    SAMPLING_GRID_VERSION,
    available_carrier_count,
    carrier_is_listed,
    coverage_regime,
    verify_authority_chain,
)
from matshix.v2.provenance import repository_provenance, runtime_provenance

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


@dataclass(frozen=True)
class V2OutcomeArtifacts:
    era_registry_path: Path
    outcome_ledger_path: Path
    issue_ledger_path: Path
    coverage_path: Path
    handcheck_path: Path
    coverage: dict[str, Any]


def _sha256_id(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _extract_etf_minutes(
    paths: AetfPaths, *, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    paths.validate()
    underlyings = tuple(CARRIER_TO_UNDERLYING.values())
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
                  AND code IN (?, ?, ?, ?)
            )
            SELECT
                m.code AS underlying_symbol,
                m.date AS session_date,
                m.trade_time,
                m.open,
                m.high,
                m.low,
                m.close,
                m.vol AS volume,
                m.amount,
                d.adj_factor
            FROM read_parquet(?, union_by_name=true) AS m
            JOIN daily AS d ON d.code = m.code AND d.date = m.date
            WHERE m.date BETWEEN ? AND ?
              AND m.code IN (?, ?, ?, ?)
            """,
            [
                paths.etf_daily,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                *underlyings,
                paths.etf_minutes,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                *underlyings,
            ],
        ).fetchdf()
    finally:
        connection.close()
    reverse = {value: key for key, value in CARRIER_TO_UNDERLYING.items()}
    frame["carrier_id"] = frame["underlying_symbol"].map(reverse)
    frame["economic_index_id"] = frame["carrier_id"].map(CARRIER_TO_INDEX)
    frame["session_date"] = pd.to_datetime(frame["session_date"].astype(str), format="%Y%m%d")
    frame["event_time"] = pd.to_datetime(frame["trade_time"])
    frame["time"] = frame["event_time"].dt.strftime("%H:%M:%S")
    frame["adjusted_mark"] = pd.to_numeric(frame["close"]) * pd.to_numeric(frame["adj_factor"])
    return frame.sort_values(
        ["carrier_id", "session_date", "event_time"], kind="stable"
    ).reset_index(drop=True)


def build_daily_realized_inputs(
    minutes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[tuple[str, pd.Timestamp], np.ndarray]]:
    """Build deterministic daily inputs without weather, Q, labels or strategy data."""

    required = {
        "session_date",
        "carrier_id",
        "time",
        "adjusted_mark",
        "adj_factor",
    }
    missing = required - set(minutes.columns)
    if missing:
        raise ValueError(f"minute input missing columns: {sorted(missing)}")
    frame = minutes.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["adjusted_mark"] = pd.to_numeric(frame["adjusted_mark"], errors="coerce")
    frame["adj_factor"] = pd.to_numeric(frame["adj_factor"], errors="coerce")
    duplicate_counts = frame.groupby(["carrier_id", "session_date", "time"]).size()
    conflicting = duplicate_counts.loc[duplicate_counts > 1]
    if not conflicting.empty:
        raise ValueError("duplicate carrier/session/minute rows are not allowed")

    daily_records: list[dict[str, Any]] = []
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray] = {}
    prior_close: dict[str, tuple[pd.Timestamp, float, float]] = {}
    for (carrier, session), group in frame.groupby(["carrier_id", "session_date"], sort=True):
        carrier_id = str(carrier)
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
        prior = prior_close.get(carrier_id)
        expected_prior = add_exchange_sessions(session_value, -1)
        overnight: float | None = None
        factor_change = False
        if (
            prior is not None
            and prior[0] == expected_prior
            and "09:30:00" in marks
            and np.isfinite(factor)
        ):
            overnight = math.log(float(marks["09:30:00"]) / prior[1])
            factor_change = not math.isclose(factor, prior[2], rel_tol=0.0, abs_tol=1e-12)
        valid = (
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
        record = {
            "session_date": session_value,
            "carrier_id": carrier_id,
            "economic_index_id": CARRIER_TO_INDEX[carrier_id],
            "mark_0930": marks.get("09:30:00"),
            "mark_1456": marks.get("14:56:00"),
            "mark_1500": marks.get("15:00:00"),
            "prior_mark_1500": None if prior is None else prior[1],
            "adj_factor": factor,
            "prior_adj_factor": None if prior is None else prior[2],
            "daily_intraday_variance": intraday_variance,
            "daily_overnight_variance": overnight_variance,
            "daily_total_variance": intraday_variance + overnight_variance if valid else math.nan,
            "overnight_log_return": overnight,
            "valid_bar_count": len(intraday_returns),
            "expected_bar_count": EXPECTED_INTRADAY_RETURNS,
            "corporate_action_status": "ADJUSTED_FACTOR_CHANGE"
            if factor_change
            else "NO_FACTOR_CHANGE",
            "daily_status": "OK" if valid else "CENSORED",
            "issues": "|".join(issues),
            "sampling_grid_version": SAMPLING_GRID_VERSION,
        }
        daily_records.append(record)
        if valid_endpoints:
            path_marks[(carrier_id, session_value)] = np.asarray(endpoint_values, dtype=float)
        close = marks.get("15:00:00")
        if close is not None and np.isfinite(factor):
            prior_close[carrier_id] = (session_value, float(close), factor)
    return pd.DataFrame(daily_records), path_marks


def _listing_age_map(
    start: pd.Timestamp, end: pd.Timestamp, listing_dates: dict[str, pd.Timestamp]
) -> dict[tuple[str, pd.Timestamp], int]:
    calendar = exchange_sessions_in_range(min(listing_dates.values()), end)
    positions = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    result: dict[tuple[str, pd.Timestamp], int] = {}
    for carrier, launch in listing_dates.items():
        for session in exchange_sessions_in_range(max(start, launch), end):
            result[(carrier, pd.Timestamp(session))] = (
                positions[pd.Timestamp(session)] - positions[launch] + 1
            )
    return result


def _overlap_ids(
    forecast_sessions: pd.DatetimeIndex,
    listing_dates: dict[str, pd.Timestamp],
) -> dict[tuple[str, int], str]:
    output: dict[tuple[str, int], str] = {}
    for carrier, launch in listing_dates.items():
        eligible = [pd.Timestamp(value) for value in forecast_sessions if value >= launch]
        if not eligible:
            continue
        for horizon in HORIZONS:
            output[(carrier, horizon)] = _sha256_id(
                {
                    "carrier_id": carrier,
                    "horizon_sessions": horizon,
                    "first_target_start": add_exchange_sessions(eligible[0], 1).date().isoformat(),
                    "last_target_end": add_exchange_sessions(eligible[-1], horizon)
                    .date()
                    .isoformat(),
                    "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
                }
            )
    return output


def build_realized_outcome_ledger(
    daily: pd.DataFrame,
    path_marks: dict[tuple[str, pd.Timestamp], np.ndarray],
    *,
    forecast_sessions: pd.DatetimeIndex,
    listing_dates: dict[str, pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_frame = daily.copy()
    daily_frame["session_date"] = pd.to_datetime(daily_frame["session_date"]).dt.normalize()
    by_key = {
        (str(row["carrier_id"]), pd.Timestamp(row["session_date"])): row
        for row in daily_frame.to_dict(orient="records")
    }
    start = pd.Timestamp(forecast_sessions.min())
    end = pd.Timestamp(forecast_sessions.max())
    ages = _listing_age_map(start, end, listing_dates)
    overlap = _overlap_ids(forecast_sessions, listing_dates)
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for forecast in forecast_sessions:
        forecast_session = pd.Timestamp(forecast).normalize()
        regime = coverage_regime(forecast_session)
        carrier_count = available_carrier_count(forecast_session)
        for carrier in CARRIER_TO_INDEX:
            listed = carrier_is_listed(carrier, forecast_session)
            base = by_key.get((carrier, forecast_session))
            for horizon in HORIZONS:
                target_dates = [
                    add_exchange_sessions(forecast_session, step) for step in range(1, horizon + 1)
                ]
                target_start = target_dates[0]
                target_end = target_dates[-1]
                common = {
                    "forecast_session": forecast_session,
                    "forecast_mark_time": settlement_observation_time(forecast_session),
                    "forecast_mark_kind": "ETF_ADJUSTED_CLOSE_1500",
                    "input_known_at": settlement_known_at(forecast_session),
                    "consumer_decision_as_of": exchange_decision_as_of(forecast_session),
                    "target_start_session": target_start,
                    "target_end_session": target_end,
                    "outcome_available_at": exchange_decision_as_of(target_end),
                    "carrier_id": carrier,
                    "economic_index_id": CARRIER_TO_INDEX[carrier],
                    "coverage_regime": regime,
                    "available_carrier_count": carrier_count,
                    "listing_date": listing_dates[carrier],
                    "listing_age_sessions": ages.get((carrier, forecast_session)),
                    "horizon_sessions": horizon,
                    "date_cluster_id": f"DATE|{forecast_session.date().isoformat()}",
                    "overlap_cluster_id": overlap.get((carrier, horizon)),
                    "sampling_grid_version": SAMPLING_GRID_VERSION,
                    "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
                    "authority_version": AUTHORITY_VERSION,
                    "evidence_tier": "RESEARCH_ONLY",
                    "vintage_kind": "PROVIDER_RECONSTRUCTED",
                    "history_evidence_kind": "RETROSPECTIVE_WALK_FORWARD",
                }
                reason: str | None = None
                if not listed:
                    reason = "NOT_LISTED"
                elif base is None or base.get("mark_1500") is None:
                    reason = "MISSING_FORECAST_MARK"
                target_rows = [by_key.get((carrier, value)) for value in target_dates]
                if reason is None and (
                    any(value is None for value in target_rows)
                    or any(
                        value is not None and value.get("daily_status") != "OK"
                        for value in target_rows
                    )
                ):
                    reason = "INCOMPLETE_TARGET_WINDOW"
                target_path_marks = [path_marks.get((carrier, value)) for value in target_dates]
                if reason is None and any(value is None for value in target_path_marks):
                    reason = "INCOMPLETE_PATH_WINDOW"
                if reason is not None:
                    row = {
                        **common,
                        "rv_variance_h": None,
                        "rv_volatility_h": None,
                        "rv_intraday_h": None,
                        "rv_overnight_h": None,
                        "max_up_log_move_h": None,
                        "max_down_log_move_h": None,
                        "close_to_close_return_h": None,
                        "overnight_gap_max_h": None,
                        "valid_bar_count": 0,
                        "expected_bar_count": horizon * EXPECTED_INTRADAY_RETURNS,
                        "corporate_action_status": None,
                        "q_variance_h": None,
                        "q_expected_move_h": None,
                        "q_horizon_status": "NOT_BUILT",
                        "upside_path_breach_h": None,
                        "downside_path_breach_h": None,
                        "label_status": "NOT_LISTED" if reason == "NOT_LISTED" else "CENSORED",
                        "data_status": "NOT_LISTED" if reason == "NOT_LISTED" else "CENSORED",
                        "issues": reason,
                    }
                    rows.append(row)
                    if reason != "NOT_LISTED":
                        issues.append(
                            {
                                "forecast_session": forecast_session,
                                "carrier_id": carrier,
                                "horizon_sessions": horizon,
                                "issue": reason,
                                "target_start_session": target_start,
                                "target_end_session": target_end,
                                "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
                            }
                        )
                    continue
                assert base is not None
                complete_rows = [value for value in target_rows if value is not None]
                complete_paths = [value for value in target_path_marks if value is not None]
                intraday_sum = sum(
                    float(value["daily_intraday_variance"]) for value in complete_rows
                )
                overnight_sum = sum(
                    float(value["daily_overnight_variance"]) for value in complete_rows
                )
                rv_intraday = 252.0 / horizon * intraday_sum
                rv_overnight = 252.0 / horizon * overnight_sum
                rv_variance = rv_intraday + rv_overnight
                all_marks = np.concatenate(complete_paths)
                frozen_mark = float(base["mark_1500"])
                moves = np.log(all_marks / frozen_mark)
                factors = [str(value["corporate_action_status"]) for value in complete_rows]
                row = {
                    **common,
                    "rv_variance_h": rv_variance,
                    "rv_volatility_h": math.sqrt(rv_variance),
                    "rv_intraday_h": rv_intraday,
                    "rv_overnight_h": rv_overnight,
                    "max_up_log_move_h": max(float(moves.max()), 0.0),
                    "max_down_log_move_h": max(float(-moves.min()), 0.0),
                    "close_to_close_return_h": math.log(
                        float(complete_rows[-1]["mark_1500"]) / frozen_mark
                    ),
                    "overnight_gap_max_h": max(
                        abs(float(value["overnight_log_return"])) for value in complete_rows
                    ),
                    "valid_bar_count": sum(
                        int(value["valid_bar_count"]) for value in complete_rows
                    ),
                    "expected_bar_count": horizon * EXPECTED_INTRADAY_RETURNS,
                    "corporate_action_status": "ADJUSTED_FACTOR_CHANGE"
                    if "ADJUSTED_FACTOR_CHANGE" in factors
                    else "NO_FACTOR_CHANGE",
                    "q_variance_h": None,
                    "q_expected_move_h": None,
                    "q_horizon_status": "NOT_BUILT",
                    "upside_path_breach_h": None,
                    "downside_path_breach_h": None,
                    "label_status": "OBSERVED",
                    "data_status": "OK",
                    "issues": "",
                }
                rows.append(row)
    ledger = pd.DataFrame(rows).sort_values(
        ["forecast_session", "carrier_id", "horizon_sessions"], kind="stable"
    )
    issue_frame = pd.DataFrame(issues)
    return ledger.reset_index(drop=True), issue_frame.reset_index(drop=True)


def build_era_registry_frame(listing_dates: dict[str, pd.Timestamp]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for era in ERA_REGISTRY:
        for carrier in CARRIER_TO_INDEX:
            rows.append(
                {
                    "coverage_regime": era["coverage_regime"],
                    "start_session": era["start_session"],
                    "end_session": era["end_session"],
                    "carrier_id": carrier,
                    "economic_index_id": CARRIER_TO_INDEX[carrier],
                    "listing_date": listing_dates[carrier],
                    "carrier_available": carrier in era["available_carriers"],
                    "available_carrier_count": era["available_carrier_count"],
                    "market_breadth_allowed": era["market_breadth_allowed"],
                    "era_definition_version": ERA_DEFINITION_VERSION,
                }
            )
    return pd.DataFrame(rows)


def _render_handcheck(coverage: dict[str, Any], ledger: pd.DataFrame) -> str:
    observed = ledger.loc[ledger["label_status"].eq("OBSERVED")]
    example = observed.sort_values(["forecast_session", "carrier_id", "horizon_sessions"]).iloc[0]
    lines = [
        "# MatSHIX V2.1.1 H1/H2 handcheck",
        "",
        f"- Authority: `{AUTHORITY_VERSION}`",
        f"- Outcome definition: `{OUTCOME_DEFINITION_VERSION}`",
        f"- Sampling grid: `{SAMPLING_GRID_VERSION}`",
        f"- Era/list-date gate: `{'PASS' if coverage['gates']['listing_dates_match'] else 'FAIL'}`",
        f"- Outcome integrity gate: `{coverage['gates']['outcome_integrity']}`",
        "- Strategy/weather inputs used: `false`",
        "",
        "## Frozen arithmetic",
        "",
        "`daily_total_variance = overnight^2 + sum(48 intraday five-minute returns^2)`",
        "",
        "`rv_variance_h = (252/H) * sum(daily_total_variance)`",
        "",
        "午休只用一次 `11:30 -> 13:05` return；不 forward-fill，不生成伪 0。",
        "Path outcome 以 forecast t 的复权 ETF 15:00 mark 为冻结基准。",
        "",
        "## First complete real row",
        "",
        f"- forecast/carrier/H: `{pd.Timestamp(example['forecast_session']).date()}` / "
        f"`{example['carrier_id']}` / `{int(example['horizon_sessions'])}`",
        f"- target: `{pd.Timestamp(example['target_start_session']).date()}` -> "
        f"`{pd.Timestamp(example['target_end_session']).date()}`",
        f"- valid/expected intraday returns: `{int(example['valid_bar_count'])}` / "
        f"`{int(example['expected_bar_count'])}`",
        f"- annualized variance: `{float(example['rv_variance_h']):.12f}`",
        f"- intraday/overnight: `{float(example['rv_intraday_h']):.12f}` / "
        f"`{float(example['rv_overnight_h']):.12f}`",
        f"- up/down max log move: `{float(example['max_up_log_move_h']):.12f}` / "
        f"`{float(example['max_down_log_move_h']):.12f}`",
        "",
        "## Boundary",
        "",
        "H2 只建立 raw outcome。H10/H20 exact Q、breach 标签与 Q−P 尚未施工，"
        "对应字段保持 `NOT_BUILT/null`，不得补零。",
        "",
    ]
    action = coverage.get("corporate_action_handcheck")
    if action is not None:
        lines.extend(
            [
                "## Corporate-action handcheck",
                "",
                f"- carrier/session: `{action['carrier_id']}` / `{action['session_date']}`",
                f"- prior/current adj_factor: `{action['prior_adj_factor']}` / "
                f"`{action['adj_factor']}`",
                f"- adjusted prior 15:00/current 09:30: `{action['prior_mark_1500']}` / "
                f"`{action['mark_0930']}`",
                f"- recomputed overnight log return: `{action['recomputed_overnight_log_return']}`",
                f"- stored overnight log return: `{action['stored_overnight_log_return']}`",
                f"- handcheck: `{'PASS' if action['passed'] else 'FAIL'}`",
                "",
            ]
        )
    return "\n".join(lines)


def run_v2_outcome_build(
    *,
    project_dir: Path,
    aetf_root: Path,
    start: str | None = None,
    end: str | None = None,
) -> V2OutcomeArtifacts:
    project = project_dir.expanduser().resolve()
    authority_chain = verify_authority_chain(project)
    paths = AetfPaths.from_root(aetf_root)
    manifest = json.loads(
        (project / "outputs/v2_baseline/v1_manifest.json").read_text(encoding="utf-8")
    )
    start_session = pd.Timestamp(start or manifest["source"]["start_session"])
    end_session = pd.Timestamp(end or manifest["source"]["end_session"])
    forecast_sessions = exchange_sessions_in_range(start_session, end_session)
    prior_session = add_exchange_sessions(start_session, -1)
    minutes = _extract_etf_minutes(paths, start=prior_session, end=end_session)
    daily, path_marks = build_daily_realized_inputs(minutes)

    contracts = contract_master(paths)
    listing_dates = {
        str(carrier): pd.Timestamp(value).normalize()
        for carrier, value in contracts.groupby("carrier_id")["list_date"].min().items()
    }
    listing_match = listing_dates == EXPECTED_LISTING_DATES
    if not listing_match:
        raise ValueError(f"contract-master list dates differ from Authority: {listing_dates}")
    era_registry = build_era_registry_frame(listing_dates)
    ledger, issues = build_realized_outcome_ledger(
        daily,
        path_marks,
        forecast_sessions=forecast_sessions,
        listing_dates=listing_dates,
    )
    processed = project / "data/processed/v2_1"
    output = project / "outputs/v2_1_outcomes"
    era_path = write_parquet(era_registry, processed / "era_registry.parquet")
    ledger_path = write_parquet(ledger, processed / "realized_outcome_ledger.parquet")
    issue_path = write_parquet(issues, processed / "outcome_issue_ledger.parquet")
    action_days = daily.loc[
        daily["corporate_action_status"].eq("ADJUSTED_FACTOR_CHANGE")
        & daily["daily_status"].eq("OK")
    ].copy()
    action_handcheck: dict[str, Any] | None = None
    action_pass = True
    if not action_days.empty:
        action_row = action_days.sort_values(["session_date", "carrier_id"]).iloc[0]
        recomputed = math.log(float(action_row["mark_0930"]) / float(action_row["prior_mark_1500"]))
        stored = float(action_row["overnight_log_return"])
        action_pass = math.isclose(recomputed, stored, rel_tol=0.0, abs_tol=1e-15)
        action_handcheck = {
            "carrier_id": str(action_row["carrier_id"]),
            "session_date": pd.Timestamp(action_row["session_date"]).date().isoformat(),
            "prior_adj_factor": float(action_row["prior_adj_factor"]),
            "adj_factor": float(action_row["adj_factor"]),
            "prior_mark_1500": float(action_row["prior_mark_1500"]),
            "mark_0930": float(action_row["mark_0930"]),
            "recomputed_overnight_log_return": recomputed,
            "stored_overnight_log_return": stored,
            "passed": action_pass,
        }
    observed = ledger["label_status"].eq("OBSERVED")
    nonlisted = ledger["label_status"].eq("NOT_LISTED")
    censored = ledger["label_status"].eq("CENSORED")
    integrity = bool(
        listing_match
        and ledger.loc[observed, "rv_variance_h"].gt(0).all()
        and ledger.loc[observed, "valid_bar_count"]
        .eq(ledger.loc[observed, "expected_bar_count"])
        .all()
        and ledger.loc[nonlisted, "rv_variance_h"].isna().all()
        and ledger.loc[censored, "rv_variance_h"].isna().all()
        and ledger["q_variance_h"].isna().all()
        and ledger["upside_path_breach_h"].isna().all()
        and action_pass
    )
    coverage: dict[str, Any] = {
        "authority_document": AUTHORITY_DOCUMENT,
        "authority_version": AUTHORITY_VERSION,
        "authority_sha256": AUTHORITY_SHA256,
        "parent_authority_sha256": PARENT_AUTHORITY_SHA256,
        "root_v2_authority_sha256": ROOT_V2_AUTHORITY_SHA256,
        "parent_adjudication_sha256": PARENT_ADJUDICATION_SHA256,
        "construction_plan_sha256": CONSTRUCTION_PLAN_SHA256,
        "authority_chain": authority_chain,
        "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
        "sampling_grid_version": SAMPLING_GRID_VERSION,
        "repository": repository_provenance(project),
        "runtime": runtime_provenance(),
        "cohort": {
            "kind": "FULL_RETROSPECTIVE_RECONSTRUCTION",
            "start_session": start_session.date().isoformat(),
            "end_session": end_session.date().isoformat(),
        },
        "evidence_boundary": {
            "inputs": [
                str(Path(aetf_root).expanduser().resolve() / "ETF/1m_etf"),
                str(Path(aetf_root).expanduser().resolve() / "ETF/1d_etf_price"),
                str(Path(aetf_root).expanduser().resolve() / "OPTION/opt_basic.parquet"),
                "outputs/v2_baseline/v1_manifest.json",
            ],
            "weather_inputs_used": False,
            "strategy_inputs_used": False,
            "future_outcome_used_as_feature": False,
        },
        "inputs": {
            "aetf_root": str(Path(aetf_root).expanduser().resolve()),
            "etf_minute_glob": paths.etf_minutes,
            "etf_daily_glob": paths.etf_daily,
            "option_contracts": str(paths.option_contracts),
            "option_contracts_sha256": file_hash(paths.option_contracts),
            "aetf_readme": str(paths.readme),
            "aetf_readme_sha256": file_hash(paths.readme),
            "v1_manifest": "outputs/v2_baseline/v1_manifest.json",
            "v1_manifest_sha256": file_hash(project / "outputs/v2_baseline/v1_manifest.json"),
        },
        "source_range": [start_session.date().isoformat(), end_session.date().isoformat()],
        "forecast_sessions": len(forecast_sessions),
        "rows": len(ledger),
        "status_counts": {
            str(key): int(value) for key, value in ledger["label_status"].value_counts().items()
        },
        "observed_by_carrier_horizon": (
            ledger.loc[observed]
            .groupby(["carrier_id", "horizon_sessions"])
            .size()
            .rename("rows")
            .reset_index()
            .to_dict(orient="records")
        ),
        "corporate_action_status_counts": {
            str(key): int(value)
            for key, value in ledger.loc[observed, "corporate_action_status"].value_counts().items()
        },
        "corporate_action_days": len(action_days),
        "corporate_action_handcheck": action_handcheck,
        "issue_counts": {
            str(key): int(value) for key, value in issues["issue"].value_counts().items()
        }
        if not issues.empty
        else {},
        "gates": {
            "listing_dates_match": listing_match,
            "not_listed_is_null": bool(ledger.loc[nonlisted, "rv_variance_h"].isna().all()),
            "censored_is_null": bool(ledger.loc[censored, "rv_variance_h"].isna().all()),
            "observed_bar_counts_complete": bool(
                ledger.loc[observed, "valid_bar_count"]
                .eq(ledger.loc[observed, "expected_bar_count"])
                .all()
            ),
            "q_not_prematurely_built": bool(ledger["q_variance_h"].isna().all()),
            "corporate_action_handcheck": action_pass,
            "outcome_integrity": "PASS" if integrity else "FAIL",
        },
        "artifacts": {
            "era_registry": str(era_path.relative_to(project)),
            "outcome_ledger": str(ledger_path.relative_to(project)),
            "issue_ledger": str(issue_path.relative_to(project)),
            "era_registry_sha256": file_hash(era_path),
            "outcome_ledger_sha256": file_hash(ledger_path),
            "issue_ledger_sha256": file_hash(issue_path),
        },
    }
    coverage_path = output / "coverage.json"
    write_json(coverage_path, coverage)
    handcheck_path = output / "handcheck.md"
    handcheck_path.parent.mkdir(parents=True, exist_ok=True)
    handcheck_path.write_text(_render_handcheck(coverage, ledger), encoding="utf-8")
    return V2OutcomeArtifacts(
        era_path,
        ledger_path,
        issue_path,
        coverage_path,
        handcheck_path,
        coverage,
    )
