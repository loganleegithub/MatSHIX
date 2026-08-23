from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pandas as pd

from matshix.calendar import add_exchange_sessions, exchange_sessions_in_range
from matshix.data.aetf import AetfPaths, extract_history, extraction_metadata
from matshix.serialization import file_hash, write_json
from matshix.storage import write_parquet
from matshix.v3.authority import (
    AUTHORITY_DOCUMENT,
    AUTHORITY_SHA256,
    AUTHORITY_VERSION,
    BASELINE_MANIFEST,
    CARRIER_ID,
    CONSTRUCTION_PLAN,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    verify_frozen_contract,
)
from matshix.v3.models import (
    add_physical_forecasts,
    add_qp_ledger_fields,
    build_model_frame,
    project_qp_ledger,
)
from matshix.v3.outcomes import (
    build_daily_realized_inputs,
    build_outcome_ledger,
    extract_etf_minutes,
)
from matshix.v3.q_weather import build_q_ledger, build_q_surfaces, evaluate_q_integrity
from matshix.v3.scoring import (
    evaluate_challenger,
    evaluate_engineering,
    evaluate_outcome_integrity,
    evaluate_p_core,
    evaluate_qp_construction,
    evaluate_qp_direction,
)

Progress = Callable[[str], None]


@dataclass(frozen=True)
class V3BuildArtifacts:
    outcome_ledger_path: Path
    p_ledger_path: Path
    q_ledger_path: Path
    qp_ledger_path: Path
    score_path: Path
    output_failure_path: Path
    failure_path: Path
    adjudication_path: Path
    score: dict[str, Any]


def _git(project: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository_provenance(project: Path) -> dict[str, Any]:
    return {
        "project_dir": str(project),
        "git_sha": _git(project, "rev-parse", "HEAD"),
        "git_branch": _git(project, "branch", "--show-current"),
        "worktree_clean_at_start": not bool(_git(project, "status", "--porcelain")),
        "main_sha": _git(project, "rev-parse", "main"),
        "tracking_main_sha": _git(project, "rev-parse", "origin/main"),
    }


def _runtime_provenance() -> dict[str, Any]:
    packages = (
        "duckdb",
        "exchange-calendars",
        "numpy",
        "pandas",
        "pyarrow",
        "scikit-learn",
        "scipy",
    )
    dependencies: dict[str, str | None] = {}
    for package in packages:
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable": str(Path(sys.executable).resolve()),
        "dependencies": dependencies,
    }


def _strategy_modules_loaded() -> bool:
    forbidden = (
        "matshix.research.shortvol",
        "matshix.research.shortvol_timing",
    )
    return any(name in sys.modules for name in forbidden)


