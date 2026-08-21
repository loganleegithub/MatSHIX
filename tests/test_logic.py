from __future__ import annotations

import numpy as np
import pytest

from matshix.logic import at_least_k_true, exactly_one, tri, tri_and, tri_not, tri_or


def test_tri_state_short_circuit_truth_table() -> None:
    assert tri(np.bool_(True)) is True
    assert tri_not(None) is None
    assert tri_and(False, None) is False
    assert tri_and(True, None) is None
    assert tri_or(True, None) is True
    assert tri_or(False, None) is None
    assert at_least_k_true([True, None, False], 2) is None
    assert at_least_k_true([True, True, None], 2) is True
    assert exactly_one([True, False, False]) is True
    assert exactly_one([True, True, None]) is False
    assert exactly_one([False, False, None]) is None


def test_tri_rejects_numeric_truthiness() -> None:
    with pytest.raises(TypeError):
        tri(1)
