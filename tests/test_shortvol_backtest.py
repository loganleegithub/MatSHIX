from __future__ import annotations

import pandas as pd
import pytest

from matshix.research.shortvol import (
    confirm_risk_increases,
    option_fill_price,
    raw_dynamic_unit,
    select_condor_candidates,
)


def test_dynamic_gate_cashes_unknown_and_applies_pressure_caps() -> None:
    unknown = pd.Series(
        {
            "global_status": "PARTIAL",
            "phase": "CALM_POSITIVE_VRP",
            "local_status": "OK",
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.01,
        }
    )
    assert raw_dynamic_unit(unknown) == (0.0, "GLOBAL_NOT_OK")

    pressured = pd.Series(
        {
            "global_status": "OK",
            "phase": "CALM_POSITIVE_VRP",
            "local_status": "OK",
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.01,
            "pressure_score": 72.0,
            "direction": "STABLE",
            "index_pressure": 10.0,
            "shock": 10.0,
            "down_tail": 10.0,
            "persistence": 10.0,
            "hard_acute": False,
        }
    )
    unit, reason = raw_dynamic_unit(pressured)
    assert unit == 0.25
    assert "GLOBAL_PRESSURE_CAP" in reason


def test_increases_need_two_decision_days_but_decreases_are_immediate() -> None:
    raw = pd.Series([0.5, 0.5, 1.0, 1.0, 0.25, 0.75, 0.75, 0.0])
    assert confirm_risk_increases(raw).tolist() == [0.0, 0.5, 0.5, 1.0, 0.25, 0.25, 0.75, 0.0]


def test_fill_scenarios_are_adverse_to_order_side() -> None:
    sell = option_fill_price(
        side="SELL", scenario="VWAP_2TICK", vwap=0.1, low=0.09, high=0.11, tick=0.0001
    )
    buy = option_fill_price(
        side="BUY", scenario="VWAP_2TICK", vwap=0.1, low=0.09, high=0.11, tick=0.0001
    )
    assert sell == pytest.approx(0.0998)
    assert buy == pytest.approx(0.1002)
    assert option_fill_price(
        side="SELL", scenario="BAR_EXTREME", vwap=0.1, low=0.09, high=0.11, tick=0.0001
    ) == pytest.approx(0.09)
    assert option_fill_price(
        side="BUY", scenario="BAR_EXTREME", vwap=0.1, low=0.09, high=0.11, tick=0.0001
    ) == pytest.approx(0.11)


def test_condor_selection_uses_only_previous_session_surface() -> None:
    sessions = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "spot_0935": [4.0, 4.0],
        }
    )
    expiry = pd.Timestamp("2025-02-07")
    strikes = [3.4, 3.5, 3.6, 3.7, 3.8, 4.2, 4.3, 4.4, 4.5, 4.6]
    contracts = pd.DataFrame(
        [
            {
                "code": f"{kind}{strike}",
                "call_put": kind,
                "exercise_price": strike,
                "list_date": pd.Timestamp("2024-12-01"),
                "maturity_date": expiry,
                "min_price_chg": 0.0001,
            }
            for kind in ("P", "C")
            for strike in strikes
        ]
    )
    surface = {(pd.Timestamp("2025-01-02"), expiry): 0.30}

    selected, rejected = select_condor_candidates(sessions, contracts, surface)

    assert len(selected) == 1
    assert selected.iloc[0]["session_date"] == pd.Timestamp("2025-01-03")
    assert selected.iloc[0]["signal_session_date"] == pd.Timestamp("2025-01-02")
    assert abs(float(selected.iloc[0]["net_delta"])) <= 0.10
    assert (rejected["reason"] == "NO_LAGGED_SURFACE_OR_SPOT").sum() == 1