def _score_frames(
    outcomes: pd.DataFrame,
    q: pd.DataFrame,
    p_frame: pd.DataFrame,
    *,
    strategy_modules_loaded: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    engineering = evaluate_engineering(
        p_frame,
        strategy_modules_loaded=strategy_modules_loaded,
    )
    outcome = evaluate_outcome_integrity(outcomes)
    p_core = evaluate_p_core(p_frame)
    q_integrity = evaluate_q_integrity(q)
    challenger = evaluate_challenger(p_frame)
    p_passed = p_core["verdict"] == "PASS"
    with_qp = add_qp_ledger_fields(p_frame, p_core_passed=p_passed)
    qp_construction = evaluate_qp_construction(with_qp, p_core_passed=p_passed)
    qp_direction = evaluate_qp_direction(with_qp, p_core_passed=p_passed)
    dimensions = {
        "ENGINEERING": engineering,
        "OUTCOME_INTEGRITY": outcome,
        "P_CORE_H20": p_core,
        "Q_RESEARCH_INTEGRITY": q_integrity,
        "P_HAR_Q_CHALLENGER": challenger,
        "QP_CONSTRUCTION_INTEGRITY": qp_construction,
        "QP_DIRECTION_RESEARCH": qp_direction,
        "FORWARD_Q": {"verdict": "NOT_APPLICABLE", "reason": "HISTORICAL_BUILD_ONLY"},
        "FORWARD_P": {"verdict": "NOT_APPLICABLE", "reason": "HISTORICAL_BUILD_ONLY"},
    }
    build_valid = engineering["verdict"] == "PASS" and outcome["verdict"] == "PASS"
    core_accepted = bool(
        build_valid
        and p_core["verdict"] == "PASS"
        and q_integrity["verdict"] == "PASS"
        and qp_construction["verdict"] == "PASS"
    )
    if core_accepted:
        top_level = "V3_RESEARCH_CORE_ACCEPTED"
    elif build_valid:
        top_level = "V3_NOT_READY"
    else:
        top_level = "V3_NOT_READY"
    score = {
        "authority_version": AUTHORITY_VERSION,
        "authority_document": AUTHORITY_DOCUMENT,
        "authority_sha256": AUTHORITY_SHA256,
        "carrier_scope": CARRIER_ID,
        "development_era": {
            "start_session": DEVELOPMENT_START.date().isoformat(),
            "end_session": DEVELOPMENT_END.date().isoformat(),
            "evidence_kind": "RETROSPECTIVE_DEVELOPMENT",
            "evidence_tier": "RESEARCH_ONLY",
        },
        "top_level_status": top_level,
        "v3_build_valid": build_valid,
        "v3_research_core_accepted": core_accepted,
        "dimensions": dimensions,
        "strategy_inputs_used": False,
        "formal_pit_claimed": False,
        "candidate_frozen": False,
        "forward_acceptance_executed": False,
    }
    return with_qp, score


def _failure_ledger(score: dict[str, Any], artifact_hashes: dict[str, str]) -> dict[str, Any]:
    dimensions = score["dimensions"]
    non_pass = [
        {
            "dimension": dimension,
            "verdict": result["verdict"],
            "reason": result["reason"],
            "required_core": dimension
            in {
                "ENGINEERING",
                "OUTCOME_INTEGRITY",
                "P_CORE_H20",
                "Q_RESEARCH_INTEGRITY",
                "QP_CONSTRUCTION_INTEGRITY",
            },
        }
        for dimension, result in dimensions.items()
        if result["verdict"] != "PASS"
    ]
    stop_dimension = next(
        (
            item["dimension"]
            for item in non_pass
            if item["required_core"] and item["verdict"] in {"FAIL", "INSUFFICIENT_EVIDENCE"}
        ),
        None,
    )
    return {
        "failure_ledger_version": AUTHORITY_VERSION,
        "authority_sha256": AUTHORITY_SHA256,
        "implementation_git_sha": score["repository"]["git_sha"],
        "carrier_scope": CARRIER_ID,
        "development_era": score["development_era"],
        "top_level_status": score["top_level_status"],
        "stop_dimension": stop_dimension,
        "non_pass_dimensions": non_pass,
        "artifact_hashes": artifact_hashes,
        "deterministic_replay": True,
        "strategy_inputs_used": False,
        "formal_pit_claimed": False,
        "candidate_frozen": False,
    }


def _render_adjudication(
    score: dict[str, Any],
    *,
    artifact_hashes: dict[str, str],
    score_hash: str,
    failure_hash: str,
) -> str:
    lines = [
        "# MatSHIX V3 回顾性开发裁决",
        "",
        f"- 顶层状态：`{score['top_level_status']}`",
        f"- Authority：`{AUTHORITY_DOCUMENT}` / `{AUTHORITY_SHA256}`",
        f"- 实现提交：`{score['repository']['git_sha']}`",
        f"- 分支：`{score['repository']['git_branch']}`",
        f"- 冻结 era：`{DEVELOPMENT_START.date()}` -> `{DEVELOPMENT_END.date()}`",
        "- 证据层：`RETROSPECTIVE_DEVELOPMENT / RESEARCH_ONLY`",
        f"- 首次完整构建开始：`{score['execution']['started_at_utc']}`",
        f"- 首次完整构建结束：`{score['execution']['ended_at_utc']}`",
        f"- 命令：`{score['execution']['command']}`",
        f"- 开始时工作树干净：`{str(score['repository']['worktree_clean_at_start']).lower()}`",
        "- deterministic replay：`true`",
        "- strategy inputs used：`false`",
        "- formal PIT claimed：`false`",
        "",
        "## 独立接受矩阵",
        "",
        "| Dimension | Verdict | Reason |",
        "|---|---|---|",
    ]
    for dimension, result in score["dimensions"].items():
        lines.append(f"| `{dimension}` | `{result['verdict']}` | `{result['reason']}` |")
    lines.extend(
        [
            "",
            "## 核心停止裁决",
            "",
        ]
    )
    if score["v3_research_core_accepted"]:
        lines.append(
            "所有回顾性核心门通过；本结果仍不是正式前向通过或交易授权。候选冻结须另按合同生成。"
        )
    else:
        failures = [
            (dimension, result)
            for dimension, result in score["dimensions"].items()
            if dimension
            in {
                "ENGINEERING",
                "OUTCOME_INTEGRITY",
                "P_CORE_H20",
                "Q_RESEARCH_INTEGRITY",
                "QP_CONSTRUCTION_INTEGRITY",
            }
            and result["verdict"] != "PASS"
        ]
        for dimension, result in failures:
            lines.append(
                f"- 停在 `{dimension}`：`{result['verdict']}` / `{result['reason']}`。"
            )
        lines.append("- 不生成候选冻结，不执行前向接受，不用策略收益、删样本或降门补洞。")
    lines.extend(["", "## 产物与 hash", ""])
    for relative, digest in artifact_hashes.items():
        lines.extend([f"- `{relative}`", f"  `{digest}`"])
    lines.extend(
        [
            "- `outputs/v3/development_score.json`",
            f"  `{score_hash}`",
            "- `MATSHIX_V3_FAILURE_LEDGER.json`",
            f"  `{failure_hash}`",
            "",
            "## 边界",
            "",
            "Q 历史输入仅为 AETF 14:56 minute close，不是 bid/ask 或可成交 mid。Q−P 即使可构造，",
            "也只是同期限方差补偿事实，不是卖方许可、错误定价或具体结构的预期收益。",
            "",
        ]
    )
    return "\n".join(lines)


def _assert_clean_execution_branch(project: Path, provenance: dict[str, Any]) -> None:
    if provenance["git_branch"] != "codex/matshix-weather-v3":
        raise ValueError(f"unexpected V3 execution branch: {provenance['git_branch']}")
    if not provenance["worktree_clean_at_start"]:
        raise ValueError("V3 first historical build requires a clean worktree")
    if provenance["main_sha"] != provenance["tracking_main_sha"]:
        raise ValueError("local main and tracking main differ before V3 execution")


def run_v3_research_build(
    *,
    project_dir: Path,
    aetf_root: Path,
    progress: Progress | None = None,
) -> V3BuildArtifacts:
    project = project_dir.expanduser().resolve()
    started = datetime.now(UTC)
    provenance = _repository_provenance(project)
    _assert_clean_execution_branch(project, provenance)
    contract = verify_frozen_contract(project)
    strategy_loaded = _strategy_modules_loaded()
    if strategy_loaded:
        raise ValueError("V3 process loaded a forbidden ShortVol strategy module")

    paths = AetfPaths.from_root(aetf_root)
    extraction = extract_history(
        paths,
        start=DEVELOPMENT_START.date().isoformat(),
        end=DEVELOPMENT_END.date().isoformat(),
    )
    minute_start = add_exchange_sessions(DEVELOPMENT_START, -23)
    minutes = extract_etf_minutes(paths, start=minute_start, end=DEVELOPMENT_END)
    forecast_sessions = exchange_sessions_in_range(DEVELOPMENT_START, DEVELOPMENT_END)

    if progress is not None:
        progress("building V3 outcome replay A")
    daily_a, path_marks_a = build_daily_realized_inputs(minutes)
    outcomes_a = build_outcome_ledger(
        daily_a,
        path_marks_a,
        forecast_sessions=forecast_sessions,
    )
    if progress is not None:
        progress("building V3 exact-H20 Q replay A")
    surfaces_a = build_q_surfaces(
        extraction.option_prices,
        extraction.etf_marks,
        progress=progress,
    )
    q_a = build_q_ledger(outcomes_a, surfaces_a)
    p_a = add_physical_forecasts(build_model_frame(daily_a, outcomes_a, q_a))
    with_qp_a, score_a = _score_frames(
        outcomes_a,
        q_a,
        p_a,
        strategy_modules_loaded=strategy_loaded,
    )

    if progress is not None:
        progress("building independent deterministic replay B")
    daily_b, path_marks_b = build_daily_realized_inputs(minutes)
    outcomes_b = build_outcome_ledger(
        daily_b,
        path_marks_b,
        forecast_sessions=forecast_sessions,
    )
    surfaces_b = build_q_surfaces(extraction.option_prices, extraction.etf_marks)
    q_b = build_q_ledger(outcomes_b, surfaces_b)
    p_b = add_physical_forecasts(build_model_frame(daily_b, outcomes_b, q_b))
    with_qp_b, score_b = _score_frames(
        outcomes_b,
        q_b,
        p_b,
        strategy_modules_loaded=strategy_loaded,
    )
    pd.testing.assert_frame_equal(daily_a, daily_b, check_exact=True)
    pd.testing.assert_frame_equal(outcomes_a, outcomes_b, check_exact=True)
    pd.testing.assert_frame_equal(q_a, q_b, check_exact=True)
    pd.testing.assert_frame_equal(with_qp_a, with_qp_b, check_exact=True)
    if score_a != score_b:
        raise AssertionError("V3 development score deterministic replay mismatch")

    processed = project / "data/processed/v3"
    output = project / "outputs/v3"
    outcome_path = write_parquet(outcomes_a, processed / "csi300_outcome_ledger.parquet")
    p_path = write_parquet(with_qp_a, processed / "csi300_p_ledger.parquet")
    q_path = write_parquet(q_a, processed / "csi300_q_ledger.parquet")
    qp_path = write_parquet(project_qp_ledger(with_qp_a), processed / "csi300_qp_ledger.parquet")
    artifact_hashes = {
        str(path.relative_to(project)): file_hash(path).removeprefix("sha256:")
        for path in (outcome_path, p_path, q_path, qp_path)
    }
    ended = datetime.now(UTC)
    command = (
        "python -m matshix build-v3-research --project-dir . "
        "--aetf-root /Users/logan/OptiMatrix_DATA/AETF"
    )
    score = {
        **score_a,
        "contract": contract,
        "construction_plan": CONSTRUCTION_PLAN,
        "baseline_manifest": BASELINE_MANIFEST,
        "baseline_manifest_sha256": file_hash(project / BASELINE_MANIFEST),
        "repository": provenance,
        "runtime": _runtime_provenance(),
        "inputs": {
            "aetf_root": str(paths.root),
            "aetf_extraction": extraction_metadata(extraction),
            "option_contracts_sha256": file_hash(paths.option_contracts),
            "aetf_readme_sha256": file_hash(paths.readme),
            "option_minute_glob": paths.option_minutes,
            "etf_minute_glob": paths.etf_minutes,
        },
        "execution": {
            "started_at_utc": started.isoformat(),
            "ended_at_utc": ended.isoformat(),
            "command": command,
            "first_frozen_historical_build": True,
        },
        "deterministic_replay": {
            "passed": True,
            "independent_transform_replays": 2,
            "frame_mismatches": 0,
        },
        "artifacts": artifact_hashes,
    }
    score_path = output / "development_score.json"
    write_json(score_path, score)
    score_hash = file_hash(score_path).removeprefix("sha256:")
    failure_payload = _failure_ledger(score, artifact_hashes)
    output_failure_path = output / "failure_ledger.json"
    write_json(output_failure_path, failure_payload)
    failure_path = project / "MATSHIX_V3_FAILURE_LEDGER.json"
    write_json(failure_path, failure_payload)
    failure_hash = file_hash(failure_path).removeprefix("sha256:")
    adjudication_path = project / "MATSHIX_V3_DEVELOPMENT_ADJUDICATION.md"
    adjudication_path.write_text(
        _render_adjudication(
            score,
            artifact_hashes=artifact_hashes,
            score_hash=score_hash,
            failure_hash=failure_hash,
        ),
        encoding="utf-8",
    )
    return V3BuildArtifacts(
        outcome_path,
        p_path,
        q_path,
        qp_path,
        score_path,
        output_failure_path,
        failure_path,
        adjudication_path,
        score,
    )
