from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

from matshix.calendar import (
    expiry_timestamp,
    settlement_observation_time,
    surface_cutoff,
    year_fraction_act365f,
)
from matshix.data.aetf import AetfPaths, extract_history, extract_settlement_history
from matshix.serialization import file_hash, write_json
from matshix.surface.research import _deduplicate_contracts
from matshix.v2.local_station import verify_v2_2_authority_chain
from matshix.v2.provenance import repository_provenance, runtime_provenance

AUDIT_CARRIER_ID = "CSI500_510500"
AUDIT_INDEX_ID = "CSI500"
AUDIT_AUTHORITY_VERSION = "2.2.0"
AUDIT_AUTHORITY_SHA256 = "2b6146a0509bfd97f28e6d2299281f0a9837f5beef716f794c78e96f696267d8"
AUDIT_START = pd.Timestamp("2025-01-02")
AUDIT_END = pd.Timestamp("2025-12-31")
PROTOCOL_DOCUMENT = "MATSHIX_V2_2_SETTLEMENT_AUDIT_PROTOCOL.md"
PROTOCOL_SHA256 = "ccc1e1da777426d8abb9e9c1acba93638df4d09e1db054005b49e9efd5c2ea1c"
DISCOUNT_BOUNDS = (0.94, 1.02)
FORWARD_SPOT_BOUNDS = (0.65, 1.35)
MINIMUM_PAIRS = 5


@dataclass(frozen=True)
class V22SettlementAuditArtifacts:
    json_path: Path
    report_path: Path
    result: dict[str, Any]


def _parity_core(frame: pd.DataFrame, *, spot: float) -> dict[str, Any]:
    if not math.isfinite(spot) or spot <= 0:
        return {
            "status": "ETF_MARK_MISSING",
            "pair_count": 0,
            "raw_discount": None,
            "raw_forward": None,
            "raw_forward_spot_ratio": None,
        }
    clean = frame.loc[
        np.isfinite(pd.to_numeric(frame["price"], errors="coerce"))
        & pd.to_numeric(frame["price"], errors="coerce").gt(0)
    ].copy()
    clean = _deduplicate_contracts(clean)
    pivot = clean.pivot(index="strike", columns="option_type", values="price")
    if "C" not in pivot or "P" not in pivot:
        return {
            "status": "PARITY_PAIR_MISSING",
            "pair_count": 0,
            "raw_discount": None,
            "raw_forward": None,
            "raw_forward_spot_ratio": None,
        }
    pairs = pivot.dropna(subset=["C", "P"]).copy()
    pairs = pairs.loc[
        pairs["C"].gt(0)
        & pairs["P"].gt(0)
        & (pairs.index >= FORWARD_SPOT_BOUNDS[0] * spot)
        & (pairs.index <= FORWARD_SPOT_BOUNDS[1] * spot)
    ]
    if len(pairs) < MINIMUM_PAIRS:
        return {
            "status": "PARITY_PAIR_MISSING",
            "pair_count": len(pairs),
            "raw_discount": None,
            "raw_forward": None,
            "raw_forward_spot_ratio": None,
        }
    strikes = pairs.index.to_numpy(dtype=float)
    differences = (pairs["C"] - pairs["P"]).to_numpy(dtype=float)
    slope = float(theilslopes(differences, strikes, method="joint").slope)
    discount = -slope
    forwards = strikes + differences / discount if discount != 0 else np.full_like(strikes, np.nan)
    forward = float(np.median(forwards))
    ratio = forward / spot
    if not math.isfinite(discount) or not DISCOUNT_BOUNDS[0] <= discount <= DISCOUNT_BOUNDS[1]:
        status = "PARITY_DISCOUNT_INVALID"
    elif not math.isfinite(forward) or not FORWARD_SPOT_BOUNDS[0] <= ratio <= FORWARD_SPOT_BOUNDS[1]:
        status = "PARITY_FORWARD_INVALID"
    else:
        status = "OK"
    return {
        "status": status,
        "pair_count": len(pairs),
        "raw_discount": discount if math.isfinite(discount) else None,
        "raw_forward": forward if math.isfinite(forward) else None,
        "raw_forward_spot_ratio": ratio if math.isfinite(ratio) else None,
    }


