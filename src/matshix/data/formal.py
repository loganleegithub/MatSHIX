from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from matshix.calendar import surface_cutoff
from matshix.constants import CARRIER_TO_INDEX, EXCLUDED_CARRIERS

FORMAL_REQUIRED_COLUMNS = frozenset(
    {
        "session_date",
        "carrier_id",
        "contract_id",
        "option_type",
        "strike",
        "expiry",
        "bid",
        "ask",
        "event_time",
        "available_at",
        "vintage_kind",
        "revision_id",
        "licence_scope",
    }
)
FORMAL_VINTAGES = frozenset({"FIRST_RELEASE", "AS_TRADED"})


@dataclass(frozen=True)
class FormalInputValidation:
    accepted: bool
    session_date: str
    accepted_rows: int
    carriers: tuple[str, ...]
    issues: tuple[str, ...]


def validate_formal_option_quotes(
    frame: pd.DataFrame,
    *,
    session_date: str,
    non_display_licence_verified: bool,
    sync_tolerance_seconds: int = 5,
) -> FormalInputValidation:
    """Validate the narrow formal hand-off before business calculations begin."""

    issues: list[str] = []
    missing = FORMAL_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        issues.append("MISSING_FIELDS:" + ",".join(sorted(missing)))
        return FormalInputValidation(False, session_date, 0, (), tuple(issues))
    if not non_display_licence_verified:
        issues.append("NON_DISPLAY_LICENCE_NOT_VERIFIED")
    carriers = tuple(sorted(frame["carrier_id"].dropna().astype(str).unique()))
    if set(carriers) != set(CARRIER_TO_INDEX):
        issues.append("FOUR_CARRIER_UNIVERSE_INCOMPLETE")
    if frame["carrier_id"].isin(EXCLUDED_CARRIERS).any():
        issues.append("EXCLUDED_588080_PRESENT")
    bid = pd.to_numeric(frame["bid"], errors="coerce")
    ask = pd.to_numeric(frame["ask"], errors="coerce")
    if bid.isna().any() or ask.isna().any() or (bid <= 0).any() or (ask < bid).any():
        issues.append("INVALID_TWO_SIDED_QUOTE")
    event_time = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    available_at = pd.to_datetime(frame["available_at"], utc=True, errors="coerce")
    cutoff = pd.Timestamp(surface_cutoff(session_date)).tz_convert("UTC")
    if event_time.isna().any():
        issues.append("EVENT_TIME_INVALID")
    else:
        ages = (cutoff - event_time).dt.total_seconds()
        if ((ages < 0) | (ages > sync_tolerance_seconds)).any():
            issues.append("QUOTE_SYNC_TOLERANCE_FAILED")
    if available_at.isna().any() or (available_at > cutoff).any():
        issues.append("PIT_AVAILABILITY_FAILED")
    if not frame["vintage_kind"].isin(FORMAL_VINTAGES).all():
        issues.append("FORMAL_VINTAGE_FAILED")
    revisions = frame["revision_id"]
    if revisions.isna().any() or (revisions.astype(str).str.len() == 0).any():
        issues.append("CONTRACT_REVISION_MISSING")
    if frame["licence_scope"].isna().any():
        issues.append("LICENCE_SCOPE_MISSING")
    return FormalInputValidation(
        accepted=not issues,
        session_date=session_date,
        accepted_rows=len(frame) if not issues else 0,
        carriers=carriers,
        issues=tuple(issues),
    )


def formal_unknown_snapshot(
    *,
    session_date: str,
    source_manifest_hash: str,
    config_hash: str,
    engine_artifact_hash: str,
    blockers: list[str],
) -> dict[str, Any]:
    answers = {
        "level": "UNKNOWN",
        "shock": "UNKNOWN",
        "tail": "UNKNOWN",
        "term": "UNKNOWN",
        "breadth": "UNKNOWN",
        "repair": "UNKNOWN",
        "outlook": "UNKNOWN",
    }
    event_ids = (
        "cross_market_iv_jump_1d",
        "broad_pressure_onset_5d",
        "systemic_acute_stress_5d",
        "persistent_cross_market_stress_20d",
        "fast_repair_5d",
    )
    probabilities = {
        event_id: {
            "event_status": "UNOBSERVABLE",
            "model_status": "NOT_RUN",
            "probability_kind": None,
            "probability": None,
            "base_rate": None,
            "uplift": None,
            "target_window_end_session": None,
            "base_rate_sample_size": None,
            "base_rate_positive_count": None,
            "training_sample_size": None,
            "training_positive_count": None,
            "brier_skill": None,
            "ece": None,
            "interpretation": "正式 PIT 输入不可用，事件不可观察",
        }
        for event_id in event_ids
    }
    return {
        "schema_version": "1.0.0",
        "engine": "MatSHIX",
        "session_date": session_date,
        "run_mode": "FORMAL_PIT_QUOTES",
        "evidence_tier": "FORMAL_PIT",
        "publication_status": "WITHHELD",
        "data_status": "UNKNOWN",
        "confidence": "NONE",
        "primary_phase": "UNKNOWN",
        "pressure_level": "UNKNOWN",
        "direction": "UNKNOWN",
        "pressure_score": None,
        "source_manifest_hash": source_manifest_hash,
        "config_hash": config_hash,
        "engine_artifact_hash": engine_artifact_hash,
        "answers": answers,
        "probabilities": probabilities,
        "narrative": {
            "headline": "今日核心曲面或正式数据链不足，暂不形成完整上交所期权市场天气。",
            "narrative": "正式发布保持 UNKNOWN；缺失的是授权、PIT 可用的同步双边盘口，而不是市场判断为平静。",
        },
        "data_quality": {"blockers": blockers},
    }
