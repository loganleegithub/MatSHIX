from __future__ import annotations

import pandas as pd

from matshix.data.formal import formal_unknown_snapshot, validate_formal_option_quotes


def _formal_rows() -> pd.DataFrame:
    session = "2026-06-05"
    carriers = ["SSE50_510050", "CSI300_510300", "CSI500_510500", "STAR50_588000"]
    return pd.DataFrame(
        [
            {
                "session_date": session,
                "carrier_id": carrier,
                "contract_id": f"contract-{number}",
                "option_type": "C",
                "strike": 3.0,
                "expiry": "2026-06-24",
                "bid": 0.10,
                "ask": 0.11,
                "event_time": "2026-06-05T14:56:57+08:00",
                "available_at": "2026-06-05T14:56:58+08:00",
                "vintage_kind": "AS_TRADED",
                "revision_id": "r1",
                "licence_scope": "NON_DISPLAY_VERIFIED",
            }
            for number, carrier in enumerate(carriers)
        ]
    )


def test_formal_boundary_requires_licence_and_two_sided_pit_quotes() -> None:
    rejected = validate_formal_option_quotes(
        _formal_rows(), session_date="2026-06-05", non_display_licence_verified=False
    )
    assert not rejected.accepted
    assert "NON_DISPLAY_LICENCE_NOT_VERIFIED" in rejected.issues
    accepted = validate_formal_option_quotes(
        _formal_rows(), session_date="2026-06-05", non_display_licence_verified=True
    )
    assert accepted.accepted
    assert accepted.accepted_rows == 4


def test_formal_unknown_is_not_calm_or_zero_probability() -> None:
    hash_value = "sha256:" + "0" * 64
    snapshot = formal_unknown_snapshot(
        session_date="2026-06-05",
        source_manifest_hash=hash_value,
        config_hash=hash_value,
        engine_artifact_hash=hash_value,
        blockers=["NO_QUOTES"],
    )
    assert snapshot["primary_phase"] == "UNKNOWN"
    assert snapshot["pressure_score"] is None
    assert all(value["probability"] is None for value in snapshot["probabilities"].values())
