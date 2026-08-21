from __future__ import annotations

from pathlib import Path

import pytest

from matshix.constants import CARRIER_TO_INDEX
from matshix.data.aetf import AetfPaths, extract_history
from matshix.pipeline import build_surface_history

AETF_ROOT = Path("/Users/logan/OptiMatrix_DATA/AETF")


@pytest.mark.real_data
@pytest.mark.skipif(not AETF_ROOT.exists(), reason="local AETF corpus is unavailable")
def test_real_2026_06_05_four_carrier_surface() -> None:
    extraction = extract_history(
        AetfPaths.from_root(AETF_ROOT), start="2026-06-05", end="2026-06-05"
    )
    assert set(extraction.option_prices["carrier_id"]) == set(CARRIER_TO_INDEX)
    assert "OP588080.SH" not in set(extraction.option_prices["option_underlying_code"])
    surfaces, _ = build_surface_history(extraction)
    assert len(surfaces) == 4
    assert set(surfaces["surface_status"]) == {"VALID"}
    assert surfaces[["iv30_mf", "iv90_mf", "iv_25d_put30", "iv_25d_call30"]].notna().all().all()
