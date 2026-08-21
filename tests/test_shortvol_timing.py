from __future__ import annotations

import pandas as pd
import pytest

from matshix.research.shortvol_timing import (
    build_market_stress_panel,
    build_timing_opportunity_panel,
    classify_timing_state,
    simulate_settlement_state_paths,
    summarize_timing_panel,
)


def test_timing_state_does_not_credit_missing_data_as_a_policy_block() -> None:
    complete = pd.Series(
        {
            "global_status": "OK",
            "local_status": "OK",
            "phase": "BALANCED_MARKET",
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.02,
            "dynamic_unit": 0.0,
        }
    )
    assert classify_timing_state(complete) == "KNOWN_BLOCK"
    allowed = complete.copy()
    allowed["dynamic_unit"] = 0.25
    partial = complete.copy()
    partial["global_status"] = "PARTIAL"
    unknown_compensation = complete.copy()
    unknown_compensation["insurance_compensation"] = "UNKNOWN"
    assert classify_timing_state(allowed) == "ALLOW"
    assert classify_timing_state(partial) == "ABSTAIN_DATA"
    assert classify_timing_state(unknown_compensation) == "ABSTAIN_DATA"


def test_opportunity_panel_uses_settlement_marks_and_defined_loss_normalization() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=15)
    calendar = pd.DataFrame(
        {
            "session_date": sessions,
            "signal_session_date": pd.Timestamp("2024-12-31"),
            "etf_mark": 4.0,
            "global_status": "OK",
            "local_status": "OK",
            "phase": "BALANCED_MARKET",
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.02,
            "dynamic_unit": 0.25,
            "raw_dynamic_unit": 0.25,
            "risk_reason": "PHASE_MAP",
        }
    )
    candidates = pd.DataFrame(
        [
            {
                "session_date": sessions[0],
                "expiry": pd.Timestamp("2025-01-24"),
                "short_put_code": "SP",
                "long_put_code": "LP",
                "short_call_code": "SC",
                "long_call_code": "LC",
                "short_put_strike": 3.9,
                "long_put_strike": 3.8,
                "short_call_strike": 4.1,
                "long_call_strike": 4.2,
            }
        ]
    )
    entry = {"SP": 0.03, "LP": 0.02, "SC": 0.03, "LC": 0.02}
    later = {"SP": 0.02, "LP": 0.015, "SC": 0.02, "LC": 0.015}
    marks = pd.DataFrame(
        [
            {
                "session_date": date,
                "code": code,
                "settle": (entry if date == sessions[0] else later)[code],
                "close": None,
            }
            for date in sessions
            for code in ("SP", "LP", "SC", "LC")
        ]
    )

    panel = build_timing_opportunity_panel(calendar, candidates, marks)

    assert set(panel["horizon"]) == {"H5", "H10", "TO_7DTE"}
    assert set(panel["state_category"]) == {"ALLOW"}
    assert panel["entry_credit"].iloc[0] == pytest.approx(200.0)
    assert panel["defined_max_loss"].iloc[0] == pytest.approx(800.0)
    assert panel["pnl_per_combo"].iloc[0] == pytest.approx(100.0)
    assert panel["return_on_max_loss"].iloc[0] == pytest.approx(0.125)
    assert panel["max_adverse_excursion"].iloc[0] == pytest.approx(0.0)