def parity_diagnostic(
    frame: pd.DataFrame,
    *,
    spot: float,
    observation_time: datetime,
    expiry: pd.Timestamp,
) -> dict[str, Any]:
    eligible = frame.loc[
        pd.to_numeric(frame["contract_unit"], errors="coerce").gt(0)
        & frame["option_type"].isin(["C", "P"])
    ].copy()
    standard = eligible.loc[eligible["is_standard"].fillna(False)].copy()
    all_result = _parity_core(eligible, spot=spot)
    standard_result = _parity_core(standard, spot=spot)

    family_pair_strikes = 0
    unit_matched_pair_strikes = 0
    unit_mismatched_only_pair_strikes = 0
    for _, strike_group in eligible.groupby("strike", sort=True):
        call_units = set(
            pd.to_numeric(
                strike_group.loc[strike_group["option_type"].eq("C"), "contract_unit"],
                errors="coerce",
            )
            .dropna()
            .astype(float)
        )
        put_units = set(
            pd.to_numeric(
                strike_group.loc[strike_group["option_type"].eq("P"), "contract_unit"],
                errors="coerce",
            )
            .dropna()
            .astype(float)
        )
        if not call_units or not put_units:
            continue
        family_pair_strikes += 1
        if call_units.intersection(put_units):
            unit_matched_pair_strikes += 1
        else:
            unit_mismatched_only_pair_strikes += 1

    expiry_text = pd.Timestamp(expiry).date().isoformat()
    dte = year_fraction_act365f(observation_time, expiry_timestamp(expiry_text)) * 365.0
    return {
        **all_result,
        "dte": dte,
        "input_contracts": len(frame),
        "eligible_contracts": len(eligible),
        "standard_contracts": len(standard),
        "nonstandard_contracts": len(eligible) - len(standard),
        "selected_nonstandard_contracts": int(
            (~_deduplicate_contracts(eligible)["is_standard"].fillna(False)).sum()
        ),
        "standard_only_status": standard_result["status"],
        "standard_only_pair_count": standard_result["pair_count"],
        "standard_only_raw_discount": standard_result["raw_discount"],
        "standard_only_rescue": bool(
            all_result["status"] != "OK" and standard_result["status"] == "OK"
        ),
        "family_pair_strikes": family_pair_strikes,
        "unit_matched_pair_strikes": unit_matched_pair_strikes,
        "unit_mismatched_only_pair_strikes": unit_mismatched_only_pair_strikes,
        "unit_mismatched_only_chain": bool(
            family_pair_strikes > 0
            and unit_matched_pair_strikes == 0
            and unit_mismatched_only_pair_strikes > 0
        ),
    }


def _audit_proxy(
    option_prices: pd.DataFrame,
    etf_marks: pd.DataFrame,
    *,
    proxy: str,
    observation_time: Any,
) -> pd.DataFrame:
    options = option_prices.loc[option_prices["carrier_id"].astype(str).eq(AUDIT_CARRIER_ID)].copy()
    marks = etf_marks.loc[etf_marks["carrier_id"].astype(str).eq(AUDIT_CARRIER_ID)].copy()
    spots = {
        pd.Timestamp(row["session_date"]).normalize(): float(row["etf_mark"])
        for row in marks.to_dict(orient="records")
    }
    rows: list[dict[str, Any]] = []
    for (session, expiry), group in options.groupby(["session_date", "expiry"], sort=True):
        session_value = pd.Timestamp(session).normalize()
        spot = spots.get(session_value)
        if spot is None:
            continue
        result = parity_diagnostic(
            group,
            spot=spot,
            observation_time=observation_time(session_value),
            expiry=pd.Timestamp(expiry),
        )
        rows.append(
            {
                "session_date": session_value,
                "expiry": pd.Timestamp(expiry).normalize(),
                "proxy": proxy,
                "spot": spot,
                **result,
            }
        )
    return pd.DataFrame(rows).sort_values(["session_date", "expiry"], kind="stable").reset_index(
        drop=True
    )


