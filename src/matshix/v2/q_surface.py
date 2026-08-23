from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from matshix.calendar import expiry_timestamp, surface_cutoff, year_fraction_act365f
from matshix.constants import (
    CARRIER_TO_INDEX,
    CARRIER_TO_OPTION_CODE,
    EXCLUDED_OPTION_CODES,
)
from matshix.data.aetf import AetfPaths, extract_history
from matshix.serialization import file_hash, write_json
from matshix.storage import write_parquet
from matshix.surface.research import ResearchCarrierSurface, build_carrier_surface
from matshix.v2.authority import AUTHORITY_VERSION, OUTCOME_DEFINITION_VERSION, Q_DEFINITION_VERSION

Progress = Callable[[str], None]


@dataclass(frozen=True)
class ExactQResult:
    q_horizon_status: str
    target_year_fraction: float
    target_calendar_days: float
    q_total_variance: float | None
    q_variance: float | None
    q_expected_move: float | None
    lower_expiry: str | None
    upper_expiry: str | None
    method: str
    valid_strikes: int | None
    put_count: int | None
    call_count: int | None
    parity_pair_count: int | None


@dataclass(frozen=True)
class V2QArtifacts:
    q_ledger_path: Path
    robustness_ledger_path: Path
    enriched_outcome_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


def exact_target_q(
    surface: ResearchCarrierSurface,
    *,
    target_year_fraction: float,
) -> ExactQResult:
    """Strictly bracket a target and interpolate total variance, never a proxy."""

    target_days = target_year_fraction * 365.0
    valid = sorted(
        [
            value
            for value in surface.expiries
            if value.variance is not None
            and np.isfinite(value.variance)
            and float(value.variance) > 0
            and value.dte > 7
        ],
        key=lambda value: value.dte,
    )
    exact = next(
        (value for value in valid if math.isclose(value.dte, target_days, abs_tol=1e-10)),
        None,
    )
    lower = exact or next((value for value in reversed(valid) if value.dte < target_days), None)
    upper = exact or next((value for value in valid if value.dte > target_days), None)
    if lower is None or upper is None:
        return ExactQResult(
            "NO_EXACT_BRACKET",
            target_year_fraction,
            target_days,
            None,
            None,
            None,
            None if lower is None else lower.expiry,
            None if upper is None else upper.expiry,
            "UNAVAILABLE",
            None,
            None,
            None,
            None,
        )
    assert lower.variance is not None
    assert upper.variance is not None
    if lower.expiry == upper.expiry:
        total_variance = target_year_fraction * float(lower.variance)
        method = "EXACT_MATURITY"
    else:
        lower_t = lower.dte / 365.0
        upper_t = upper.dte / 365.0
        weight = (target_year_fraction - lower_t) / (upper_t - lower_t)
        total_variance = (1.0 - weight) * lower_t * float(
            lower.variance
        ) + weight * upper_t * float(upper.variance)
        method = "TOTAL_VARIANCE_EXACT_BRACKET"
    q_variance = total_variance / target_year_fraction
    if not np.isfinite(q_variance) or q_variance <= 0 or total_variance <= 0:
        return ExactQResult(
            "STATIC_ARBITRAGE_VIOLATION",
            target_year_fraction,
            target_days,
            None,
            None,
            None,
            lower.expiry,
            upper.expiry,
            method,
            None,
            None,
            None,
            None,
        )
    return ExactQResult(
        "OK",
        target_year_fraction,
        target_days,
        total_variance,
        q_variance,
        math.sqrt(total_variance),
        lower.expiry,
        upper.expiry,
        method,
        min(lower.valid_total_strikes, upper.valid_total_strikes),
        min(lower.valid_otm_puts, upper.valid_otm_puts),
        min(lower.valid_otm_calls, upper.valid_otm_calls),
        min(lower.parity_pair_count, upper.parity_pair_count),
    )


def wing_dominance(down_skew: object, up_skew: object) -> str | None:
    down = pd.to_numeric(pd.Series([down_skew]), errors="coerce").iloc[0]
    up = pd.to_numeric(pd.Series([up_skew]), errors="coerce").iloc[0]
    if pd.isna(down) or pd.isna(up):
        return None
    if math.isclose(float(down), float(up), rel_tol=0.0, abs_tol=1e-12):
        return "TIE"
    return "DOWN" if float(down) > float(up) else "UP"


