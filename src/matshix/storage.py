from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow", compression="zstd")
    return path


def flatten_market_states(history: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in history.to_dict(orient="records"):
        scores = record["scores"]
        answers = record["answers"]
        breadth = record["breadth_metrics"]
        rows.append(
            {
                "session_date": record["session_date"],
                "evidence_tier": record["evidence_tier"],
                "data_status": record["data_status"],
                "confidence": record["confidence"],
                "primary_phase": record["primary_phase"],
                "raw_phase": record["raw_phase"],
                "pressure_level": record["pressure_level"],
                "direction": record["direction"],
                "pressure_score": record["pressure_score"],
                "insurance_level": scores.get("insurance_level"),
                "shock": scores.get("shock"),
                "down_tail": scores.get("down_tail"),
                "up_tail": scores.get("up_tail"),
                "persistence": scores.get("persistence"),
                "breadth": scores.get("breadth"),
                "repair": scores.get("repair"),
                "level_answer": answers.get("level"),
                "shock_answer": answers.get("shock"),
                "tail_answer": answers.get("tail"),
                "term_answer": answers.get("term"),
                "breadth_answer": answers.get("breadth"),
                "repair_answer": answers.get("repair"),
                "outlook_answer": answers.get("outlook", "UNKNOWN"),
                "large_stressed": breadth["segment_stressed"].get("large"),
                "mid_stressed": breadth["segment_stressed"].get("mid"),
                "tech_stressed": breadth["segment_stressed"].get("tech"),
                "stressed_segment_count": breadth.get("stressed_segment_count"),
                "stressed_index_count": breadth.get("stressed_index_count"),
                "weighted_breadth_score": breadth.get("weighted_breadth_score"),
                "hard_acute": record.get("hard_acute"),
                "persistent_now": record.get("persistent_now"),
                "repair_confirmed": record.get("repair_confirmed"),
                "checkpoint_hash": record.get("checkpoint_hash"),
                "previous_checkpoint_hash": record.get("previous_checkpoint_hash"),
            }
        )
    return pd.DataFrame(rows)


def flatten_economic_index_states(history: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in history.to_dict(orient="records"):
        for economic_index_id, index_state in record["economic_indices"].items():
            axes = index_state["state"]
            rows.append(
                {
                    "session_date": record["session_date"],
                    "economic_index_id": economic_index_id,
                    "carrier_id": index_state["source_carrier"],
                    "data_status": index_state["data_status"],
                    "insurance_level": axes.get("insurance_level"),
                    "shock": axes.get("shock"),
                    "down_tail": axes.get("down_tail"),
                    "up_tail": axes.get("up_tail"),
                    "persistence": axes.get("persistence"),
                    "repair": axes.get("repair"),
                    "index_pressure": axes.get("index_pressure"),
                    "issues": "|".join(index_state["issues"]),
                }
            )
    return pd.DataFrame(rows)
