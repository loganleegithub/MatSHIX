from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from matshix.constants import ACUTE_PHASES, IMMEDIATE_PHASES


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PhaseCheckpoint:
    session_date: str
    published_phase: str
    candidate_phase: str | None
    candidate_streak: int
    state_version: str
    config_hash: str
    previous_checkpoint_hash: str | None

    @property
    def checkpoint_hash(self) -> str:
        return _stable_hash(asdict(self))


def transition_phase(
    *,
    session_date: str,
    raw_phase: str,
    data_status: str,
    hard_acute: bool | None,
    shock_score: float | None,
    previous: PhaseCheckpoint | None,
    config_hash: str,
) -> PhaseCheckpoint:
    candidate: str | None = None
    streak = 0
    if data_status != "OK" or raw_phase == "UNKNOWN":
        published = "UNKNOWN"
    elif previous is None or previous.published_phase == "UNKNOWN":
        published = raw_phase
    elif previous.published_phase in ACUTE_PHASES:
        if raw_phase in ACUTE_PHASES:
            published = raw_phase
        elif hard_acute is False and shock_score is not None and shock_score < 75:
            candidate = raw_phase
            streak = previous.candidate_streak + 1 if previous.candidate_phase == raw_phase else 1
            if streak >= 2:
                published = raw_phase
                candidate = None
                streak = 0
            else:
                published = previous.published_phase
        else:
            published = previous.published_phase
    elif raw_phase in IMMEDIATE_PHASES:
        published = raw_phase
    elif raw_phase == previous.published_phase:
        published = previous.published_phase
    else:
        candidate = raw_phase
        streak = previous.candidate_streak + 1 if previous.candidate_phase == raw_phase else 1
        if streak >= 2:
            published = raw_phase
            candidate = None
            streak = 0
        else:
            published = previous.published_phase
    return PhaseCheckpoint(
        session_date=session_date,
        published_phase=published,
        candidate_phase=candidate,
        candidate_streak=streak,
        state_version="1.0.0",
        config_hash=config_hash,
        previous_checkpoint_hash=None if previous is None else previous.checkpoint_hash,
    )


def apply_phase_hysteresis(history: pd.DataFrame, *, config_hash: str) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    previous: PhaseCheckpoint | None = None
    for record in history.sort_values("session_date").to_dict(orient="records"):
        shock = record.get("scores", {}).get("shock")
        checkpoint = transition_phase(
            session_date=pd.Timestamp(record["session_date"]).date().isoformat(),
            raw_phase=str(record["raw_phase"]),
            data_status=str(record["data_status"]),
            hard_acute=record.get("hard_acute"),
            shock_score=None if shock is None or pd.isna(shock) else float(shock),
            previous=previous,
            config_hash=config_hash,
        )
        current = dict(record)
        current["primary_phase"] = checkpoint.published_phase
        current["candidate_phase"] = checkpoint.candidate_phase
        current["candidate_streak"] = checkpoint.candidate_streak
        current["previous_checkpoint_hash"] = checkpoint.previous_checkpoint_hash
        current["checkpoint_hash"] = checkpoint.checkpoint_hash
        output.append(current)
        previous = checkpoint
    return pd.DataFrame(output)
