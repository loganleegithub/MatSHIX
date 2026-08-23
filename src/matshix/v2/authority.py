from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from matshix.constants import CARRIER_TO_INDEX
from matshix.serialization import file_hash

AUTHORITY_VERSION = "2.1.1"
ERA_DEFINITION_VERSION = "2.0.0"
SAMPLING_GRID_VERSION = "ETF_5M_GRID_XSHG_2.0.0"
OUTCOME_DEFINITION_VERSION = "2.1.1"
Q_DEFINITION_VERSION = "2.1.1"
STATE_DEFINITION_VERSION = "2.1.1"
PHASE_DEFINITION_VERSION = "2.1.1"
CAPABILITY_DEFINITION_VERSION = "2.1.1"
TARGET_DEFINITION_VERSION = "2.1.1"
PREDICTOR_REGISTRY_VERSION = "2.1.1"
PHYSICAL_MODEL_VERSION = "2.1.1"
QP_DEFINITION_VERSION = "2.1.1"
PROBABILITY_DEFINITION_VERSION = "2.1.1"
ACCEPTANCE_DEFINITION_VERSION = "2.1.1"
FAILURE_LEDGER_VERSION = "2.1.1"
WEATHER_SNAPSHOT_SCHEMA_VERSION = "2.1.1"

AUTHORITY_DOCUMENT = "MATSHIX_V2_1_1_AUTHORITY.md"
AUTHORITY_SHA256 = "03c06e4c861bd313d0502ecbc25ee1e18511c7a080b8bc2fa1fb3eaf451c0705"
CONSTRUCTION_PLAN_SHA256 = "785008372be80ff9375aea592ee96532397d67f91b0f633390683ff5056d848f"
PARENT_AUTHORITY_SHA256 = "d41dd08b93548ce6c3ab6f2e5bda503a5e11b0d022814fbbcdffec27bbd13557"
ROOT_V2_AUTHORITY_SHA256 = "18309ed4e71c8e8074ea3abc5645f25e465b612b300ad3b80ed9379776dad152"
PARENT_ADJUDICATION_SHA256 = "eb0a0b90db9d3e3213c620568bc472ba2bbe62cb0a36fba78f042ec9e0315ebc"
DESIGN_AUDIT_SHA256 = "4adffd096aa937196c97b905a8f3c3f088d32b026ea5763677e5a147d39ca579"

DEVELOPMENT_START = pd.Timestamp("2023-01-03")
DEVELOPMENT_END = pd.Timestamp("2024-12-31")
CONFIRMATION_START = pd.Timestamp("2025-01-02")
CONFIRMATION_END = pd.Timestamp("2026-06-05")

HORIZONS = (5, 10, 20)

ERA_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "coverage_regime": "ERA_A_50_ONLY",
        "start_session": "2015-02-09",
        "end_session": "2019-12-22",
        "available_carriers": ("SSE50_510050",),
        "available_carrier_count": 1,
        "market_breadth_allowed": False,
    },
    {
        "coverage_regime": "ERA_B_50_300",
        "start_session": "2019-12-23",
        "end_session": "2022-09-18",
        "available_carriers": ("SSE50_510050", "CSI300_510300"),
        "available_carrier_count": 2,
        "market_breadth_allowed": False,
    },
    {
        "coverage_regime": "ERA_C_50_300_500",
        "start_session": "2022-09-19",
        "end_session": "2023-06-04",
        "available_carriers": (
            "SSE50_510050",
            "CSI300_510300",
            "CSI500_510500",
        ),
        "available_carrier_count": 3,
        "market_breadth_allowed": False,
    },
    {
        "coverage_regime": "ERA_D_FOUR_CARRIERS",
        "start_session": "2023-06-05",
        "end_session": None,
        "available_carriers": tuple(CARRIER_TO_INDEX),
        "available_carrier_count": 4,
        "market_breadth_allowed": True,
    },
)

EXPECTED_LISTING_DATES = {
    "SSE50_510050": pd.Timestamp("2015-02-09"),
    "CSI300_510300": pd.Timestamp("2019-12-23"),
    "CSI500_510500": pd.Timestamp("2022-09-19"),
    "STAR50_588000": pd.Timestamp("2023-06-05"),
}


def verify_authority_chain(project: Path) -> dict[str, dict[str, str]]:
    expected = {
        AUTHORITY_DOCUMENT: AUTHORITY_SHA256,
        "MATSHIX_V2_1_AUTHORITY.md": PARENT_AUTHORITY_SHA256,
        "MATSHIX_V2_AUTHORITY.md": ROOT_V2_AUTHORITY_SHA256,
        "MATSHIX_V2_ADJUDICATION.md": PARENT_ADJUDICATION_SHA256,
        "MATSHIX_V2_1_DESIGN_AUDIT.md": DESIGN_AUDIT_SHA256,
        "MATSHIX_V2_CONSTRUCTION_PLAN.md": CONSTRUCTION_PLAN_SHA256,
    }
    verified: dict[str, dict[str, str]] = {}
    for relative, expected_digest in expected.items():
        path = project / relative
        actual_digest = file_hash(path).removeprefix("sha256:")
        if actual_digest != expected_digest:
            raise ValueError(
                f"frozen Authority chain mismatch for {relative}: "
                f"expected {expected_digest}, got {actual_digest}"
            )
        verified[relative] = {"sha256": actual_digest, "status": "VERIFIED"}
    return verified


def era_for_session(session: str | pd.Timestamp) -> dict[str, Any]:
    value = pd.Timestamp(session).normalize()
    for era in ERA_REGISTRY:
        start = pd.Timestamp(str(era["start_session"]))
        end_value = era["end_session"]
        if value >= start and (end_value is None or value <= pd.Timestamp(str(end_value))):
            return era
    raise ValueError(f"session predates MatSHIX V2 Authority: {value.date()}")


def coverage_regime(session: str | pd.Timestamp) -> str:
    return str(era_for_session(session)["coverage_regime"])


def available_carrier_count(session: str | pd.Timestamp) -> int:
    return int(era_for_session(session)["available_carrier_count"])


def carrier_is_listed(carrier_id: str, session: str | pd.Timestamp) -> bool:
    return bool(pd.Timestamp(session).normalize() >= EXPECTED_LISTING_DATES[carrier_id])
