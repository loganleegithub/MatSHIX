from __future__ import annotations

from typing import Any

import pandas as pd

from matshix.calendar import exchange_decision_as_of
from matshix.constants import CARRIER_TO_INDEX, INDEX_ORDER, INDEX_TO_CARRIER
from matshix.narrative import build_narrative, rank_evidence
from matshix.serialization import jsonable


def build_research_snapshot(
    *,
    state: dict[str, Any],
    index_rows: dict[str, dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
    source_manifest_hash: str,
    config_hash: str,
    input_hash: str,
    engine_artifact_hash: str,
    revision_id: str,
    coverage_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    session = pd.Timestamp(state["session_date"]).normalize()
    answers = dict(state["answers"])
    evidence = rank_evidence(index_rows)
    narrative = build_narrative({**state, "answers": answers}, evidence)
    proxy_methods: list[dict[str, str]] = []
    indices: dict[str, Any] = {}
    for index in INDEX_ORDER:
        row = index_rows[index]
        scored = state["economic_indices"][index]
        for metric, method_field in (
            ("IV30", "iv30_method"),
            ("IV60", "iv60_method"),
            ("IV90", "iv90_method"),
            ("ATM30", "atm_iv30_method"),
            ("PUT25_30", "iv_25d_put30_method"),
            ("CALL25_30", "iv_25d_call30_method"),
        ):
            method = str(row.get(method_field, "UNAVAILABLE"))
            if "PROXY" in method:
                proxy_methods.append(
                    {"economic_index_id": index, "metric": metric, "method": method}
                )
        indices[index] = {
            "carrier_id": INDEX_TO_CARRIER[index],
            "data_status": scored["data_status"],
            "surface_status": row.get("surface_status"),
            "scores": scored["state"],
            "surface": {
                "iv30_mf": row.get("iv30_mf"),
                "iv30_method": row.get("iv30_method"),
                "iv60_mf": row.get("iv60_mf"),
                "iv60_method": row.get("iv60_method"),
                "iv90_mf": row.get("iv90_mf"),
                "iv90_method": row.get("iv90_method"),
                "fvol_30_90": row.get("fvol_30_90"),
                "atm_iv30": row.get("atm_iv30"),
                "atm_iv30_method": row.get("atm_iv30_method"),
                "iv_25d_put30": row.get("iv_25d_put30"),
                "iv_25d_put30_method": row.get("iv_25d_put30_method"),
                "iv_25d_call30": row.get("iv_25d_call30"),
                "iv_25d_call30_method": row.get("iv_25d_call30_method"),
                "down_skew25": row.get("down_skew25"),
                "up_skew25": row.get("up_skew25"),
                "pcr_volume": row.get("pcr_volume"),
                "pcr_oi": row.get("pcr_oi"),
            },
            "insurance_compensation": row.get("insurance_compensation"),
            "issues": scored["issues"],
        }
    narrative["research_proxies"] = proxy_methods
    if proxy_methods:
        proxy_text = "；".join(
            f"{value['economic_index_id']}.{value['metric']}={value['method']}"
            for value in proxy_methods
        )
        narrative["narrative"] += f"\n研究代理：{proxy_text}。"
    payload = {
        "schema_version": "1.0.0",
        "engine": "MatSHIX",
        "session_date": session.date().isoformat(),
        "decision_as_of": exchange_decision_as_of(session).isoformat(),
        "run_mode": "RESEARCH_MINUTE_CLOSE",
        "evidence_tier": "RESEARCH_ONLY",
        "publication_status": "RESEARCH_ONLY_NOT_FORMAL",
        "data_status": state["data_status"],
        "confidence": state["confidence"],
        "primary_phase": state["primary_phase"],
        "pressure_level": state["pressure_level"],
        "direction": state["direction"],
        "pressure_score": state["pressure_score"],
        "source_manifest_hash": source_manifest_hash,
        "config_hash": config_hash,
        "input_hash": input_hash,
        "engine_artifact_hash": engine_artifact_hash,
        "revision_id": revision_id,
        "methodology_versions": {
            "surface": "MATSHIX_RESEARCH_MINUTE_CLOSE_V2",
            "feature": "1.0.0",
            "state": "1.0.0",
            "probability": "1.0.0",
        },
        "universe": {
            "carriers": list(CARRIER_TO_INDEX),
            "economic_indices": list(INDEX_ORDER),
            "excluded_carriers": ["STAR50_588080"],
        },
        "scores": state["scores"],
        "answers": answers,
        "breadth": state["breadth_metrics"],
        "economic_indices": indices,
        "probabilities": judgments,
        "narrative": narrative,
        "data_quality": {
            "price_kind": "AETF 14:56 minute close",
            "vintage_kind": "PROVIDER_RECONSTRUCTED",
            "licence_scope": "LOCAL_RESEARCH_RIGHTS_UNVERIFIED",
            "formal_bid_ask_available": False,
            "formal_publication_allowed": False,
            "coverage": coverage_summary,
            "formal_blockers": [
                "AUTHORIZED_SYNCHRONIZED_BID_ASK_NOT_AVAILABLE",
                "PIT_AVAILABILITY_NOT_PROVEN",
                "CONTRACT_REVISION_CHAIN_NOT_PROVEN",
                "NON_DISPLAY_LICENCE_NOT_VERIFIED",
            ],
        },
    }
    converted = jsonable(payload)
    if not isinstance(converted, dict):
        raise TypeError("snapshot conversion did not produce an object")
    return converted