def merge_proxy_audits(settlement: pd.DataFrame, minute: pd.DataFrame) -> pd.DataFrame:
    keys = ["session_date", "expiry"]
    left = settlement.add_prefix("settlement_").rename(
        columns={f"settlement_{key}": key for key in keys}
    )
    right = minute.add_prefix("minute_").rename(columns={f"minute_{key}": key for key in keys})
    result = left.merge(right, on=keys, how="outer", indicator=True)
    result["same_chain_present"] = result["_merge"].eq("both")
    result["settlement_invalid_minute_ok"] = result[
        "settlement_status"
    ].eq("PARITY_DISCOUNT_INVALID") & result["minute_status"].eq("OK")
    return result.sort_values(keys, kind="stable").reset_index(drop=True)


def classify_audit(rows: pd.DataFrame) -> dict[str, Any]:
    paired = rows.loc[rows["same_chain_present"].astype(bool)].copy()
    invalid = paired.loc[paired["settlement_status"].eq("PARITY_DISCOUNT_INVALID")].copy()
    recovered = invalid.loc[invalid["minute_status"].eq("OK")].copy()
    invalid_count = len(invalid)
    recovery_share = len(recovered) / invalid_count if invalid_count else 0.0
    standard_rescue_share = (
        float(invalid["settlement_standard_only_rescue"].astype(bool).mean())
        if invalid_count
        else 0.0
    )
    unit_mismatch_share = (
        float(invalid["settlement_unit_mismatched_only_chain"].astype(bool).mean())
        if invalid_count
        else 0.0
    )
    settlement_median = pd.to_numeric(
        recovered["settlement_raw_discount"], errors="coerce"
    ).median()
    minute_median = pd.to_numeric(recovered["minute_raw_discount"], errors="coerce").median()
    settlement_median_value = None if pd.isna(settlement_median) else float(settlement_median)
    minute_median_value = None if pd.isna(minute_median) else float(minute_median)

    data_defect = bool(
        invalid_count >= 126
        and (standard_rescue_share >= 0.50 or unit_mismatch_share >= 0.50)
    )
    method_mismatch = bool(
        invalid_count >= 126
        and recovery_share >= 0.70
        and settlement_median_value is not None
        and not DISCOUNT_BOUNDS[0] <= settlement_median_value <= DISCOUNT_BOUNDS[1]
        and minute_median_value is not None
        and DISCOUNT_BOUNDS[0] <= minute_median_value <= DISCOUNT_BOUNDS[1]
        and standard_rescue_share < 0.10
    )
    if data_defect:
        verdict = "DATA_FIELD_DEFECT"
        reason = "STANDARD_OR_CONTRACT_UNIT_RESCUE_DOMINATES"
    elif method_mismatch:
        verdict = "METHOD_MISMATCH"
        reason = "SETTLEMENT_PARITY_REJECTED_WHILE_SAME_CHAIN_MINUTE_PARITY_RECOVERS"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
        reason = "FROZEN_CAUSAL_CLASSIFICATION_NOT_MET"
    return {
        "verdict": verdict,
        "reason": reason,
        "paired_expiry_chains": len(paired),
        "settlement_discount_invalid_chains": invalid_count,
        "minute_recovered_chains": len(recovered),
        "minute_recovery_share": recovery_share,
        "standard_only_rescue_chains": int(
            invalid["settlement_standard_only_rescue"].astype(bool).sum()
        ),
        "standard_only_rescue_share": standard_rescue_share,
        "unit_mismatched_only_chains": int(
            invalid["settlement_unit_mismatched_only_chain"].astype(bool).sum()
        ),
        "unit_mismatched_only_share": unit_mismatch_share,
        "recovered_settlement_raw_discount_median": settlement_median_value,
        "recovered_minute_raw_discount_median": minute_median_value,
        "thresholds": {
            "minimum_invalid_chains": 126,
            "data_rescue_share": 0.50,
            "method_recovery_share": 0.70,
            "maximum_standard_rescue_share_for_method": 0.10,
            "discount_bounds": list(DISCOUNT_BOUNDS),
        },
    }


