from __future__ import annotations

from typing import Any

import pandas as pd

from matshix.constants import CARRIER_TO_INDEX

AUTHORITY_VERSION = "2.0.0"
ERA_DEFINITION_VERSION = "2.0.0"
SAMPLING_GRID_VERSION = "ETF_5M_GRID_XSHG_2.0.0"
OUTCOME_DEFINITION_VERSION = "2.0.0"
Q_DEFINITION_VERSION = "2.0.0"
STATE_DEFINITION_VERSION = "2.0.0"
PHASE_DEFINITION_VERSION = "2.0.0"
CAPABILITY_DEFINITION_VERSION = "2.0.0"
TARGET_DEFINITION_VERSION = "2.0.0"
PREDICTOR_REGISTRY_VERSION = "2.0.0"
PHYSICAL_MODEL_VERSION = "2.0.0"
QP_DEFINITION_VERSION = "2.0.0"
PROBABILITY_DEFINITION_VERSION = "2.0.0"
ACCEPTANCE_DEFINITION_VERSION = "2.0.0"
FAILURE_LEDGER_VERSION = "2.0.0"
WEATHER_SNAPSHOT_SCHEMA_VERSION = "2.0.0"

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
