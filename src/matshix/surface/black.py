from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _d1(forward: float, strike: float, sigma: float, year_fraction: float) -> float:
    return (math.log(forward / strike) + 0.5 * sigma * sigma * year_fraction) / (
        sigma * math.sqrt(year_fraction)
    )


def black_price(
    *,
    option_type: str,
    forward: float,
    strike: float,
    sigma: float,
    year_fraction: float,
    discount_factor: float,
) -> float:
    if min(forward, strike, sigma, year_fraction, discount_factor) <= 0:
        raise ValueError("Black inputs must be positive")
    kind = option_type.upper()
    d1 = _d1(forward, strike, sigma, year_fraction)
    d2 = d1 - sigma * math.sqrt(year_fraction)
    if kind == "C":
        return float(discount_factor * (forward * norm.cdf(d1) - strike * norm.cdf(d2)))
    if kind == "P":
        return float(discount_factor * (strike * norm.cdf(-d2) - forward * norm.cdf(-d1)))
    raise ValueError("option_type must be C or P")


def forward_delta(
    *, option_type: str, forward: float, strike: float, sigma: float, year_fraction: float
) -> float:
    value = float(norm.cdf(_d1(forward, strike, sigma, year_fraction)))
    if option_type.upper() == "C":
        return value
    if option_type.upper() == "P":
        return value - 1.0
    raise ValueError("option_type must be C or P")


def price_bounds(
    *, option_type: str, forward: float, strike: float, discount_factor: float
) -> tuple[float, float]:
    if option_type.upper() == "C":
        return discount_factor * max(forward - strike, 0.0), discount_factor * forward
    if option_type.upper() == "P":
        return discount_factor * max(strike - forward, 0.0), discount_factor * strike
    raise ValueError("option_type must be C or P")


def implied_volatility(
    *,
    option_type: str,
    price: float,
    forward: float,
    strike: float,
    year_fraction: float,
    discount_factor: float,
    sigma_lower: float = 1e-4,
    sigma_upper: float = 5.0,
) -> float:
    lower, upper = price_bounds(
        option_type=option_type,
        forward=forward,
        strike=strike,
        discount_factor=discount_factor,
    )
    if not np.isfinite(price) or price < lower - 1e-12 or price >= upper - 1e-12:
        raise ValueError("INTRINSIC_BOUND_VIOLATION")

    def objective(sigma: float) -> float:
        return (
            black_price(
                option_type=option_type,
                forward=forward,
                strike=strike,
                sigma=sigma,
                year_fraction=year_fraction,
                discount_factor=discount_factor,
            )
            - price
        )

    low = objective(sigma_lower)
    high = objective(sigma_upper)
    if low == 0:
        return sigma_lower
    if high == 0:
        return sigma_upper
    if low * high > 0:
        raise ValueError("IV_ROOT_NOT_BRACKETED")
    return float(
        brentq(
            objective,
            sigma_lower,
            sigma_upper,
            xtol=1e-12,
            rtol=4.0 * np.finfo(float).eps,
            maxiter=200,
        )
    )