def _dte_strata(rows: pd.DataFrame) -> list[dict[str, Any]]:
    settlement_dte = pd.to_numeric(rows["settlement_dte"], errors="coerce")
    buckets = pd.cut(
        settlement_dte,
        bins=[-np.inf, 20, 40, 70, np.inf],
        labels=["LE20", "21_40", "41_70", "GT70"],
    )
    frame = rows.assign(dte_bucket=buckets)
    output: list[dict[str, Any]] = []
    for bucket, group in frame.groupby("dte_bucket", observed=True, sort=True):
        invalid = group["settlement_status"].eq("PARITY_DISCOUNT_INVALID")
        output.append(
            {
                "dte_bucket": str(bucket),
                "chains": len(group),
                "settlement_discount_invalid": int(invalid.sum()),
                "minute_recovered": int((invalid & group["minute_status"].eq("OK")).sum()),
                "settlement_raw_discount_median": float(
                    pd.to_numeric(group["settlement_raw_discount"], errors="coerce").median()
                )
                if pd.to_numeric(group["settlement_raw_discount"], errors="coerce").notna().any()
                else None,
                "minute_raw_discount_median": float(
                    pd.to_numeric(group["minute_raw_discount"], errors="coerce").median()
                )
                if pd.to_numeric(group["minute_raw_discount"], errors="coerce").notna().any()
                else None,
            }
        )
    return output


def _status_counts(frame: pd.DataFrame, field: str) -> dict[str, int]:
    return {str(key): int(value) for key, value in frame[field].value_counts().items()}


def _render_report(result: dict[str, Any]) -> str:
    verdict = result["classification"]
    interpretations = {
        "DATA_FIELD_DEFECT": (
            "冻结证据支持 settlement 合约字段缺陷；该结论不授权修改 parity 容错，"
            "也不改变 CSI300_LOCAL 裁决。"
        ),
        "METHOD_MISMATCH": (
            "冻结证据支持当前 call-put parity admissibility 与 provider-reconstructed "
            "settlement 构造不匹配；不证明 settlement 字段错误，也不授权扩大 discount "
            "range、配对容错或修改 CSI300_LOCAL 裁决。"
        ),
        "INSUFFICIENT_EVIDENCE": (
            "冻结证据不足以把 2025 年 settlement 失败归因为合约字段缺陷或方法不匹配；"
            "不得据此修改 parity 容错或 CSI300_LOCAL 裁决。"
        ),
    }
    lines = [
        "# MatSHIX V2.2 CSI500 2025 settlement parity audit",
        "",
        f"- Verdict: `{verdict['verdict']}`",
        f"- Reason: `{verdict['reason']}`",
        f"- Authority: `{AUDIT_AUTHORITY_VERSION}` / `{AUDIT_AUTHORITY_SHA256}`",
        f"- Protocol: `{PROTOCOL_SHA256}`",
        "- Strategy inputs used: `false`",
        "- Pricing tolerances changed: `false`",
        "",
        "## Frozen classification evidence",
        "",
        f"- paired expiry chains: `{verdict['paired_expiry_chains']}`",
        f"- settlement discount-invalid: `{verdict['settlement_discount_invalid_chains']}`",
        f"- same-chain minute recovered: `{verdict['minute_recovered_chains']}` / "
        f"`{verdict['minute_recovery_share']:.2%}`",
        f"- standard-only rescue: `{verdict['standard_only_rescue_chains']}` / "
        f"`{verdict['standard_only_rescue_share']:.2%}`",
        f"- unit-mismatched-only chains: `{verdict['unit_mismatched_only_chains']}` / "
        f"`{verdict['unit_mismatched_only_share']:.2%}`",
        f"- recovered settlement/minute raw discount median: "
        f"`{verdict['recovered_settlement_raw_discount_median']}` / "
        f"`{verdict['recovered_minute_raw_discount_median']}`",
        "",
        "## Interpretation boundary",
        "",
        interpretations[verdict["verdict"]],
        "",
    ]
    return "\n".join(lines)


