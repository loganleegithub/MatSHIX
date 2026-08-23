from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from matshix.calendar import settlement_observation_time
from matshix.serialization import file_hash
from matshix.v2.settlement_audit import (
    PROTOCOL_SHA256,
    classify_audit,
    parity_diagnostic,
)


def _parity_frame(*, discount: float) -> pd.DataFrame:
    forward = 101.0
    rows: list[dict[str, object]] = []
    for position, strike in enumerate(range(80, 125, 5)):
        call = 5.0 + discount * max(forward - strike, 0.0)
        put = 5.0 + discount * max(strike - forward, 0.0)
        for option_type, price in (("C", call), ("P", put)):
            rows.append(
                {
                    "contract_id": f"{position}-{option_type}",
                    "strike": float(strike),
                    "option_type": option_type,
                    "price": price,
                    "contract_unit": 10000.0,
                    "is_standard": True,
                    "open_interest": 100.0,
                    "daily_volume": 10.0,
                }
            )
    return pd.DataFrame(rows)


def test_parity_diagnostic_preserves_frozen_discount_bounds() -> None:
    session = pd.Timestamp("2025-01-02")
    valid = parity_diagnostic(
        _parity_frame(discount=0.99),
        spot=100.0,
        observation_time=settlement_observation_time(session),
        expiry=pd.Timestamp("2025-02-26"),
    )
    invalid = parity_diagnostic(
        _parity_frame(discount=1.04),
        spot=100.0,
        observation_time=settlement_observation_time(session),
        expiry=pd.Timestamp("2025-02-26"),
    )
    assert valid["status"] == "OK"
    assert valid["raw_discount"] == pytest.approx(0.99)
    assert invalid["status"] == "PARITY_DISCOUNT_INVALID"
    assert invalid["raw_discount"] == pytest.approx(1.04)


def _classification_rows(*, standard_rescue_share: float) -> pd.DataFrame:
    rows = 130
    rescued = int(rows * standard_rescue_share)
    return pd.DataFrame(
        {
            "same_chain_present": True,
            "settlement_status": "PARITY_DISCOUNT_INVALID",
            "minute_status": "OK",
            "settlement_standard_only_rescue": [True] * rescued
            + [False] * (rows - rescued),
            "settlement_unit_mismatched_only_chain": False,
            "settlement_raw_discount": 1.03,
            "minute_raw_discount": 0.99,
        }
    )


def test_frozen_classification_distinguishes_data_from_method() -> None:
    method = classify_audit(_classification_rows(standard_rescue_share=0.0))
    data = classify_audit(_classification_rows(standard_rescue_share=0.60))
    assert method["verdict"] == "METHOD_MISMATCH"
    assert data["verdict"] == "DATA_FIELD_DEFECT"


def test_audit_protocol_bytes_are_frozen() -> None:
    project = Path(__file__).resolve().parents[1]
    actual = file_hash(project / "MATSHIX_V2_2_SETTLEMENT_AUDIT_PROTOCOL.md")
    assert actual == f"sha256:{PROTOCOL_SHA256}"


def test_audit_module_does_not_mutate_pricing_or_import_shortvol() -> None:
    project = Path(__file__).resolve().parents[1]
    source = (project / "src/matshix/v2/settlement_audit.py").read_text(encoding="utf-8")
    assert "matshix.research.shortvol" not in source
    assert "discount_bounds=" not in source
