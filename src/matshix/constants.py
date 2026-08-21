from __future__ import annotations

from typing import Final

EVIDENCE_TIER_RESEARCH: Final = "RESEARCH_ONLY"
EVIDENCE_TIER_FORMAL: Final = "FORMAL_PIT"

CARRIER_TO_INDEX: Final[dict[str, str]] = {
    "SSE50_510050": "SSE50",
    "CSI300_510300": "CSI300",
    "CSI500_510500": "CSI500",
    "STAR50_588000": "STAR50",
}
INDEX_TO_CARRIER: Final[dict[str, str]] = {value: key for key, value in CARRIER_TO_INDEX.items()}
CARRIER_TO_UNDERLYING: Final[dict[str, str]] = {
    "SSE50_510050": "510050.SH",
    "CSI300_510300": "510300.SH",
    "CSI500_510500": "510500.SH",
    "STAR50_588000": "588000.SH",
}
CARRIER_TO_OPTION_CODE: Final[dict[str, str]] = {
    "SSE50_510050": "OP510050.SH",
    "CSI300_510300": "OP510300.SH",
    "CSI500_510500": "OP510500.SH",
    "STAR50_588000": "OP588000.SH",
}
EXCLUDED_OPTION_CODES: Final[frozenset[str]] = frozenset({"OP588080.SH"})
EXCLUDED_CARRIERS: Final[frozenset[str]] = frozenset({"STAR50_588080"})

ECONOMIC_WEIGHTS: Final[dict[str, float]] = {
    "SSE50": 0.20,
    "CSI300": 0.20,
    "CSI500": 0.30,
    "STAR50": 0.30,
}
INDEX_ORDER: Final[tuple[str, ...]] = tuple(ECONOMIC_WEIGHTS)
SEGMENT_ORDER: Final[tuple[str, ...]] = ("large", "mid", "tech")

EVENT_IDS: Final[tuple[str, ...]] = (
    "cross_market_iv_jump_1d",
    "broad_pressure_onset_5d",
    "systemic_acute_stress_5d",
    "persistent_cross_market_stress_20d",
    "fast_repair_5d",
)
EVENT_HORIZONS: Final[dict[str, int]] = {
    "cross_market_iv_jump_1d": 1,
    "broad_pressure_onset_5d": 5,
    "systemic_acute_stress_5d": 5,
    "persistent_cross_market_stress_20d": 20,
    "fast_repair_5d": 5,
}
EVENT_SEEDS: Final[dict[str, int]] = {event: 1101 + index for index, event in enumerate(EVENT_IDS)}

ACUTE_PHASES: Final[frozenset[str]] = frozenset({"SYSTEMIC_ACUTE_STRESS", "LOCALIZED_ACUTE_STRESS"})
IMMEDIATE_PHASES: Final[frozenset[str]] = frozenset(
    {
        "SYSTEMIC_ACUTE_STRESS",
        "LOCALIZED_ACUTE_STRESS",
        "REPAIR_IN_PROGRESS",
        "BROAD_PERSISTENT_PRESSURE",
    }
)