def _surface_rows(
    option_prices: pd.DataFrame,
    etf_marks: pd.DataFrame,
    *,
    price_proxy: str,
    progress: Progress | None,
) -> tuple[pd.DataFrame, dict[tuple[pd.Timestamp, str], ResearchCarrierSurface]]:
    spots = {
        (pd.Timestamp(row["session_date"]), str(row["carrier_id"])): float(row["etf_mark"])
        for row in etf_marks.to_dict(orient="records")
    }
    built: dict[tuple[pd.Timestamp, str], ResearchCarrierSurface] = {}
    records: list[dict[str, Any]] = []
    groups = list(option_prices.groupby(["session_date", "carrier_id"], sort=True))
    for index, ((session, carrier), group) in enumerate(groups, start=1):
        session_value = pd.Timestamp(session).normalize()
        carrier_id = str(carrier)
        spot = spots.get((session_value, carrier_id))
        if spot is None or not np.isfinite(spot) or spot <= 0:
            continue
        surface = build_carrier_surface(
            group,
            session_date=session_value.date().isoformat(),
            carrier_id=carrier_id,
            economic_index_id=CARRIER_TO_INDEX[carrier_id],
            spot=spot,
            observation_time=surface_cutoff(session_value),
        )
        built[(session_value, carrier_id)] = surface
        records.append(
            {
                "forecast_session": session_value,
                "carrier_id": carrier_id,
                "economic_index_id": CARRIER_TO_INDEX[carrier_id],
                "price_proxy": price_proxy,
                "surface_status": surface.surface_status,
                "input_contracts": surface.input_contracts,
                "eligible_contracts": surface.eligible_contracts,
                "iv30_mf": surface.iv30_mf,
                "iv30_method": surface.iv30_method,
                "atm_iv30": surface.atm_iv30,
                "iv_25d_put30": surface.iv_25d_put30,
                "iv_25d_call30": surface.iv_25d_call30,
                "down_skew25": surface.down_skew25,
                "up_skew25": surface.up_skew25,
                "wing_dominance": wing_dominance(surface.down_skew25, surface.up_skew25),
                "issues": "|".join(surface.issues),
            }
        )
        if progress is not None and (index % 250 == 0 or index == len(groups)):
            progress(f"{price_proxy}: built {index}/{len(groups)} carrier sessions")
    return pd.DataFrame(records), built