def test_summary_calls_out_inverse_selection_and_tail_miss() -> None:
    outcomes = [-0.50, -0.40, 0.10, 0.20, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    categories = ["ALLOW"] * 4 + ["KNOWN_BLOCK"] * 6
    base = pd.DataFrame(
        {
            "session_date": pd.bdate_range("2025-01-02", periods=10),
            "expiry": pd.to_datetime(
                ["2025-02-28"] * 2
                + ["2025-03-28"] * 2
                + ["2025-04-25"] * 2
                + ["2025-05-23"] * 2
                + ["2025-06-27"] * 2
            ),
            "exit_date": pd.bdate_range("2025-01-16", periods=10),
            "state_category": categories,
            "risk_unit": [0.25] * 4 + [0.0] * 6,
            "phase": ["BALANCED_MARKET"] * 10,
            "risk_reason": ["PHASE_MAP"] * 10,
            "return_on_max_loss": outcomes,
            "max_adverse_excursion": outcomes,
            "loss_side": ["CALL"] * 10,
            "put_side_pnl": [0.0] * 10,
            "call_side_pnl": outcomes,
        }
    )
    panel = pd.concat(
        [base.assign(horizon=horizon) for horizon in ("H5", "H10", "TO_7DTE")],
        ignore_index=True,
    )

    report = summarize_timing_panel(panel)
    primary = report["horizons"]["TO_7DTE"]

    assert report["conclusion"] == "IN_SAMPLE_TIMING_NOT_SUPPORTED"
    assert primary["allow_minus_block_mean"] == pytest.approx(-0.325)
    assert primary["tail"]["bad_opportunity_days"] == 1
    assert primary["tail"]["blocked_bad_opportunity_days"] == 0
    assert primary["tail"]["block_capture_rate"] == 0.0


def test_market_stress_panel_requires_the_previous_session_surface() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=25)
    calendar = pd.DataFrame(
        {
            "session_date": sessions,
            "etf_mark": [4.0 * (1.001**index) for index in range(len(sessions))],
            "global_status": "OK",
            "local_status": "OK",
            "phase": "BALANCED_MARKET",
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.02,
            "dynamic_unit": 0.25,
        }
    )
    expiry = pd.Timestamp("2025-02-07")
    contracts = pd.DataFrame(
        [
            {
                "call_put": kind,
                "list_date": pd.Timestamp("2024-12-01"),
                "maturity_date": expiry,
            }
            for kind in ("C", "P")
        ]
    )
    surface = {(sessions[0], expiry): 0.20}

    panel = build_market_stress_panel(calendar, contracts, surface)

    assert set(panel["horizon"]) == {"H5", "H10", "H20"}
    assert set(panel["session_date"]) == {sessions[1]}
    assert set(panel["lagged_atm_iv"]) == {0.20}


def test_settlement_state_path_isolates_a_known_block_exit_from_execution() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=15)
    units = [0.25, 0.25, 0.25] + [0.0] * 12
    calendar = pd.DataFrame(
        {
            "session_date": sessions,
            "etf_mark": 4.0,
            "global_status": "OK",
            "local_status": "OK",
            "phase": ["BALANCED_MARKET"] * 3 + ["BROAD_PRESSURE"] * 12,
            "insurance_compensation": "RICH",
            "vrp_ewma94": 0.02,
            "dynamic_unit": units,
        }
    )
    candidates = pd.DataFrame(
        [
            {
                "session_date": sessions[0],
                "expiry": pd.Timestamp("2025-01-24"),
                "short_put_code": "SP",
                "long_put_code": "LP",
                "short_call_code": "SC",
                "long_call_code": "LC",
                "short_put_strike": 3.9,
                "long_put_strike": 3.8,
                "short_call_strike": 4.1,
                "long_call_strike": 4.2,
            }
        ]
    )
    entry = {"SP": 0.03, "LP": 0.02, "SC": 0.03, "LC": 0.02}
    early_exit = {"SP": 0.02, "LP": 0.015, "SC": 0.02, "LC": 0.015}
    late_loss = {"SP": 0.05, "LP": 0.02, "SC": 0.04, "LC": 0.02}
    marks = pd.DataFrame(
        [
            {
                "session_date": date,
                "code": code,
                "settle": (entry if index == 0 else early_exit if index <= 3 else late_loss)[code],
                "close": None,
            }
            for index, date in enumerate(sessions)
            for code in ("SP", "LP", "SC", "LC")
        ]
    )

    ledger, runtime = simulate_settlement_state_paths(calendar, candidates, marks)
    static = ledger.loc[ledger["mode"].eq("STATIC_KNOWN_UNIVERSE")].iloc[0]
    known_exit = ledger.loc[ledger["mode"].eq("KNOWN_BLOCK_EXIT")].iloc[0]

    assert static["exit_reason"] == "DTE_7"
    assert static["pnl_per_combo"] == pytest.approx(-300.0)
    assert known_exit["exit_reason"] == "STATE_KNOWN_BLOCK"
    assert known_exit["pnl_per_combo"] == pytest.approx(100.0)
    assert runtime["KNOWN_BLOCK_EXIT"]["unfilled_state_exit_days"] == 0