def run_v2_2_settlement_audit(
    *, project_dir: Path, aetf_root: Path
) -> V22SettlementAuditArtifacts:
    project = project_dir.expanduser().resolve()
    authority_chain = verify_v2_2_authority_chain(project)
    protocol_hash = file_hash(project / PROTOCOL_DOCUMENT).removeprefix("sha256:")
    if protocol_hash != PROTOCOL_SHA256:
        raise ValueError("frozen settlement audit protocol hash mismatch")
    paths = AetfPaths.from_root(aetf_root)
    settlement = extract_settlement_history(
        paths,
        start=AUDIT_START.date().isoformat(),
        end=AUDIT_END.date().isoformat(),
    )
    minute = extract_history(
        paths,
        start=AUDIT_START.date().isoformat(),
        end=AUDIT_END.date().isoformat(),
    )
    settlement_rows = _audit_proxy(
        settlement.option_prices,
        settlement.etf_marks,
        proxy="PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT",
        observation_time=settlement_observation_time,
    )
    minute_rows = _audit_proxy(
        minute.option_prices,
        minute.etf_marks,
        proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
    )
    replay_settlement = _audit_proxy(
        settlement.option_prices,
        settlement.etf_marks,
        proxy="PROVIDER_RECONSTRUCTED_EOD_SETTLEMENT",
        observation_time=settlement_observation_time,
    )
    replay_minute = _audit_proxy(
        minute.option_prices,
        minute.etf_marks,
        proxy="MINUTE_CLOSE_1456",
        observation_time=surface_cutoff,
    )
    pd.testing.assert_frame_equal(settlement_rows, replay_settlement, check_exact=True)
    pd.testing.assert_frame_equal(minute_rows, replay_minute, check_exact=True)
    rows = merge_proxy_audits(settlement_rows, minute_rows)
    classification = classify_audit(rows)
    result: dict[str, Any] = {
        "audit_version": AUDIT_AUTHORITY_VERSION,
        "authority_sha256": AUDIT_AUTHORITY_SHA256,
        "protocol_document": PROTOCOL_DOCUMENT,
        "protocol_sha256": PROTOCOL_SHA256,
        "carrier_scope": AUDIT_CARRIER_ID,
        "economic_index_id": AUDIT_INDEX_ID,
        "audit_range": [AUDIT_START.date().isoformat(), AUDIT_END.date().isoformat()],
        "classification": classification,
        "status_counts": {
            "settlement": _status_counts(settlement_rows, "status"),
            "minute_1456": _status_counts(minute_rows, "status"),
        },
        "dte_strata": _dte_strata(rows),
        "rows": rows.to_dict(orient="records"),
        "authority_chain": authority_chain,
        "repository": repository_provenance(project),
        "runtime": runtime_provenance(),
        "inputs": {
            "aetf_root": str(Path(aetf_root).expanduser().resolve()),
            "option_contracts_sha256": file_hash(paths.option_contracts),
        },
        "deterministic_replay": True,
        "strategy_inputs_used": False,
        "pricing_tolerances_changed": False,
        "csi300_adjudication_changed": False,
    }
    output = project / "outputs/v2_2_audit"
    json_path = output / "settlement_parity_audit.json"
    write_json(json_path, result)
    report_path = output / "settlement_parity_audit.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(result), encoding="utf-8")
    return V22SettlementAuditArtifacts(json_path, report_path, result)