def _extract_near_close_vwap(paths: AetfPaths, *, start: str, end: str) -> pd.DataFrame:
    paths.validate()
    option_codes = tuple(CARRIER_TO_OPTION_CODE.values())
    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    connection.execute("SET preserve_insertion_order TO false")
    try:
        frame = connection.execute(
            """
            WITH contracts AS (
                SELECT
                    code AS contract_id,
                    opt_code AS option_underlying_code,
                    call_put AS option_type,
                    exercise_price AS strike,
                    maturity_date AS expiry,
                    coalesce(per_unit, opt_multiplier) AS contract_unit,
                    symbol,
                    list_date,
                    delist_date,
                    CASE
                        WHEN per_unit = 10000
                         AND opt_multiplier = 10000
                         AND symbol NOT LIKE '%A%'
                        THEN true ELSE false
                    END AS is_standard
                FROM read_parquet(?)
                WHERE opt_code IN (?, ?, ?, ?)
            ), daily AS (
                SELECT code, date, vol, amount, oi
                FROM read_parquet(?, union_by_name=true)
                WHERE date BETWEEN ? AND ?
            ), near_close AS (
                SELECT
                    m.code,
                    m.date,
                    sum(CASE WHEN m.vol > 0 AND m.amount > 0 THEN m.vol ELSE 0 END)
                        AS window_volume,
                    sum(CASE WHEN m.vol > 0 AND m.amount > 0 THEN m.amount ELSE 0 END)
                        AS window_amount,
                    min(CASE WHEN m.vol > 0 AND m.amount > 0 THEN m.low ELSE NULL END)
                        AS window_low,
                    max(CASE WHEN m.vol > 0 AND m.amount > 0 THEN m.high ELSE NULL END)
                        AS window_high
                FROM read_parquet(?, union_by_name=true) AS m
                WHERE m.date BETWEEN ? AND ?
                  AND substr(m.trade_time, 12, 8) BETWEEN '14:52:00' AND '14:56:59'
                GROUP BY m.code, m.date
            )
            SELECT
                w.date AS session_date,
                w.code AS contract_id,
                c.option_underlying_code,
                c.option_type,
                c.strike,
                c.expiry,
                c.contract_unit,
                c.is_standard,
                w.window_volume,
                w.window_amount,
                w.window_low,
                w.window_high,
                coalesce(d.vol, 0) AS daily_volume,
                coalesce(d.amount, 0) AS daily_amount,
                coalesce(d.oi, 0) AS open_interest
            FROM near_close AS w
            JOIN contracts AS c ON c.contract_id = w.code
            LEFT JOIN daily AS d ON d.code = w.code AND d.date = w.date
            WHERE c.list_date <= w.date
              AND c.delist_date >= w.date
              AND w.window_volume > 0
              AND w.window_amount > 0
            """,
            [
                str(paths.option_contracts),
                *option_codes,
                paths.option_daily,
                pd.Timestamp(start).strftime("%Y%m%d"),
                pd.Timestamp(end).strftime("%Y%m%d"),
                paths.option_minutes,
                pd.Timestamp(start).strftime("%Y%m%d"),
                pd.Timestamp(end).strftime("%Y%m%d"),
            ],
        ).fetchdf()
    finally:
        connection.close()
    reverse = {value: key for key, value in CARRIER_TO_OPTION_CODE.items()}
    frame["carrier_id"] = frame["option_underlying_code"].map(reverse)
    frame["economic_index_id"] = frame["carrier_id"].map(CARRIER_TO_INDEX)
    if frame["option_underlying_code"].isin(EXCLUDED_OPTION_CODES).any():
        raise AssertionError("excluded 588080 option entered V2 Q robustness")
    frame["session_date"] = pd.to_datetime(frame["session_date"].astype(str), format="%Y%m%d")
    frame["expiry"] = pd.to_datetime(frame["expiry"].astype(str), format="%Y%m%d")
    frame["price"] = pd.to_numeric(frame["window_amount"]) / (
        pd.to_numeric(frame["window_volume"]) * pd.to_numeric(frame["contract_unit"])
    )
    consistent = (
        np.isfinite(frame["price"])
        & frame["price"].gt(0)
        & frame["price"].ge(pd.to_numeric(frame["window_low"]) - 1e-12)
        & frame["price"].le(pd.to_numeric(frame["window_high"]) + 1e-12)
    )
    return (
        frame.loc[consistent]
        .sort_values(
            ["session_date", "carrier_id", "expiry", "strike", "option_type"], kind="stable"
        )
        .reset_index(drop=True)
    )


def _empty_q(status: str, target_year_fraction: float) -> ExactQResult:
    return ExactQResult(
        status,
        target_year_fraction,
        target_year_fraction * 365.0,
        None,
        None,
        None,
        None,
        None,
        "UNAVAILABLE",
        None,
        None,
        None,
        None,
    )


def _build_q_ledger(
    metadata: pd.DataFrame,
    surface_rows: pd.DataFrame,
    surfaces: dict[tuple[pd.Timestamp, str], ResearchCarrierSurface],
    *,
    price_proxy: str,
) -> pd.DataFrame:
    surface_by_key = {
        (pd.Timestamp(row["forecast_session"]), str(row["carrier_id"])): row
        for row in surface_rows.to_dict(orient="records")
    }
    output: list[dict[str, Any]] = []
    for row in metadata.to_dict(orient="records"):
        session = pd.Timestamp(row["forecast_session"])
        carrier = str(row["carrier_id"])
        surface = surfaces.get((session, carrier))
        base = surface_by_key.get((session, carrier), {})
        target_yf = year_fraction_act365f(
            surface_cutoff(session), expiry_timestamp(pd.Timestamp(row["target_end_session"]))
        )
        if row["data_status"] == "NOT_LISTED":
            result = _empty_q("NOT_LISTED", target_yf)
        elif surface is None:
            result = _empty_q("UNOBSERVABLE", target_yf)
        else:
            result = exact_target_q(surface, target_year_fraction=target_yf)
        output.append(
            {
                "forecast_session": session,
                "carrier_id": carrier,
                "economic_index_id": row["economic_index_id"],
                "horizon_sessions": int(row["horizon_sessions"]),
                "target_start_session": row["target_start_session"],
                "target_end_session": row["target_end_session"],
                "known_at": row["input_known_at"],
                "coverage_regime": row["coverage_regime"],
                "available_carrier_count": row["available_carrier_count"],
                "listing_age_sessions": row["listing_age_sessions"],
                "price_proxy": price_proxy,
                **asdict(result),
                "surface_status": base.get("surface_status"),
                "input_contracts": base.get("input_contracts"),
                "eligible_contracts": base.get("eligible_contracts"),
                "iv30_mf": base.get("iv30_mf"),
                "iv30_method": base.get("iv30_method"),
                "atm_iv30": base.get("atm_iv30"),
                "iv_25d_put30": base.get("iv_25d_put30"),
                "iv_25d_call30": base.get("iv_25d_call30"),
                "down_skew25": base.get("down_skew25"),
                "up_skew25": base.get("up_skew25"),
                "wing_dominance": base.get("wing_dominance"),
                "liquidity_status": "POSITIVE_WINDOW_TRADES"
                if price_proxy == "NEAR_CLOSE_PRINT_VWAP_1452_1456"
                else "CLOSE_PROXY_NO_BID_ASK",
                "unit": "ANNUALIZED_VARIANCE_252",
                "q_definition_version": Q_DEFINITION_VERSION,
                "authority_version": AUTHORITY_VERSION,
                "evidence_tier": "RESEARCH_ONLY",
                "issues": base.get("issues", ""),
            }
        )
    return pd.DataFrame(output).sort_values(
        ["forecast_session", "carrier_id", "horizon_sessions"], kind="stable"
    )


