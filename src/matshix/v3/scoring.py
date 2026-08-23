from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from matshix.v3.authority import (
    BOOTSTRAP_BLOCK_LENGTH,
    BOOTSTRAP_REPETITIONS,
    CHALLENGER_FEATURES,
    FORBIDDEN_MODEL_FIELDS,
    HAR_FEATURES,
    P_BOOTSTRAP_SEED,
    QP_BOOTSTRAP_SEED,
)
from matshix.v3.outcomes import EXPECTED_INTRADAY_RETURNS


def qlike(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    ratio = actual / forecast
    return np.asarray(ratio - np.log(ratio) - 1.0, dtype=float)


def _all_finite(frame: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series:
    result = pd.Series(True, index=frame.index, dtype=bool)
    for field in fields:
        result &= pd.to_numeric(frame[field], errors="coerce").notna()
    return result


def _block_positions(
    length: int,
    *,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    selected: list[int] = []
    maximum_start = max(length - block_length, 0)
    while len(selected) < length:
        start = int(rng.integers(0, maximum_start + 1))
        width = min(block_length, length - len(selected), length - start)
        selected.extend(range(start, start + width))
    return np.asarray(selected, dtype=int)


def _bootstrap_skill_lower(
    paired: pd.DataFrame,
    *,
    forecast_field: str,
    baseline_fields: tuple[str, ...],
    seed: int,
) -> float | None:
    actual = pd.to_numeric(paired["rv_variance_h20"], errors="coerce").to_numpy(dtype=float)
    forecast = pd.to_numeric(paired[forecast_field], errors="coerce").to_numpy(dtype=float)
    baselines = [
        pd.to_numeric(paired[field], errors="coerce").to_numpy(dtype=float)
        for field in baseline_fields
    ]
    rng = np.random.default_rng(seed)
    samples: list[float] = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        positions = _block_positions(
            len(paired), block_length=BOOTSTRAP_BLOCK_LENGTH, rng=rng
        )
        candidate_loss = float(qlike(actual[positions], forecast[positions]).mean())
        baseline_loss = min(
            float(qlike(actual[positions], value[positions]).mean()) for value in baselines
        )
        if baseline_loss > 0:
            samples.append(1.0 - candidate_loss / baseline_loss)
    return float(np.quantile(samples, 0.05)) if samples else None


def _spearman(left: pd.Series, right: pd.Series) -> float | None:
    if len(left) < 3 or left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return None
    value = float(spearmanr(left.to_numpy(dtype=float), right.to_numpy(dtype=float)).statistic)
    return value if np.isfinite(value) else None


def evaluate_outcome_integrity(outcomes: pd.DataFrame) -> dict[str, Any]:
    observed = outcomes.loc[outcomes["outcome_status"].eq("OBSERVED")].copy()
    censored = outcomes.loc[outcomes["outcome_status"].eq("CENSORED")].copy()
    checks = {
        "single_carrier_h20": bool(
            outcomes["carrier_id"].nunique() == 1
            and set(outcomes["horizon_sessions"].astype(int)) == {20}
        ),
        "observed_positive": bool(
            len(observed) > 0
            and pd.to_numeric(observed["rv_variance_h20"], errors="coerce").gt(0).all()
        ),
        "observed_bar_counts_complete": bool(
            observed["valid_bar_count"].eq(20 * EXPECTED_INTRADAY_RETURNS).all()
        ),
        "censored_is_null": bool(
            pd.to_numeric(censored["rv_variance_h20"], errors="coerce").isna().all()
        ),
        "outcome_after_forecast": bool(
            pd.to_datetime(outcomes["target_start_session"])
            .gt(pd.to_datetime(outcomes["forecast_session"]))
            .all()
        ),
        "availability_after_target": bool(
            pd.to_datetime(outcomes["outcome_available_at"], utc=True)
            .gt(pd.to_datetime(outcomes["target_end_session"], utc=True))
            .all()
        ),
    }
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "reason": "OUTCOME_INTEGRITY_PASSED"
        if all(checks.values())
        else "OUTCOME_INTEGRITY_FAILED",
        "checks": checks,
        "rows": len(outcomes),
        "observed_rows": len(observed),
        "censored_rows": len(censored),
        "session_range": [
            pd.Timestamp(outcomes["forecast_session"].min()).date().isoformat(),
            pd.Timestamp(outcomes["forecast_session"].max()).date().isoformat(),
        ],
    }


def evaluate_engineering(
    frame: pd.DataFrame,
    *,
    strategy_modules_loaded: bool,
) -> dict[str, Any]:
    lower_columns = {str(value).lower() for value in frame.columns}
    strategy_columns = {
        "pnl",
        "nav",
        "position",
        "leg",
        "exit",
        "strategy_return",
    }
    p_with_missing_q = frame.loc[
        frame["p_publish_opportunity"].astype(bool) & frame["q_status"].ne("OK")
    ]
    checks = {
        "primary_features_exact": HAR_FEATURES
        == ("log_rv_d1_lag1", "log_mean_rv_d5_lag1", "log_mean_rv_d22_lag1"),
        "challenger_features_exact": CHALLENGER_FEATURES
        == (*HAR_FEATURES, "log_q_variance_h20"),
        "h4_absent_from_models": not bool(
            set(HAR_FEATURES + CHALLENGER_FEATURES).intersection(FORBIDDEN_MODEL_FIELDS)
        ),
        "strategy_columns_absent": not bool(lower_columns.intersection(strategy_columns)),
        "strategy_modules_not_loaded": not strategy_modules_loaded,
        "q_missing_does_not_block_p": "log_q_variance_h20" not in HAR_FEATURES,
        "single_local_carrier": bool(frame["carrier_id"].nunique() == 1),
    }
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "reason": "ENGINEERING_GATES_PASSED"
        if all(checks.values())
        else "ENGINEERING_GATE_FAILED",
        "checks": checks,
        "p_rows_published_with_missing_q": len(p_with_missing_q),
        "strategy_inputs_used": False,
    }


def evaluate_p_core(frame: pd.DataFrame) -> dict[str, Any]:
    opportunities = frame.loc[frame["p_evaluation_opportunity"].astype(bool)].copy()
    published = opportunities.loc[
        pd.to_numeric(opportunities["p_primary_variance_h20"], errors="coerce").notna()
    ].copy()
    point_coverage = len(published) / len(opportunities) if len(opportunities) else 0.0
    paired_fields = (
        "rv_variance_h20",
        "p_primary_variance_h20",
        "p_b0_climatology_variance_h20",
        "p_b1_ewma94_variance_h20",
    )
    paired = opportunities.loc[_all_finite(opportunities, paired_fields)].copy()
    interval_fields = (
        "rv_variance_h20",
        "p_interval_low_h20",
        "p_interval_high_h20",
    )
    interval = opportunities.loc[_all_finite(opportunities, interval_fields)].copy()
    extreme = paired.loc[paired["is_causal_extreme"].astype(bool)].copy()
    sample_insufficient = bool(len(paired) < 252 or len(interval) < 126 or len(extreme) < 20)
    base: dict[str, Any] = {
        "opportunity_rows": len(opportunities),
        "published_rows": len(published),
        "point_forecast_coverage": point_coverage,
        "paired_point_rows": len(paired),
        "paired_interval_rows": len(interval),
        "causal_extreme_rows": len(extreme),
    }
    if sample_insufficient:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "P_CORE_SAMPLE_GATE_NOT_MET",
            **base,
        }

    actual = pd.to_numeric(paired["rv_variance_h20"], errors="coerce").to_numpy(dtype=float)
    primary = pd.to_numeric(
        paired["p_primary_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    b0 = pd.to_numeric(
        paired["p_b0_climatology_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    b1 = pd.to_numeric(
        paired["p_b1_ewma94_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    losses = {
        "P_PRIMARY_HAR": float(qlike(actual, primary).mean()),
        "B0_ROLLING_CLIMATOLOGY": float(qlike(actual, b0).mean()),
        "B1_EWMA94": float(qlike(actual, b1).mean()),
    }
    best_baseline = min(
        ("B0_ROLLING_CLIMATOLOGY", "B1_EWMA94"), key=lambda key: losses[key]
    )
    skill = 1.0 - losses["P_PRIMARY_HAR"] / losses[best_baseline]
    bootstrap_lower = _bootstrap_skill_lower(
        paired,
        forecast_field="p_primary_variance_h20",
        baseline_fields=("p_b0_climatology_variance_h20", "p_b1_ewma94_variance_h20"),
        seed=P_BOOTSTRAP_SEED,
    )
    bias = abs(float((primary.mean() - actual.mean()) / actual.mean()))
    interval_actual = pd.to_numeric(
        interval["rv_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_low = pd.to_numeric(
        interval["p_interval_low_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_high = pd.to_numeric(
        interval["p_interval_high_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_coverage = float(
        ((interval_actual >= interval_low) & (interval_actual <= interval_high)).mean()
    )
    extreme_actual = pd.to_numeric(
        extreme["rv_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_primary = pd.to_numeric(
        extreme["p_primary_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_b0 = pd.to_numeric(
        extreme["p_b0_climatology_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_b1 = pd.to_numeric(
        extreme["p_b1_ewma94_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_losses = {
        "P_PRIMARY_HAR": float(qlike(extreme_actual, extreme_primary).mean()),
        "B0_ROLLING_CLIMATOLOGY": float(qlike(extreme_actual, extreme_b0).mean()),
        "B1_EWMA94": float(qlike(extreme_actual, extreme_b1).mean()),
    }
    finite_positive = bool(
        pd.to_numeric(published["p_primary_variance_h20"], errors="coerce").gt(0).all()
    )
    gates = {
        "paired_rows": len(paired) >= 252,
        "point_coverage": point_coverage >= 0.70,
        "qlike_skill": skill >= 0.02,
        "bootstrap_lower": bootstrap_lower is not None and bootstrap_lower > 0.0,
        "normalized_bias": bias <= 0.20,
        "finite_positive": finite_positive,
        "interval_rows": len(interval) >= 126,
        "interval_coverage": 0.65 <= interval_coverage <= 0.95,
        "extreme_rows": len(extreme) >= 20,
        "extreme_qlike": extreme_losses["P_PRIMARY_HAR"]
        <= min(extreme_losses["B0_ROLLING_CLIMATOLOGY"], extreme_losses["B1_EWMA94"]),
    }
    passed = all(gates.values())
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "P_CORE_H20_GATES_PASSED" if passed else "P_CORE_H20_GATE_FAILED",
        **base,
        "gates": gates,
        "best_baseline": best_baseline,
        "qlike": losses,
        "paired_qlike_skill": skill,
        "bootstrap_skill_lower_90": bootstrap_lower,
        "absolute_normalized_bias": bias,
        "interval_80_empirical_coverage": interval_coverage,
        "extreme_qlike": extreme_losses,
        "bootstrap": {
            "kind": "MOVING_DATE_BLOCK",
            "repetitions": BOOTSTRAP_REPETITIONS,
            "block_length_sessions": BOOTSTRAP_BLOCK_LENGTH,
            "confidence": 0.90,
            "seed": P_BOOTSTRAP_SEED,
        },
    }


def evaluate_challenger(frame: pd.DataFrame) -> dict[str, Any]:
    opportunities = frame.loc[
        frame["challenger_evaluation_opportunity"].astype(bool)
    ].copy()
    eligible = opportunities.loc[
        pd.to_numeric(opportunities["p_challenger_variance_h20"], errors="coerce").notna()
    ].copy()
    coverage = len(eligible) / len(opportunities) if len(opportunities) else 0.0
    paired_fields = (
        "rv_variance_h20",
        "p_primary_variance_h20",
        "p_challenger_variance_h20",
    )
    paired = opportunities.loc[_all_finite(opportunities, paired_fields)].copy()
    interval = opportunities.loc[
        _all_finite(
            opportunities,
            (
                "rv_variance_h20",
                "p_challenger_interval_low_h20",
                "p_challenger_interval_high_h20",
            ),
        )
    ].copy()
    extreme = paired.loc[paired["is_causal_extreme"].astype(bool)].copy()
    base = {
        "opportunity_rows": len(opportunities),
        "eligible_rows": len(eligible),
        "eligible_q_opportunity_coverage": coverage,
        "paired_rows": len(paired),
        "interval_rows": len(interval),
        "extreme_rows": len(extreme),
    }
    if len(paired) < 252 or len(interval) < 126 or len(extreme) < 20:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "research_status": "INSUFFICIENT_EVIDENCE",
            "reason": "CHALLENGER_SAMPLE_GATE_NOT_MET",
            **base,
        }
    actual = pd.to_numeric(paired["rv_variance_h20"], errors="coerce").to_numpy(dtype=float)
    primary = pd.to_numeric(
        paired["p_primary_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    challenger = pd.to_numeric(
        paired["p_challenger_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    primary_loss = float(qlike(actual, primary).mean())
    challenger_loss = float(qlike(actual, challenger).mean())
    skill = 1.0 - challenger_loss / primary_loss
    bootstrap_lower = _bootstrap_skill_lower(
        paired,
        forecast_field="p_challenger_variance_h20",
        baseline_fields=("p_primary_variance_h20",),
        seed=P_BOOTSTRAP_SEED,
    )
    bias = abs(float((challenger.mean() - actual.mean()) / actual.mean()))
    interval_actual = pd.to_numeric(
        interval["rv_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_low = pd.to_numeric(
        interval["p_challenger_interval_low_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_high = pd.to_numeric(
        interval["p_challenger_interval_high_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    interval_coverage = float(
        ((interval_actual >= interval_low) & (interval_actual <= interval_high)).mean()
    )
    extreme_actual = pd.to_numeric(
        extreme["rv_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_primary = pd.to_numeric(
        extreme["p_primary_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_challenger = pd.to_numeric(
        extreme["p_challenger_variance_h20"], errors="coerce"
    ).to_numpy(dtype=float)
    extreme_primary_loss = float(qlike(extreme_actual, extreme_primary).mean())
    extreme_challenger_loss = float(qlike(extreme_actual, extreme_challenger).mean())
    gates = {
        "paired_rows": len(paired) >= 252,
        "eligible_q_coverage": coverage >= 0.70,
        "qlike_skill": skill >= 0.02,
        "bootstrap_lower": bootstrap_lower is not None and bootstrap_lower > 0.0,
        "normalized_bias": bias <= 0.20,
        "interval_coverage": 0.65 <= interval_coverage <= 0.95,
        "extreme_qlike": extreme_challenger_loss <= extreme_primary_loss,
    }
    passed = all(gates.values())
    return {
        "verdict": "PASS" if passed else "FAIL",
        "research_status": "PROMOTION_CANDIDATE" if passed else "REJECTED_CHALLENGER",
        "reason": "CHALLENGER_GATES_PASSED" if passed else "CHALLENGER_GATE_FAILED",
        **base,
        "gates": gates,
        "qlike": {"P_PRIMARY_HAR": primary_loss, "P_HAR_Q_CHALLENGER": challenger_loss},
        "paired_qlike_skill": skill,
        "bootstrap_skill_lower_90": bootstrap_lower,
        "absolute_normalized_bias": bias,
        "interval_80_empirical_coverage": interval_coverage,
        "extreme_qlike": {
            "P_PRIMARY_HAR": extreme_primary_loss,
            "P_HAR_Q_CHALLENGER": extreme_challenger_loss,
        },
    }


def evaluate_qp_construction(frame: pd.DataFrame, *, p_core_passed: bool) -> dict[str, Any]:
    if not p_core_passed:
        return {
            "verdict": "NOT_APPLICABLE",
            "reason": "P_CORE_H20_NOT_PASS",
            "constructed_rows": 0,
        }
    observable = frame.loc[frame["qp_status"].ne("UNOBSERVABLE")].copy()
    observable = observable.loc[observable["qp_status"].ne("NOT_APPLICABLE")].copy()
    q_value = pd.to_numeric(observable["q_variance_h20"], errors="coerce")
    p_value = pd.to_numeric(observable["p_primary_variance_h20"], errors="coerce")
    p_low = pd.to_numeric(observable["p_interval_low_h20"], errors="coerce")
    p_high = pd.to_numeric(observable["p_interval_high_h20"], errors="coerce")
    gap = pd.to_numeric(observable["qp_variance_premium_h20"], errors="coerce")
    gap_low = pd.to_numeric(observable["qp_interval_low_h20"], errors="coerce")
    gap_high = pd.to_numeric(observable["qp_interval_high_h20"], errors="coerce")
    checks = {
        "constructed_rows_nonzero": len(observable) > 0,
        "same_horizon": bool(set(observable["horizon_sessions"].astype(int)) == {20})
        if len(observable)
        else False,
        "same_unit": bool(set(observable["unit"].astype(str)) == {"ANNUALIZED_VARIANCE"})
        if len(observable)
        else False,
        "point_identity": bool(((gap - (q_value - p_value)).abs() <= 1e-12).all()),
        "low_identity": bool(((gap_low - (q_value - p_high)).abs() <= 1e-12).all()),
        "high_identity": bool(((gap_high - (q_value - p_low)).abs() <= 1e-12).all()),
        "research_tier_only": bool(
            set(observable["qp_evidence_tier"].astype(str)) == {"RESEARCH_QP_ESTIMATE"}
        )
        if len(observable)
        else False,
    }
    passed = all(checks.values())
    return {
        "verdict": "PASS" if passed else "FAIL",
        "reason": "QP_CONSTRUCTION_INTEGRITY_PASSED"
        if passed
        else "QP_CONSTRUCTION_INTEGRITY_FAILED",
        "constructed_rows": len(observable),
        "checks": checks,
    }


def _bootstrap_qp(
    paired: pd.DataFrame,
    metric: Callable[[pd.DataFrame], float | None],
) -> float | None:
    rng = np.random.default_rng(QP_BOOTSTRAP_SEED)
    values: list[float] = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        positions = _block_positions(
            len(paired), block_length=BOOTSTRAP_BLOCK_LENGTH, rng=rng
        )
        value = metric(paired.iloc[positions])
        if value is not None and np.isfinite(value):
            values.append(value)
    return float(np.quantile(values, 0.05)) if values else None


def _qp_spearman(frame: pd.DataFrame) -> float | None:
    return _spearman(
        pd.to_numeric(frame["qp_variance_premium_h20"], errors="coerce"),
        pd.to_numeric(frame["ex_post_q_minus_realized_h20"], errors="coerce"),
    )


def _qp_top_bottom(frame: pd.DataFrame) -> float | None:
    percentile = pd.to_numeric(frame["qp_percentile_h20"], errors="coerce")
    ex_post = pd.to_numeric(frame["ex_post_q_minus_realized_h20"], errors="coerce")
    top = ex_post.loc[percentile >= 0.80]
    bottom = ex_post.loc[percentile <= 0.20]
    return float(top.mean() - bottom.mean()) if len(top) and len(bottom) else None


def evaluate_qp_direction(frame: pd.DataFrame, *, p_core_passed: bool) -> dict[str, Any]:
    if not p_core_passed:
        return {"verdict": "NOT_APPLICABLE", "reason": "P_CORE_H20_NOT_PASS"}
    paired = frame.loc[
        _all_finite(
            frame,
            (
                "qp_variance_premium_h20",
                "ex_post_q_minus_realized_h20",
                "qp_percentile_h20",
            ),
        )
    ].copy()
    p_opportunities = frame.loc[frame["p_evaluation_opportunity"].astype(bool)]
    q_available = p_opportunities["q_status"].eq("OK")
    q_coverage = float(q_available.mean()) if len(q_available) else 0.0
    if len(paired) < 126:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "research_status": "QP_DIRECTION_NOT_VALIDATED",
            "reason": "QP_DIRECTION_PAIRED_ROWS_BELOW_126",
            "paired_rows": len(paired),
            "q_availability_coverage": q_coverage,
        }
    correlation = _qp_spearman(paired)
    difference = _qp_top_bottom(paired)
    correlation_lower = _bootstrap_qp(paired, _qp_spearman)
    difference_lower = _bootstrap_qp(paired, _qp_top_bottom)
    sign_coverage = float(paired["qp_sign_confident_h20"].astype(bool).mean())
    bootstrap_pass = bool(
        (correlation_lower is not None and correlation_lower > 0)
        or (difference_lower is not None and difference_lower > 0)
    )
    passed = bool(
        correlation is not None
        and correlation > 0
        and difference is not None
        and difference > 0
        and bootstrap_pass
        and sign_coverage >= 0.30
    )
    return {
        "verdict": "PASS" if passed else "FAIL",
        "research_status": "QP_DIRECTION_VALIDATED"
        if passed
        else "QP_DIRECTION_NOT_VALIDATED",
        "reason": "QP_DIRECTION_GATES_PASSED" if passed else "QP_DIRECTION_GATE_FAILED",
        "paired_rows": len(paired),
        "spearman": correlation,
        "top_minus_bottom_quintile_mean": difference,
        "spearman_bootstrap_lower_90": correlation_lower,
        "top_minus_bottom_bootstrap_lower_90": difference_lower,
        "sign_confident_coverage": sign_coverage,
        "q_availability_coverage": q_coverage,
        "bootstrap": {
            "kind": "MOVING_DATE_BLOCK",
            "repetitions": BOOTSTRAP_REPETITIONS,
            "block_length_sessions": BOOTSTRAP_BLOCK_LENGTH,
            "confidence": 0.90,
            "seed": QP_BOOTSTRAP_SEED,
        },
    }
