from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matshix.v3.authority import CHALLENGER_FEATURES, FORBIDDEN_MODEL_FIELDS, HAR_FEATURES
from matshix.v3.models import add_physical_forecasts, add_qp_ledger_fields


def _model_frame(rows: int = 410, *, q_available: bool = False) -> pd.DataFrame:
    dates = pd.date_range("2020-01-02", periods=rows, freq="D")
    values = np.arange(rows, dtype=float)
    actual = 0.035 + 0.004 * np.sin(values / 17.0) + 0.00001 * values
    known = pd.DatetimeIndex(dates).tz_localize("Asia/Shanghai") + pd.Timedelta(
        hours=14, minutes=56, seconds=59
    )
    available = pd.DatetimeIndex(dates).tz_localize("Asia/Shanghai") + pd.Timedelta(
        days=1, hours=9
    )
    q_variance = 0.045 + 0.002 * np.cos(values / 13.0)
    return pd.DataFrame(
        {
            "forecast_session": dates,
            "known_at": known,
            "outcome_available_at": available,
            "rv_variance_h20": actual,
            "outcome_status": "OBSERVED",
            "log_rv_d1_lag1": -3.5 + 0.1 * np.sin(values / 11.0),
            "log_mean_rv_d5_lag1": -3.4 + 0.1 * np.cos(values / 19.0),
            "log_mean_rv_d22_lag1": -3.3 + 0.0003 * values,
            "p_b1_ewma94_variance_h20": 0.037 + 0.001 * np.sin(values / 23.0),
            "q_status": "OK" if q_available else "NO_EXACT_BRACKET",
            "q_variance_h20": q_variance if q_available else np.nan,
            "log_q_variance_h20": np.log(q_variance) if q_available else np.nan,
        }
    )


def test_p_primary_attends_when_q_and_h4_are_entirely_missing() -> None:
    frame = _model_frame(q_available=False)
    result = add_physical_forecasts(frame)
    row = result.iloc[300]
    assert row["p_publish_opportunity"]
    assert row["p_model_status"] == "RETROSPECTIVE_SCORE"
    assert row["p_primary_variance_h20"] > 0
    assert row["challenger_model_status"] == "UNOBSERVABLE_Q"
    assert not any(field in result.columns for field in FORBIDDEN_MODEL_FIELDS[:5])


def test_current_and_future_outcome_mutation_cannot_change_past_p_or_oof_interval() -> None:
    frame = _model_frame(q_available=False)
    first = add_physical_forecasts(frame)
    changed = frame.copy()
    changed.loc[390:, "rv_variance_h20"] = 9.0
    second = add_physical_forecasts(changed)
    fields = [
        "p_primary_variance_h20",
        "p_interval_low_h20",
        "p_interval_high_h20",
        "p_interval_status",
    ]
    assert first.loc[389, fields].to_dict() == second.loc[389, fields].to_dict()
    assert first.loc[389, "p_interval_status"] == "OOF_INTERVAL"


def test_frozen_models_and_deterministic_replay_are_exact() -> None:
    frame = _model_frame(q_available=True)
    first = add_physical_forecasts(frame)
    second = add_physical_forecasts(frame)
    pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert HAR_FEATURES == (
        "log_rv_d1_lag1",
        "log_mean_rv_d5_lag1",
        "log_mean_rv_d22_lag1",
    )
    assert CHALLENGER_FEATURES == (*HAR_FEATURES, "log_q_variance_h20")
    assert not set(CHALLENGER_FEATURES).intersection(FORBIDDEN_MODEL_FIELDS)


def test_qp_h20_point_and_interval_identities_are_exact() -> None:
    frame = pd.DataFrame(
        {
            "q_variance_h20": [0.05, np.nan],
            "p_primary_variance_h20": [0.03, 0.03],
            "p_interval_low_h20": [0.02, 0.02],
            "p_interval_high_h20": [0.04, 0.04],
            "rv_variance_h20": [0.035, 0.035],
        }
    )
    result = add_qp_ledger_fields(frame, p_core_passed=True)
    assert result.loc[0, "qp_variance_premium_h20"] == pytest.approx(0.02)
    assert result.loc[0, "qp_interval_low_h20"] == pytest.approx(0.01)
    assert result.loc[0, "qp_interval_high_h20"] == pytest.approx(0.03)
    assert result.loc[0, "ex_post_q_minus_realized_h20"] == pytest.approx(0.015)
    assert result.loc[0, "qp_status"] == "THICK_COMPENSATION"
    assert result.loc[1, "qp_status"] == "UNOBSERVABLE"


def test_v3_modules_do_not_import_strategy_runtime_and_cli_is_lazy() -> None:
    project = Path(__file__).resolve().parents[1]
    imported: set[str] = set()
    for source_path in (project / "src/matshix/v3").glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
    assert not any(value.startswith("matshix.research") for value in imported)
    command = (
        "import sys; import matshix.cli; "
        "assert 'matshix.research.shortvol' not in sys.modules; "
        "assert 'matshix.research.shortvol_timing' not in sys.modules"
    )
    subprocess.run(
        [sys.executable, "-c", command],
        cwd=project,
        check=True,
        env={**os.environ, "PYTHONPATH": str(project / "src")},
    )
