from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit


@dataclass(frozen=True)
class PlattResult:
    a: float
    b: float
    success: bool
    message: str


def binary_log_loss(labels: np.ndarray, probabilities: np.ndarray) -> float:
    y = np.asarray(labels, dtype=float)
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1.0 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def brier_score(labels: np.ndarray, probabilities: np.ndarray) -> float:
    return float(
        np.mean((np.asarray(probabilities, dtype=float) - np.asarray(labels, dtype=float)) ** 2)
    )


def fit_platt(scores: np.ndarray, labels: np.ndarray) -> PlattResult:
    z = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=float)
    if len(z) != len(y) or not len(z) or not np.isfinite(z).all() or not np.isfinite(y).all():
        return PlattResult(1.0, 0.0, False, "invalid input")

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        a, b = parameters
        logits = a * z + b
        probabilities = expit(logits)
        loss = float(np.mean(np.logaddexp(0.0, logits) - y * logits)) + 1e-6 * (a * a + b * b)
        gradient = np.asarray(
            [
                float(np.mean((probabilities - y) * z) + 2e-6 * a),
                float(np.mean(probabilities - y) + 2e-6 * b),
            ]
        )
        return loss, gradient

    result = minimize(
        lambda parameters: objective(parameters)[0],
        np.asarray([1.0, 0.0]),
        jac=lambda parameters: objective(parameters)[1],
        method="L-BFGS-B",
        bounds=[(0.0, None), (None, None)],
        options={"maxiter": 1000, "ftol": 1e-12, "gtol": 1e-8},
    )
    success = bool(result.success) and np.isfinite(result.x).all() and float(result.x[0]) >= 0
    return PlattResult(float(result.x[0]), float(result.x[1]), success, str(result.message))


def apply_platt(score: float, result: PlattResult) -> float:
    if not result.success:
        raise ValueError("Platt calibrator is not publishable")
    return float(np.clip(expit(result.a * score + result.b), 1e-6, 1.0 - 1e-6))


def exact_ece_252(labels: np.ndarray, probabilities: np.ndarray, dates: np.ndarray) -> float:
    if len(labels) != 252:
        raise ValueError("ECE contract requires exactly 252 rows")
    frame = pd.DataFrame(
        {
            "label": labels,
            "probability": probabilities,
            "date": pd.to_datetime(dates),
            "order": np.arange(252),
        }
    ).sort_values(["probability", "date", "order"], kind="stable")
    cursor = 0
    ece = 0.0
    for size in (51, 51, 50, 50, 50):
        group = frame.iloc[cursor : cursor + size]
        ece += size / 252.0 * abs(float(group["probability"].mean()) - float(group["label"].mean()))
        cursor += size
    return ece


def moving_block_skill_ci(
    labels: np.ndarray,
    model_probabilities: np.ndarray,
    base_probabilities: np.ndarray,
    *,
    block_length: int,
    seed: int,
    replicates: int = 5000,
) -> tuple[float, float]:
    y = np.asarray(labels, dtype=float)
    model = np.asarray(model_probabilities, dtype=float)
    base = np.asarray(base_probabilities, dtype=float)
    if len(y) != 252 or len(model) != 252 or len(base) != 252:
        raise ValueError("bootstrap contract requires 252 paired rows")
    starts = np.arange(0, 252 - block_length + 1)
    generator = np.random.default_rng(seed)
    skills = np.empty(replicates, dtype=float)
    for replicate in range(replicates):
        sampled: list[int] = []
        while len(sampled) < 252:
            start = int(generator.choice(starts))
            sampled.extend(range(start, start + block_length))
        index = np.asarray(sampled[:252], dtype=int)
        base_brier = brier_score(y[index], base[index])
        if base_brier == 0:
            raise ValueError("bootstrap base Brier is zero")
        skills[replicate] = 1.0 - brier_score(y[index], model[index]) / base_brier
    lower, upper = np.quantile(skills, [0.05, 0.95], method="linear")
    return float(lower), float(upper)
