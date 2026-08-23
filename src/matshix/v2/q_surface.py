from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from matshix.calendar import (
    expiry_timestamp,
    settlement_known_at,
    settlement_observation_time,
    surface_cutoff,
    year_fraction_act365f,
)
from matshix.constants import (
    CARRIER_TO_INDEX,
)
from matshix.data.aetf import AetfPaths, extract_history, extract_settlement_history
from matshix.serialization import file_hash, write_json
from matshix.storage import write_parquet
from matshix.surface.research import ResearchCarrierSurface, build_carrier_surface
from matshix.v2.authority import (
    AUTHORITY_DOCUMENT,
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    CONFIRMATION_END,
    CONFIRMATION_START,
    CONSTRUCTION_PLAN_SHA256,
    OUTCOME_DEFINITION_VERSION,
    PARENT_ADJUDICATION_SHA256,
    PARENT_AUTHORITY_SHA256,
    Q_DEFINITION_VERSION,
    ROOT_V2_AUTHORITY_SHA256,
    verify_authority_chain,
)
from matshix.v2.provenance import repository_provenance, runtime_provenance

Progress = Callable[[str], None]
ObservationTime = Callable[[pd.Timestamp], datetime]


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
    observation_time: ObservationTime = surface_cutoff,
    methodology_version: str = "MATSHIX_RESEARCH_MINUTE_CLOSE_V2",
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
            observation_time=observation_time(session_value),
            methodology_version=methodology_version,
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
                "iv60_mf": surface.iv60_mf,
                "iv60_method": surface.iv60_method,
                "iv90_mf": surface.iv90_mf,
                "iv90_method": surface.iv90_method,
                "fvar_30_90": surface.fvar_30_90,
                "fvol_30_90": surface.fvol_30_90,
                "term_log_ratio_30_90": surface.term_log_ratio_30_90,
                "atm_iv30": surface.atm_iv30,
                "iv_25d_put30": surface.iv_25d_put30,
                "iv_25d_call30": surface.iv_25d_call30,
                "rr25": surface.rr25,
                "down_skew25": surface.down_skew25,
                "up_skew25": surface.up_skew25,
                "bf25": surface.bf25,
                "wing_variance_spread": surface.wing_variance_spread,
                "wing_dominance": wing_dominance(surface.down_skew25, surface.up_skew25),
                "issues": "|".join(surface.issues),
            }
        )
        if progress is not None and (index % 250 == 0 or index == len(groups)):
            progress(f"{price_proxy}: built {index}/{len(groups)} carrier sessions")
    return pd.DataFrame(records), built


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
    observation_time: ObservationTime = surface_cutoff,
    known_at: ObservationTime = surface_cutoff,
    liquidity_status: str = "CLOSE_PROXY_NO_BID_ASK",
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
        observed_at = observation_time(session)
        target_yf = year_fraction_act365f(
            observed_at, expiry_timestamp(pd.Timestamp(row["target_end_session"]))
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
                "observation_time": observed_at,
                "known_at": known_at(session),
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
                "iv60_mf": base.get("iv60_mf"),
                "iv60_method": base.get("iv60_method"),
                "iv90_mf": base.get("iv90_mf"),
                "iv90_method": base.get("iv90_method"),
                "fvar_30_90": base.get("fvar_30_90"),
                "fvol_30_90": base.get("fvol_30_90"),
                "term_log_ratio_30_90": base.get("term_log_ratio_30_90"),
                "atm_iv30": base.get("atm_iv30"),
                "iv_25d_put30": base.get("iv_25d_put30"),
                "iv_25d_call30": base.get("iv_25d_call30"),
                "rr25": base.get("rr25"),
                "down_skew25": base.get("down_skew25"),
                "up_skew25": base.get("up_skew25"),
                "bf25": base.get("bf25"),
                "wing_variance_spread": base.get("wing_variance_spread"),
                "wing_dominance": base.get("wing_dominance"),
                "liquidity_status": liquidity_status,
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


def _moving_date_block_median_ci(
    frame: pd.DataFrame,
    *,
    block_length: int,
    seed: int,
    replicates: int,
) -> tuple[float | None, float | None]:
    if frame.empty:
        return None, None
    by_date = {
        pd.Timestamp(session): pd.to_numeric(group["signed_relative_delta"]).to_numpy(dtype=float)
        for session, group in frame.groupby("forecast_session", sort=True)
    }
    dates = sorted(by_date)
    if len(dates) < block_length:
        return None, None
    starts = np.arange(0, len(dates) - block_length + 1)
    generator = np.random.default_rng(seed)
    medians = np.empty(replicates, dtype=float)
    for replicate in range(replicates):
        sampled_dates: list[pd.Timestamp] = []
        while len(sampled_dates) < len(dates):
            start = int(generator.choice(starts))
            sampled_dates.extend(dates[start : start + block_length])
        values = np.concatenate([by_date[value] for value in sampled_dates[: len(dates)]])
        medians[replicate] = float(np.median(values))
    lower, upper = np.quantile(medians, [0.05, 0.95], method="linear")
    return float(lower), float(upper)


def _stratified_robustness(
    listed: pd.DataFrame,
    both: pd.DataFrame,
    dominance: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    listed_frame = listed.copy()
    both_frame = both.copy()
    dominance_frame = dominance.copy()
    for frame in (listed_frame, both_frame, dominance_frame):
        frame["year"] = pd.to_datetime(frame["forecast_session"]).dt.year

    def summarize(
        label: dict[str, Any],
        listed_slice: pd.DataFrame,
        both_slice: pd.DataFrame,
        dominance_slice: pd.DataFrame,
    ) -> dict[str, Any]:
        primary_exact = listed_slice["primary_q_horizon_status"].eq("OK")
        comparator_exact = listed_slice["comparator_q_horizon_status"].eq("OK")
        signed = pd.to_numeric(both_slice["signed_relative_delta"], errors="coerce").dropna()
        absolute = signed.abs()
        return {
            **label,
            "listed_h20_rows": len(listed_slice),
            "primary_exact_h20_rows": int(primary_exact.sum()),
            "paired_exact_h20_rows": len(both_slice),
            "paired_exact_coverage": (
                len(both_slice) / int(primary_exact.sum()) if int(primary_exact.sum()) else 0.0
            ),
            "exact_availability_agreement": float((primary_exact == comparator_exact).mean())
            if len(listed_slice)
            else 0.0,
            "median_signed_relative_delta": float(signed.median()) if len(signed) else None,
            "median_absolute_relative_delta": float(absolute.median()) if len(absolute) else None,
            "p90_absolute_relative_delta": float(absolute.quantile(0.90))
            if len(absolute)
            else None,
            "wing_paired_rows": len(dominance_slice),
            "wing_agreement": float(
                (
                    dominance_slice["primary_wing_dominance"]
                    == dominance_slice["comparator_wing_dominance"]
                ).mean()
            )
            if len(dominance_slice)
            else None,
        }

    output: dict[str, list[dict[str, Any]]] = {
        "by_carrier": [],
        "by_year": [],
        "by_carrier_year": [],
    }
    for carrier, group in listed_frame.groupby("carrier_id", sort=True):
        output["by_carrier"].append(
            summarize(
                {"carrier_id": str(carrier)},
                group,
                both_frame.loc[both_frame["carrier_id"].eq(carrier)],
                dominance_frame.loc[dominance_frame["carrier_id"].eq(carrier)],
            )
        )
    for year, group in listed_frame.groupby("year", sort=True):
        output["by_year"].append(
            summarize(
                {"year": int(year)},
                group,
                both_frame.loc[both_frame["year"].eq(year)],
                dominance_frame.loc[dominance_frame["year"].eq(year)],
            )
        )
    for (carrier, year), group in listed_frame.groupby(["carrier_id", "year"], sort=True):
        output["by_carrier_year"].append(
            summarize(
                {"carrier_id": str(carrier), "year": int(year)},
                group,
                both_frame.loc[both_frame["carrier_id"].eq(carrier) & both_frame["year"].eq(year)],
                dominance_frame.loc[
                    dominance_frame["carrier_id"].eq(carrier) & dominance_frame["year"].eq(year)
                ],
            )
        )
    return output


def evaluate_q_robustness(
    primary: pd.DataFrame,
    comparator: pd.DataFrame,
    *,
    block_length: int = 20,
    seed: int = 2026082300,
    replicates: int = 2000,
) -> dict[str, Any]:
    keys = ["forecast_session", "carrier_id", "horizon_sessions"]
    left = primary.add_prefix("primary_").rename(columns={f"primary_{key}": key for key in keys})
    right = comparator.add_prefix("comparator_").rename(
        columns={f"comparator_{key}": key for key in keys}
    )
    paired = left.merge(right, on=keys, how="inner")
    listed_h20 = paired.loc[
        paired["horizon_sessions"].eq(20) & paired["primary_q_horizon_status"].ne("NOT_LISTED")
    ].copy()
    primary_exact = listed_h20["primary_q_horizon_status"].eq("OK")
    comparator_exact = listed_h20["comparator_q_horizon_status"].eq("OK")
    both = listed_h20.loc[primary_exact & comparator_exact].copy()
    primary_count = int(primary_exact.sum())
    paired_count = len(both)
    paired_coverage = paired_count / primary_count if primary_count else 0.0
    both["signed_relative_delta"] = (
        pd.to_numeric(both["comparator_q_variance"]) - pd.to_numeric(both["primary_q_variance"])
    ) / pd.to_numeric(both["primary_q_variance"])
    signed = pd.to_numeric(both["signed_relative_delta"], errors="coerce").dropna()
    absolute = signed.abs()
    availability_agreement = (
        float((primary_exact == comparator_exact).mean()) if len(listed_h20) else 0.0
    )
    dominance = paired.loc[
        paired["horizon_sessions"].eq(20)
        & paired["primary_wing_dominance"].notna()
        & paired["comparator_wing_dominance"].notna()
    ].copy()
    dominance_agreement = (
        float(
            (dominance["primary_wing_dominance"] == dominance["comparator_wing_dominance"]).mean()
        )
        if len(dominance)
        else 0.0
    )
    ci_lower, ci_upper = _moving_date_block_median_ci(
        both,
        block_length=block_length,
        seed=seed,
        replicates=replicates,
    )
    metrics = {
        "primary_exact_h20_rows": primary_count,
        "paired_exact_h20_rows": paired_count,
        "paired_exact_coverage": paired_coverage,
        "median_signed_relative_q_variance_delta": float(signed.median()) if len(signed) else None,
        "median_absolute_relative_q_variance_delta": float(absolute.median())
        if len(absolute)
        else None,
        "p90_absolute_relative_q_variance_delta": float(absolute.quantile(0.90))
        if len(absolute)
        else None,
        "exact_bracket_availability_agreement": availability_agreement,
        "dominant_side_paired_rows": len(dominance),
        "dominant_side_agreement": dominance_agreement,
        "median_signed_relative_delta_block_ci90": [ci_lower, ci_upper],
        "bootstrap": {
            "kind": "MOVING_DATE_BLOCK",
            "replicates": replicates,
            "block_length_sessions": block_length,
            "confidence": 0.90,
            "seed": seed,
        },
    }
    insufficient = bool(
        paired_count < 126
        or len(dominance) < 126
        or paired_coverage < 0.70
        or ci_lower is None
        or ci_upper is None
    )
    if insufficient:
        verdict = "INSUFFICIENT_EVIDENCE"
        reason = "PAIRED_Q_ROBUSTNESS_COVERAGE_BELOW_FROZEN_GATE"
    else:
        assert ci_lower is not None
        assert ci_upper is not None
        passed = bool(
            absolute.median() <= 0.05
            and absolute.quantile(0.90) <= 0.15
            and availability_agreement >= 0.95
            and dominance_agreement >= 0.90
            and ci_lower >= -0.05
            and ci_upper <= 0.05
        )
        verdict = "PASS" if passed else "FAIL"
        reason = (
            "FROZEN_SETTLEMENT_Q_ROBUSTNESS_GATES_PASSED"
            if passed
            else "FROZEN_SETTLEMENT_Q_ROBUSTNESS_GATE_FAILED"
        )
    return {
        **metrics,
        "strata": _stratified_robustness(listed_h20, both, dominance),
        "verdict": verdict,
        "reason": reason,
    }


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
        "# MatSHIX V2.1.1 H3 settlement Q acceptance",
        "",
        f"- Authority: `{AUTHORITY_VERSION}`",
        f"- Q definition: `{Q_DEFINITION_VERSION}`",
        f"- Confirmation: `{summary['confirmation_range'][0]}` -> "
        f"`{summary['confirmation_range'][1]}`",
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
            "## Frozen settlement-vs-14:56 Confirmation gate",
            "",
            f"- verdict/reason: `{robustness['verdict']}` / `{robustness['reason']}`",
            f"- paired exact H20: `{robustness['paired_exact_h20_rows']}` / "
            f"`{robustness['primary_exact_h20_rows']}` = "
            f"`{robustness['paired_exact_coverage']:.2%}`",
            f"- median/p90 absolute relative Q variance delta: "
            f"`{robustness['median_absolute_relative_q_variance_delta']}` / "
            f"`{robustness['p90_absolute_relative_q_variance_delta']}`",
            f"- median signed relative delta: "
            f"`{robustness['median_signed_relative_q_variance_delta']}`",
            f"- 90% moving-date-block CI of median signed delta: "
            f"`{robustness['median_signed_relative_delta_block_ci90']}`",
            f"- exact availability agreement: "
            f"`{robustness['exact_bracket_availability_agreement']:.2%}`",
            f"- wing dominant-side agreement: `{robustness['dominant_side_agreement']:.2%}` "
            f"over `{robustness['dominant_side_paired_rows']}` rows",
            "",
            "Primary 为 provider-reconstructed EOD settlement；comparator 为 14:56 "
            "minute close。两者均不产生 bid/ask、tradable 或 formal PIT 声明。",
            "",
            "Q gate 非 PASS 时，Authority 要求停止，不得继续用 H4、P、Q−P、策略收益"
            "或另一个 proxy 给 Q 补洞。",
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
    authority_chain = verify_authority_chain(project)
    outcome_path = project / "data/processed/v2_1/realized_outcome_ledger.parquet"
    if not outcome_path.is_file():
        raise FileNotFoundError("V2.1 H2 outcome ledger must be built before H3 Q")
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
        progress("extracting provider-reconstructed settlement primary Q inputs")
    settlement = extract_settlement_history(paths, start=start, end=end)
    primary_rows, primary_surfaces = _surface_rows(
        settlement.option_prices,
        settlement.etf_marks,
        price_proxy="PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT",
        observation_time=settlement_observation_time,
        methodology_version="MATSHIX_RESEARCH_SETTLEMENT_SURFACE_2_1_1",
        progress=progress,
    )
    primary_q = _build_q_ledger(
        metadata,
        primary_rows,
        primary_surfaces,
        price_proxy="PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT",
        observation_time=settlement_observation_time,
        known_at=settlement_known_at,
        liquidity_status="EXCHANGE_SETTLEMENT_PROVIDER_RECONSTRUCTED",
    )
    if progress is not None:
        progress("extracting frozen 14:56 close comparator Q inputs")
    close = extract_history(paths, start=start, end=end)
    comparator_rows, comparator_surfaces = _surface_rows(
        close.option_prices,
        close.etf_marks,
        price_proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
        methodology_version="MATSHIX_RESEARCH_MINUTE_CLOSE_V2",
        progress=progress,
    )
    comparator_q = _build_q_ledger(
        metadata,
        comparator_rows,
        comparator_surfaces,
        price_proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
        known_at=surface_cutoff,
        liquidity_status="RECONSTRUCTED_ASOF_CLOSE_NO_BID_ASK",
    )
    confirmation_primary = primary_q.loc[
        pd.to_datetime(primary_q["forecast_session"]).between(CONFIRMATION_START, CONFIRMATION_END)
    ].copy()
    confirmation_comparator = comparator_q.loc[
        pd.to_datetime(comparator_q["forecast_session"]).between(
            CONFIRMATION_START, CONFIRMATION_END
        )
    ].copy()
    robustness = evaluate_q_robustness(confirmation_primary, confirmation_comparator)
    enriched = enrich_outcomes_with_q(outcomes, primary_q)
    processed = project / "data/processed/v2_1"
    output = project / "outputs/v2_1_q_acceptance"
    q_path = write_parquet(primary_q, processed / "q_weather_ledger.parquet")
    robust_path = write_parquet(comparator_q, processed / "q_robustness_ledger.parquet")
    enriched_path = write_parquet(enriched, processed / "realized_outcome_q_labeled_ledger.parquet")
    listed = primary_q["q_horizon_status"].ne("NOT_LISTED")
    coverage_rows: list[dict[str, Any]] = []
    for (carrier, horizon), group in primary_q.loc[listed].groupby(
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
        "authority_document": AUTHORITY_DOCUMENT,
        "authority_version": AUTHORITY_VERSION,
        "authority_sha256": AUTHORITY_SHA256,
        "parent_authority_sha256": PARENT_AUTHORITY_SHA256,
        "root_v2_authority_sha256": ROOT_V2_AUTHORITY_SHA256,
        "parent_adjudication_sha256": PARENT_ADJUDICATION_SHA256,
        "construction_plan_sha256": CONSTRUCTION_PLAN_SHA256,
        "authority_chain": authority_chain,
        "q_definition_version": Q_DEFINITION_VERSION,
        "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
        "repository": repository_provenance(project),
        "runtime": runtime_provenance(),
        "inputs": {
            "aetf_root": str(Path(aetf_root).expanduser().resolve()),
            "option_minute_glob": paths.option_minutes,
            "option_daily_glob": paths.option_daily,
            "option_contracts": str(paths.option_contracts),
            "option_contracts_sha256": file_hash(paths.option_contracts),
            "etf_minute_glob": paths.etf_minutes,
            "etf_daily_glob": paths.etf_daily,
            "aetf_readme": str(paths.readme),
            "aetf_readme_sha256": file_hash(paths.readme),
            "outcome_ledger": str(outcome_path.relative_to(project)),
            "outcome_ledger_sha256": file_hash(outcome_path),
        },
        "confirmation_range": [
            CONFIRMATION_START.date().isoformat(),
            CONFIRMATION_END.date().isoformat(),
        ],
        "q_gate": q_gate,
        "stop_required": q_gate != "PASS",
        "stop_reason": None if q_gate == "PASS" else robustness["reason"],
        "evidence_boundary": {
            "primary_price_proxy": "PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT",
            "robustness_price_proxy": "MINUTE_CLOSE_1456",
            "primary_observation_time": "15:00:00 Asia/Shanghai",
            "primary_known_at": "23:59:59 Asia/Shanghai",
            "formal_bid_ask_available": False,
            "future_outcome_values_used_for_q_construction": False,
            "future_outcome_values_used_for_q_proxy_selection": False,
            "strategy_inputs_used": False,
        },
        "exact_coverage": coverage_rows,
        "q_horizon_status_counts": {
            str(key): int(value)
            for key, value in primary_q["q_horizon_status"].value_counts().items()
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