def evaluate_q_robustness(main: pd.DataFrame, robust: pd.DataFrame) -> dict[str, Any]:
    keys = ["forecast_session", "carrier_id", "horizon_sessions"]
    left = main.add_prefix("main_").rename(columns={f"main_{key}": key for key in keys})
    right = robust.add_prefix("robust_").rename(columns={f"robust_{key}": key for key in keys})
    paired = left.merge(right, on=keys, how="inner")
    listed_h20 = paired.loc[
        paired["horizon_sessions"].eq(20) & paired["main_q_horizon_status"].ne("NOT_LISTED")
    ].copy()
    main_exact = listed_h20["main_q_horizon_status"].eq("OK")
    robust_exact = listed_h20["robust_q_horizon_status"].eq("OK")
    both = listed_h20.loc[main_exact & robust_exact].copy()
    main_count = int(main_exact.sum())
    paired_count = len(both)
    paired_coverage = paired_count / main_count if main_count else 0.0
    relative = (
        pd.to_numeric(both["robust_q_variance"]) - pd.to_numeric(both["main_q_variance"])
    ).abs() / pd.to_numeric(both["main_q_variance"])
    availability_agreement = float((main_exact == robust_exact).mean()) if len(listed_h20) else 0.0
    dominance = paired.loc[
        paired["horizon_sessions"].eq(20)
        & paired["main_wing_dominance"].notna()
        & paired["robust_wing_dominance"].notna()
    ]
    dominance_agreement = (
        float((dominance["main_wing_dominance"] == dominance["robust_wing_dominance"]).mean())
        if len(dominance)
        else 0.0
    )
    metrics = {
        "main_exact_h20_rows": main_count,
        "paired_exact_h20_rows": paired_count,
        "paired_eligible_coverage": paired_coverage,
        "median_absolute_relative_q_variance_delta": float(relative.median())
        if len(relative)
        else None,
        "p90_absolute_relative_q_variance_delta": float(relative.quantile(0.90))
        if len(relative)
        else None,
        "exact_bracket_availability_agreement": availability_agreement,
        "dominant_side_paired_rows": len(dominance),
        "dominant_side_agreement": dominance_agreement,
    }
    if paired_count < 126 or len(dominance) < 126 or paired_coverage < 0.70:
        verdict = "INSUFFICIENT_EVIDENCE"
        reason = "PAIRED_Q_ROBUSTNESS_COVERAGE_BELOW_FROZEN_GATE"
    else:
        passed = bool(
            relative.median() <= 0.05
            and relative.quantile(0.90) <= 0.15
            and availability_agreement >= 0.95
            and dominance_agreement >= 0.90
        )
        verdict = "PASS" if passed else "FAIL"
        reason = "FROZEN_Q_ROBUSTNESS_GATES_PASSED" if passed else "FROZEN_Q_ROBUSTNESS_GATE_FAILED"
    return {**metrics, "verdict": verdict, "reason": reason}


