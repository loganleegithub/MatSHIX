from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias

import numpy as np

Tri: TypeAlias = bool | None


def tri(value: object) -> Tri:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    raise TypeError(f"expected tri-state boolean, got {type(value).__name__}")


def tri_not(value: Tri) -> Tri:
    return None if value is None else not value


def tri_and(*values: Tri) -> Tri:
    normalized = [tri(value) for value in values]
    if any(value is False for value in normalized):
        return False
    if any(value is None for value in normalized):
        return None
    return True


def tri_or(*values: Tri) -> Tri:
    normalized = [tri(value) for value in values]
    if any(value is True for value in normalized):
        return True
    if any(value is None for value in normalized):
        return None
    return False


def at_least_k_true(values: Iterable[Tri], k: int) -> Tri:
    normalized = [tri(value) for value in values]
    if k < 0:
        raise ValueError("k must be non-negative")
    true_count = sum(value is True for value in normalized)
    unknown_count = sum(value is None for value in normalized)
    if true_count >= k:
        return True
    if true_count + unknown_count < k:
        return False
    return None


def exactly_one(values: Iterable[Tri]) -> Tri:
    normalized = list(values)
    at_least_one = at_least_k_true(normalized, 1)
    at_least_two = at_least_k_true(normalized, 2)
    if at_least_two is True:
        return False
    if at_least_two is None:
        return None
    return at_least_one


def count_if_all_known(values: Iterable[Tri]) -> int | None:
    normalized = [tri(value) for value in values]
    if any(value is None for value in normalized):
        return None
    return sum(value is True for value in normalized)
