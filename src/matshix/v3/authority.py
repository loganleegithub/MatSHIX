from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from matshix.serialization import file_hash

AUTHORITY_VERSION = "3.0.0"
AUTHORITY_DOCUMENT = "MATSHIX_V3_AUTHORITY.md"
AUTHORITY_SHA256 = "01bb4a250da9bf6d738f17e5345ff7b2370c5315ad092b2c2cf3741d4114f454"
CONSTRUCTION_PLAN = "MATSHIX_V3_CONSTRUCTION_PLAN.md"
CONSTRUCTION_PLAN_SHA256 = "468197a6c6037ab050f0ff372190f86747361420483b93bb98d21e14af2d80bc"
BASELINE_MANIFEST = "MATSHIX_V3_BASELINE_MANIFEST.json"

CONTRACT_COMMIT = "f69b3a25b70c667d4c8c1e0e5d0a21981e40e38d"
STABLE_PARENT_COMMIT = "ca32d3bbe175c84ea16e3c9b265b679896d23c6e"
V2_ARCHIVE_REF = "archive/matshix-v2.2.3-development-fail"
V2_ARCHIVE_COMMIT = "93f883b063953525890430ae54731f23da354659"
V2_ARCHIVE_EVIDENCE_HASHES = {
    "MATSHIX_V2_2_3_AUTHORITY.md": (
        "d47dc66aac34061d0b7287d6caa7877f3077d7f7aca1cd158b5d3805315de665"
    ),
    "MATSHIX_V2_2_3_DEVELOPMENT_ADJUDICATION.md": (
        "31d4b2721f5faf3fb41141bf89f1a6381d6a0955ab48cb26d7aa5bd0bebdc522"
    ),
    "MATSHIX_V2_2_3_FAILURE_LEDGER.json": (
        "eaef94437687b4a854c3e7b4f386819cc904105b1e7ed1e392798512671d0a5e"
    ),
}

SHORTVOL_HASHES = {
    "src/matshix/research/shortvol.py": (
        "8ff1e988937229abf591dde95b0d0b796fb756e9b2dd988ec11da4260c6641c8"
    ),
    "src/matshix/research/shortvol_timing.py": (
        "1034a0d942491ab084ee2ac20e7a172ea678927d829907aa0fccd5fd69bd0cd6"
    ),
}

CARRIER_ID = "CSI300_510300"
ECONOMIC_INDEX_ID = "CSI300"
UNDERLYING_SYMBOL = "510300.SH"
DEVELOPMENT_START = pd.Timestamp("2020-01-02")
DEVELOPMENT_END = pd.Timestamp("2026-06-05")
HORIZON_SESSIONS = 20
PATH_HORIZON_SESSIONS = 10

HAR_FEATURES = (
    "log_rv_d1_lag1",
    "log_mean_rv_d5_lag1",
    "log_mean_rv_d22_lag1",
)
CHALLENGER_FEATURES = (*HAR_FEATURES, "log_q_variance_h20")
FORBIDDEN_MODEL_FIELDS = (
    "common_iv_shock",
    "downside_price_shock",
    "upside_price_shock",
    "down_tail",
    "up_tail",
    "pnl",
    "nav",
    "position",
    "leg",
    "exit",
    "strategy_return",
)

P_BOOTSTRAP_SEED = 2026082401
Q_BOOTSTRAP_SEED = 2026082402
QP_BOOTSTRAP_SEED = 2026082403
BOOTSTRAP_REPETITIONS = 2000
BOOTSTRAP_BLOCK_LENGTH = 20


def _git(project: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_blob_sha256(project: Path, ref: str, relative: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=project,
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


def verify_frozen_contract(project_dir: Path) -> dict[str, Any]:
    project = project_dir.expanduser().resolve()
    expected_files = {
        AUTHORITY_DOCUMENT: AUTHORITY_SHA256,
        CONSTRUCTION_PLAN: CONSTRUCTION_PLAN_SHA256,
        **SHORTVOL_HASHES,
    }
    verified: dict[str, dict[str, str]] = {}
    for relative, expected in expected_files.items():
        actual = file_hash(project / relative).removeprefix("sha256:")
        if actual != expected:
            raise ValueError(
                f"frozen V3 input mismatch for {relative}: expected {expected}, got {actual}"
            )
        verified[relative] = {"sha256": actual, "status": "VERIFIED"}

    archive_commit = _git(project, "rev-parse", f"{V2_ARCHIVE_REF}^{{}}")
    if archive_commit != V2_ARCHIVE_COMMIT:
        raise ValueError(
            f"V2 failed archive mismatch: expected {V2_ARCHIVE_COMMIT}, got {archive_commit}"
        )
    archive_evidence: dict[str, dict[str, str]] = {}
    for relative, expected in V2_ARCHIVE_EVIDENCE_HASHES.items():
        actual = _git_blob_sha256(project, V2_ARCHIVE_COMMIT, relative)
        if actual != expected:
            raise ValueError(
                f"V2 archive evidence mismatch for {relative}: expected {expected}, got {actual}"
            )
        archive_evidence[relative] = {"sha256": actual, "status": "VERIFIED"}

    manifest_path = project / BASELINE_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("baseline_id") != "MATSHIX_V3_PRE_SEMANTIC_CONSTRUCTION_2026_08_24":
        raise ValueError("unexpected V3 baseline manifest identity")
    return {
        "files": verified,
        "archive_ref": V2_ARCHIVE_REF,
        "archive_commit": archive_commit,
        "archive_evidence": archive_evidence,
        "baseline_manifest": BASELINE_MANIFEST,
        "baseline_manifest_sha256": file_hash(manifest_path),
    }