def enrich_outcomes_with_q(outcomes: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    keys = ["forecast_session", "carrier_id", "horizon_sessions"]
    replaceable = [
        "q_total_variance",
        "target_year_fraction",
        "method",
        "lower_expiry",
        "upper_expiry",
        "q_path_label_status",
    ]
    base = outcomes.drop(columns=[field for field in replaceable if field in outcomes.columns])
    q_fields = q[
        keys
        + [
            "q_variance",
            "q_total_variance",
            "q_expected_move",
            "q_horizon_status",
            "target_year_fraction",
            "method",
            "lower_expiry",
            "upper_expiry",
        ]
    ].rename(
        columns={
            "q_variance": "q_variance_h_v2",
            "q_expected_move": "q_expected_move_h_v2",
            "q_horizon_status": "q_horizon_status_v2",
        }
    )
    result = base.merge(q_fields, on=keys, how="left", validate="one_to_one")
    result["q_variance_h"] = result.pop("q_variance_h_v2")
    result["q_expected_move_h"] = result.pop("q_expected_move_h_v2")
    result["q_horizon_status"] = result.pop("q_horizon_status_v2")
    observable = result["label_status"].eq("OBSERVED") & result["q_horizon_status"].eq("OK")
    result["upside_path_breach_h"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result["downside_path_breach_h"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result.loc[observable, "upside_path_breach_h"] = (
        pd.to_numeric(result.loc[observable, "max_up_log_move_h"])
        > pd.to_numeric(result.loc[observable, "q_expected_move_h"])
    ).to_numpy()
    result.loc[observable, "downside_path_breach_h"] = (
        pd.to_numeric(result.loc[observable, "max_down_log_move_h"])
        > pd.to_numeric(result.loc[observable, "q_expected_move_h"])
    ).to_numpy()
    result["q_path_label_status"] = "UNKNOWN_Q"
    result.loc[observable, "q_path_label_status"] = "OBSERVED"
    result.loc[result["label_status"].eq("CENSORED"), "q_path_label_status"] = "CENSORED"
    result.loc[result["label_status"].eq("NOT_LISTED"), "q_path_label_status"] = "NOT_LISTED"
    return result


def _render_report(summary: dict[str, Any]) -> str:
    robustness = summary["robustness"]
    lines = [
        "# MatSHIX V2 H3 Q acceptance",
        "",
        f"- Authority: `{AUTHORITY_VERSION}`",
        f"- Q definition: `{Q_DEFINITION_VERSION}`",
        f"- Q gate: `{summary['q_gate']}`",
        f"- Stop required: `{str(summary['stop_required']).lower()}`",
        "- Future outcome used for Q construction/selection: `false`",
        "- Strategy input used: `false`",
        "",
        "## Exact horizon coverage",
        "",
    ]
    for row in summary["exact_coverage"]:
        lines.append(
            f"- `{row['carrier_id']}` H{row['horizon_sessions']}: "
            f"`{row['exact_rows']}/{row['listed_rows']}` = `{row['coverage']:.2%}`"
        )
    lines.extend(
        [
            "",
            "## Frozen near-close robustness gate",
            "",
            f"- verdict/reason: `{robustness['verdict']}` / `{robustness['reason']}`",
            f"- paired exact H20: `{robustness['paired_exact_h20_rows']}` / "
            f"`{robustness['main_exact_h20_rows']}` = "
            f"`{robustness['paired_eligible_coverage']:.2%}`",
            f"- median/p90 absolute relative Q variance delta: "
            f"`{robustness['median_absolute_relative_q_variance_delta']}` / "
            f"`{robustness['p90_absolute_relative_q_variance_delta']}`",
            f"- exact availability agreement: "
            f"`{robustness['exact_bracket_availability_agreement']:.2%}`",
            f"- wing dominant-side agreement: `{robustness['dominant_side_agreement']:.2%}` "
            f"over `{robustness['dominant_side_paired_rows']}` rows",
            "",
            "Q gate 非 PASS 时，Authority 要求停止，不得继续用 P、Q−P、策略收益或 proxy "
            "选择给 Q 补洞。",
            "",
        ]
    )
    return "\n".join(lines)


def run_v2_q_build(
    *,
    project_dir: Path,
    aetf_root: Path,
    progress: Progress | None = None,
) -> V2QArtifacts:
    project = project_dir.expanduser().resolve()
    outcome_path = project / "data/processed/v2/realized_outcome_ledger.parquet"
    if not outcome_path.is_file():
        raise FileNotFoundError("H2 outcome ledger must be built before H3 Q")
    outcomes = pd.read_parquet(outcome_path)
    metadata = outcomes[
        [
            "forecast_session",
            "input_known_at",
            "target_start_session",
            "target_end_session",
            "carrier_id",
            "economic_index_id",
            "horizon_sessions",
            "coverage_regime",
            "available_carrier_count",
            "listing_age_sessions",
            "data_status",
        ]
    ].copy()
    start = pd.Timestamp(metadata["forecast_session"].min()).date().isoformat()
    end = pd.Timestamp(metadata["forecast_session"].max()).date().isoformat()
    paths = AetfPaths.from_root(aetf_root)
    if progress is not None:
        progress("extracting frozen 14:56 main Q inputs")
    extraction = extract_history(paths, start=start, end=end)
    main_rows, main_surfaces = _surface_rows(
        extraction.option_prices,
        extraction.etf_marks,
        price_proxy="MINUTE_CLOSE_1456",
        progress=progress,
    )
    main_q = _build_q_ledger(metadata, main_rows, main_surfaces, price_proxy="MINUTE_CLOSE_1456")
    if progress is not None:
        progress("extracting outcome-blind 14:52-14:56 positive-trade VWAP inputs")
    robust_prices = _extract_near_close_vwap(paths, start=start, end=end)
    robust_rows, robust_surfaces = _surface_rows(
        robust_prices,
        extraction.etf_marks,
        price_proxy="NEAR_CLOSE_PRINT_VWAP_1452_1456",
        progress=progress,
    )
    robust_q = _build_q_ledger(
        metadata,
        robust_rows,
        robust_surfaces,
        price_proxy="NEAR_CLOSE_PRINT_VWAP_1452_1456",
    )
    robustness = evaluate_q_robustness(main_q, robust_q)
    enriched = enrich_outcomes_with_q(outcomes, main_q)
    processed = project / "data/processed/v2"
    output = project / "outputs/v2_q_acceptance"
    q_path = write_parquet(main_q, processed / "q_weather_ledger.parquet")
    robust_path = write_parquet(robust_q, processed / "q_robustness_ledger.parquet")
    enriched_path = write_parquet(enriched, processed / "realized_outcome_q_labeled_ledger.parquet")
    listed = main_q["q_horizon_status"].ne("NOT_LISTED")
    coverage_rows: list[dict[str, Any]] = []
    for (carrier, horizon), group in main_q.loc[listed].groupby(
        ["carrier_id", "horizon_sessions"], sort=True
    ):
        exact = int(group["q_horizon_status"].eq("OK").sum())
        coverage_rows.append(
            {
                "carrier_id": str(carrier),
                "horizon_sessions": int(horizon),
                "exact_rows": exact,
                "listed_rows": len(group),
                "coverage": exact / len(group),
            }
        )
    q_gate = str(robustness["verdict"])
    summary: dict[str, Any] = {
        "authority_version": AUTHORITY_VERSION,
        "q_definition_version": Q_DEFINITION_VERSION,
        "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
        "q_gate": q_gate,
        "stop_required": q_gate != "PASS",
        "stop_reason": None if q_gate == "PASS" else robustness["reason"],
        "evidence_boundary": {
            "main_price_proxy": "MINUTE_CLOSE_1456",
            "robustness_price_proxy": "NEAR_CLOSE_PRINT_VWAP_1452_1456",
            "formal_bid_ask_available": False,
            "future_outcome_values_used_for_q_construction": False,
            "future_outcome_values_used_for_q_proxy_selection": False,
            "strategy_inputs_used": False,
        },
        "exact_coverage": coverage_rows,
        "q_horizon_status_counts": {
            str(key): int(value) for key, value in main_q["q_horizon_status"].value_counts().items()
        },
        "robustness": robustness,
        "path_label_counts_by_horizon": [
            {
                "horizon_sessions": int(horizon),
                "upside_observed": int(group["upside_path_breach_h"].notna().sum()),
                "upside_positive": int(group["upside_path_breach_h"].fillna(False).sum()),
                "downside_observed": int(group["downside_path_breach_h"].notna().sum()),
                "downside_positive": int(group["downside_path_breach_h"].fillna(False).sum()),
            }
            for horizon, group in enriched.groupby("horizon_sessions", sort=True)
        ],
        "artifacts": {
            "q_ledger": str(q_path.relative_to(project)),
            "q_ledger_sha256": file_hash(q_path),
            "robustness_ledger": str(robust_path.relative_to(project)),
            "robustness_ledger_sha256": file_hash(robust_path),
            "enriched_outcome_ledger": str(enriched_path.relative_to(project)),
            "enriched_outcome_ledger_sha256": file_hash(enriched_path),
        },
    }
    summary_path = output / "summary.json"
    write_json(summary_path, summary)
    report_path = output / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(summary), encoding="utf-8")
    return V2QArtifacts(q_path, robust_path, enriched_path, summary_path, report_path, summary)
