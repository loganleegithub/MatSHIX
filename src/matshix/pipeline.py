from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from matshix.calendar import exchange_decision_as_of
from matshix.constants import CARRIER_TO_INDEX, EVENT_IDS, INDEX_ORDER
from matshix.data.aetf import AetfExtraction, AetfPaths, extract_history, extraction_metadata
from matshix.data.formal import formal_unknown_snapshot
from matshix.features.history import build_index_feature_history
from matshix.narrative import rank_evidence
from matshix.probability.model import (
    acceptance_metrics,
    fit_current_probability,
    generate_oof_predictions,
    sequential_calibration,
)
from matshix.probability.predictors import add_probability_predictors
from matshix.probability.publication import build_current_judgments, determine_outlook
from matshix.probability.targets import build_target_ledger
from matshix.serialization import content_hash, file_hash, write_json
from matshix.snapshot import build_research_snapshot
from matshix.state.ontology import add_state_ontology
from matshix.state.scores import build_market_score_history
from matshix.state.transitions import apply_phase_hysteresis
from matshix.storage import flatten_economic_index_states, flatten_market_states, write_parquet
from matshix.surface.research import ResearchCarrierSurface, build_carrier_surface

Progress = Callable[[str], None]


@dataclass(frozen=True)
class BuildResult:
    project_dir: str
    start_session: str
    end_session: str
    extracted_sessions: int
    state_sessions: int
    latest_snapshot: str
    formal_snapshot: str
    acceptance_report: str
    dashboard_input: str
    engine_artifact_hash: str
    revision_id: str


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return value


def _configuration(project_dir: Path) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    model = _load_yaml(project_dir / "configs/model_v1.yaml")
    source = _load_yaml(project_dir / "configs/source_manifest_v1.yaml")
    return model, source, content_hash(model), content_hash(source)


def compute_engine_artifact_hash(project_dir: Path) -> str:
    files = sorted((project_dir / "src/matshix").rglob("*.py"))
    files.extend(sorted((project_dir / "schemas").glob("*.json")))
    files.extend(
        project_dir / name
        for name in ("pyproject.toml", "requirements.lock", "requirements-dev.lock")
    )
    return content_hash(
        {str(path.relative_to(project_dir)): file_hash(path) for path in files if path.is_file()}
    )


def _flatten_surface(
    surface: ResearchCarrierSurface,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    carrier = asdict(surface)
    expiries = carrier.pop("expiries")
    carrier["issues"] = "|".join(carrier["issues"])
    expiry_rows: list[dict[str, Any]] = []
    for expiry in expiries:
        expiry_rows.append(
            {
                "session_date": carrier["session_date"],
                "carrier_id": carrier["carrier_id"],
                "economic_index_id": carrier["economic_index_id"],
                "evidence_tier": carrier["evidence_tier"],
                "methodology_version": carrier["methodology_version"],
                **expiry,
                "issues": "|".join(expiry["issues"]),
            }
        )
    return carrier, expiry_rows


def build_surface_history(
    extraction: AetfExtraction,
    *,
    minimum_total_strikes: int = 9,
    include_identifiable_adjusted_contracts: bool = True,
    nearest_tenor_max_distance_days: dict[int, int] | None = None,
    nearest_delta_max_distance: float = 0.12,
    nearest_atm_log_moneyness: float = 0.08,
    progress: Progress | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    marks = extraction.etf_marks.set_index(["session_date", "carrier_id"])["etf_mark"]
    groups = list(extraction.option_prices.groupby(["session_date", "carrier_id"], sort=True))
    carrier_rows: list[dict[str, Any]] = []
    expiry_rows: list[dict[str, Any]] = []
    total = len(groups)
    for number, ((session, carrier_id), frame) in enumerate(groups, start=1):
        key = (pd.Timestamp(session), str(carrier_id))
        if key not in marks.index:
            continue
        carrier = str(carrier_id)
        surface = build_carrier_surface(
            frame,
            session_date=pd.Timestamp(session).date().isoformat(),
            carrier_id=carrier,
            economic_index_id=CARRIER_TO_INDEX[carrier],
            spot=float(marks.loc[key]),
            minimum_total_strikes=minimum_total_strikes,
            include_identifiable_adjusted_contracts=include_identifiable_adjusted_contracts,
            nearest_tenor_max_distance_days=nearest_tenor_max_distance_days,
            nearest_delta_max_distance=nearest_delta_max_distance,
            nearest_atm_log_moneyness=nearest_atm_log_moneyness,
        )
        flat, expiry = _flatten_surface(surface)
        carrier_rows.append(flat)
        expiry_rows.extend(expiry)
        if progress is not None and (number == 1 or number % 100 == 0 or number == total):
            progress(f"曲面 {number}/{total}: {pd.Timestamp(session).date()} {carrier}")
    carriers = pd.DataFrame(carrier_rows)
    expiries = pd.DataFrame(expiry_rows)
    for frame in (carriers, expiries):
        frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    return carriers, expiries


def coverage_table(surfaces: pd.DataFrame) -> pd.DataFrame:
    frame = surfaces.copy()
    frame["year"] = pd.to_datetime(frame["session_date"]).dt.year
    rows: list[dict[str, Any]] = []
    for (carrier, year), group in frame.groupby(["carrier_id", "year"], sort=True):
        count = len(group)
        rows.append(
            {
                "carrier_id": carrier,
                "year": int(year),
                "sessions": count,
                "valid_surface_share": float((group["surface_status"] == "VALID").mean()),
                "iv30_bracket_share": float(
                    group["iv30_method"].eq("TOTAL_VARIANCE_INTERPOLATION").mean()
                ),
                "iv30_reference_share": float(group["iv30_mf"].notna().mean()),
                "iv90_bracket_share": float(
                    group["iv90_method"].eq("TOTAL_VARIANCE_INTERPOLATION").mean()
                ),
                "iv90_reference_share": float(group["iv90_mf"].notna().mean()),
                "put25_bracket_share": float(
                    group["iv_25d_put30_method"].eq("TOTAL_VARIANCE_INTERPOLATION").mean()
                ),
                "put25_reference_share": float(group["iv_25d_put30"].notna().mean()),
                "call25_bracket_share": float(
                    group["iv_25d_call30_method"].eq("TOTAL_VARIANCE_INTERPOLATION").mean()
                ),
                "call25_reference_share": float(group["iv_25d_call30"].notna().mean()),
                "proxy_surface_share": float(
                    group[
                        [
                            "iv30_method",
                            "iv90_method",
                            "iv_25d_put30_method",
                            "iv_25d_call30_method",
                        ]
                    ]
                    .apply(lambda row: any("PROXY" in str(value) for value in row), axis=1)
                    .mean()
                ),
                "formal_two_sided_quote_share": None,
                "relative_spread_median": None,
                "relative_spread_p95": None,
                "price_kind": "MINUTE_CLOSE_NOT_BID_ASK",
            }
        )
    return pd.DataFrame(rows)


def _probability_outputs(
    history: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    ledger = build_target_ledger(history)
    oof_frames: list[pd.DataFrame] = []
    metrics: dict[str, dict[str, Any]] = {}
    raw_oof: dict[str, pd.DataFrame] = {}
    for event_id in EVENT_IDS:
        generated = generate_oof_predictions(ledger, event_id=event_id)
        raw_oof[event_id] = generated
        calibrated = sequential_calibration(generated)
        metrics[event_id] = acceptance_metrics(calibrated, event_id=event_id)
        if not calibrated.empty:
            oof_frames.append(calibrated)
    oof = pd.concat(oof_frames, ignore_index=True) if oof_frames else pd.DataFrame()
    latest_position = int(history["prediction_position"].iloc[-1])
    accepted: dict[str, dict[str, Any]] = {}
    for event_id in EVENT_IDS:
        current = fit_current_probability(
            ledger,
            raw_oof[event_id],
            metrics[event_id],
            event_id=event_id,
            prediction_position=latest_position,
        )
        if current is not None:
            accepted[event_id] = current
    return ledger, oof, metrics, accepted


def _add_outlooks(
    history: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    accepted_latest: dict[str, dict[str, Any]],
    base_rate_minimum_samples: int,
    base_rate_maximum_samples: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    state = history.copy()
    probability_rows: list[dict[str, Any]] = []
    judgments_by_date: dict[str, dict[str, Any]] = {}
    latest_position = int(state["prediction_position"].iloc[-1])
    records: list[dict[str, Any]] = []
    for record in state.to_dict(orient="records"):
        position = int(record["prediction_position"])
        models = accepted_latest if position == latest_position else {}
        judgments = build_current_judgments(
            ledger,
            prediction_position=position,
            accepted_models=models,
            base_rate_minimum_samples=base_rate_minimum_samples,
            base_rate_maximum_samples=base_rate_maximum_samples,
        )
        answers = dict(record["answers"])
        answers["outlook"] = determine_outlook(str(record["data_status"]), judgments)
        record["answers"] = answers
        records.append(record)
        session_key = pd.Timestamp(record["session_date"]).date().isoformat()
        judgments_by_date[session_key] = judgments
        for event_id, value in judgments.items():
            probability_rows.append(
                {
                    "session_date": pd.Timestamp(record["session_date"]),
                    "prediction_position": position,
                    "event_id": event_id,
                    **value,
                }
            )
    return pd.DataFrame(records), pd.DataFrame(probability_rows), judgments_by_date


def _index_rows_for_session(
    features: pd.DataFrame, session: pd.Timestamp
) -> dict[str, dict[str, Any]]:
    selected = features.loc[pd.to_datetime(features["session_date"]).dt.normalize() == session]
    rows = {str(row["economic_index_id"]): row for row in selected.to_dict(orient="records")}
    if set(rows) != set(INDEX_ORDER):
        raise ValueError(f"index feature panel incomplete on {session.date()}")
    return rows


def _attach_table_contract(
    frame: pd.DataFrame,
    *,
    version_field: str,
    version: str,
    common_columns: dict[str, str],
) -> None:
    frame[version_field] = version
    for column, value in common_columns.items():
        frame[column] = value
    if "session_date" in frame.columns:
        sessions = pd.to_datetime(frame["session_date"]).dt.normalize()
        frame["decision_as_of"] = pd.to_datetime(
            [exchange_decision_as_of(value) for value in sessions], utc=True
        )
        frame["available_at"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")


def _issue_ledger(surfaces: pd.DataFrame, expiry_surfaces: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in surfaces.to_dict(orient="records"):
        for issue in str(record.get("issues", "")).split("|"):
            if issue:
                rows.append(
                    {
                        "session_date": record["session_date"],
                        "carrier_id": record["carrier_id"],
                        "expiry": None,
                        "issue_id": issue,
                        "issue_scope": "CARRIER_CORE_OR_PROXY",
                        "resolution_status": "DISCLOSED",
                    }
                )
    for record in expiry_surfaces.to_dict(orient="records"):
        for issue in str(record.get("issues", "")).split("|"):
            if issue:
                rows.append(
                    {
                        "session_date": record["session_date"],
                        "carrier_id": record["carrier_id"],
                        "expiry": record["expiry"],
                        "issue_id": issue,
                        "issue_scope": "EXPIRY_DIAGNOSTIC",
                        "resolution_status": "DISCLOSED",
                    }
                )
    return pd.DataFrame(rows)


def _acceptance_payload(
    *,
    extraction: AetfExtraction,
    surfaces: pd.DataFrame,
    states: pd.DataFrame,
    ledger: pd.DataFrame,
    probability_history: pd.DataFrame,
    metrics: dict[str, dict[str, Any]],
    coverage: pd.DataFrame,
    revision_id: str,
) -> dict[str, Any]:
    option_codes = set(extraction.option_prices["option_underlying_code"].astype(str))
    expected_carriers = set(CARRIER_TO_INDEX)
    actual_carriers = set(surfaces["carrier_id"].astype(str))
    coverage_records = coverage.to_dict(orient="records")
    probability_records: list[dict[str, Any]] = []
    for event_id in EVENT_IDS:
        event = ledger.loc[ledger["event_id"] == event_id]
        observed = event.loc[event["label_status"].isin(["OBSERVED_0", "OBSERVED_1"])]
        probability_records.append(
            {
                "event_id": event_id,
                "eligible": int((event["event_status"] == "ELIGIBLE").sum()),
                "not_applicable": int((event["event_status"] == "NOT_APPLICABLE").sum()),
                "unobservable": int((event["event_status"] == "UNOBSERVABLE").sum()),
                "observed": len(observed),
                "positives": int(observed["label"].sum()) if len(observed) else 0,
                "model_acceptance": metrics[event_id],
            }
        )
    checks = {
        "real_aetf_input_used": len(extraction.option_prices) > 0,
        "four_carriers_present": actual_carriers == expected_carriers,
        "star50_only_588000": "OP588000.SH" in option_codes and "OP588080.SH" not in option_codes,
        "state_history_nonempty": len(states) > 0,
        "minimum_60_state_sessions": len(states) >= 60,
        "minimum_60_publishable_research_states": int(
            ((states["data_status"] == "OK") & (states["primary_phase"] != "UNKNOWN")).sum()
        )
        >= 60,
        "latest_research_narrative_publishable": states.iloc[-1]["data_status"] == "OK"
        and states.iloc[-1]["primary_phase"] != "UNKNOWN",
        "latest_probability_judgment_available": bool(
            probability_history.loc[
                probability_history["prediction_position"]
                == probability_history["prediction_position"].max(),
                "probability",
            ]
            .notna()
            .any()
        ),
        "research_proxy_methods_disclosed": all(
            surfaces[column].notna().all()
            for column in (
                "iv30_method",
                "iv60_method",
                "iv90_method",
                "atm_iv30_method",
                "iv_25d_put30_method",
                "iv_25d_call30_method",
            )
        ),
        "five_event_ledgers_present": set(ledger["event_id"].unique()) == set(EVENT_IDS),
        "formal_g0_passed": False,
    }
    return {
        "acceptance_kind": "REAL_DATA_RESEARCH",
        "overall_status": "PASS_RESEARCH_ONLY_FORMAL_BLOCKED"
        if all(value for key, value in checks.items() if key != "formal_g0_passed")
        else "FAIL",
        "revision_id": revision_id,
        "source": extraction_metadata(extraction),
        "checks": checks,
        "coverage": coverage_records,
        "probability": probability_records,
        "formal_gates": {
            "G0": "NOT_PASSED",
            "reason": "No authorized PIT synchronized bid/ask history or licence evidence is present.",
            "G1_G6": "NOT_CLAIMED",
        },
    }


def _write_acceptance_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# MatSHIX 真实数据验收报告",
        "",
        f"- 结论：`{payload['overall_status']}`",
        f"- 证据层：`{payload['acceptance_kind']}`",
        f"- Revision：`{payload['revision_id']}`",
        "- 正式 G0：`NOT_PASSED`（缺授权 PIT 同步 bid/ask 与许可凭证）",
        "",
        "## 业务链检查",
        "",
    ]
    for key, value in payload["checks"].items():
        lines.append(f"- `{key}`：`{value}`")
    lines.extend(["", "## Carrier × Year 覆盖", ""])
    lines.append(
        "| Carrier | Year | Sessions | Valid | IV30 exact/ref | IV90 exact/ref | "
        "25D Put exact/ref | 25D Call exact/ref |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["coverage"]:
        lines.append(
            "| {carrier_id} | {year} | {sessions} | {valid_surface_share:.1%} | "
            "{iv30_bracket_share:.1%}/{iv30_reference_share:.1%} | "
            "{iv90_bracket_share:.1%}/{iv90_reference_share:.1%} | "
            "{put25_bracket_share:.1%}/{put25_reference_share:.1%} | "
            "{call25_bracket_share:.1%}/{call25_reference_share:.1%} |".format(**row)
        )
    lines.extend(["", "## 五事件样本与模型状态", ""])
    lines.append("| Event | Eligible | Observed | Positive | Model accepted | Reason |")
    lines.append("|---|---:|---:|---:|---|---|")
    for row in payload["probability"]:
        acceptance = row["model_acceptance"]
        lines.append(
            f"| {row['event_id']} | {row['eligible']} | {row['observed']} | "
            f"{row['positives']} | {acceptance.get('accepted', False)} | "
            f"{acceptance.get('reason', '')} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本报告使用真实 AETF 14:56 分钟收盘数据完成研究链验收。分钟收盘不是双边盘口，"
            "无法报告真实 relative spread，也不得升级为正式 G0–G6 验收。概率模型未通过时，"
            "产品只展示同类历史 BaseRate 或 INSUFFICIENT_HISTORY，不制造特征概率。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_research_project(
    *,
    aetf_root: Path,
    project_dir: Path,
    start: str | None = None,
    end: str | None = None,
    progress: Progress | None = None,
) -> BuildResult:
    project = project_dir.expanduser().resolve()
    model_config, _source_config, config_hash, source_manifest_hash = _configuration(project)
    engine_artifact_hash = compute_engine_artifact_hash(project)
    if progress is not None:
        progress("读取四载体真实 AETF 14:56 分钟收盘数据")
    extraction = extract_history(AetfPaths.from_root(aetf_root), start=start, end=end)
    processed = project / "data/processed/research"
    option_path = write_parquet(extraction.option_prices, processed / "option_observation.parquet")
    mark_path = write_parquet(extraction.etf_marks, processed / "etf_mark.parquet")
    input_hash = content_hash(
        {
            "option_observation": file_hash(option_path),
            "etf_mark": file_hash(mark_path),
            "metadata": extraction_metadata(extraction),
        }
    )
    revision_id = content_hash(
        {
            "input_hash": input_hash,
            "config_hash": config_hash,
            "source": source_manifest_hash,
            "engine_artifact_hash": engine_artifact_hash,
        }
    )
    surface_config = model_config["surface"]
    surfaces, expiry_surfaces = build_surface_history(
        extraction,
        minimum_total_strikes=int(surface_config["research_minimum_total_strikes"]),
        include_identifiable_adjusted_contracts=bool(
            surface_config["research_include_identifiable_adjusted_contracts"]
        ),
        nearest_tenor_max_distance_days={
            int(key): int(value)
            for key, value in surface_config["research_nearest_tenor_max_distance_days"].items()
        },
        nearest_delta_max_distance=float(surface_config["research_nearest_delta_max_distance"]),
        nearest_atm_log_moneyness=float(surface_config["research_nearest_atm_log_moneyness"]),
        progress=progress,
    )
    coverage = coverage_table(surfaces)
    if progress is not None:
        progress("计算连续交易日特征、七坐标、答案与唯一 phase")
    features = build_index_feature_history(
        surfaces,
        extraction.etf_marks,
        reference_sessions=int(model_config["reference_sessions"]),
        minimum_valid=int(model_config["research_minimum_percentile_history"]),
        vov_max_span_sessions=int(model_config["research_iv_vov_max_span_sessions"]),
    )
    scored = build_market_score_history(
        features,
        reference_sessions=int(model_config["reference_sessions"]),
        minimum_valid=int(model_config["research_minimum_percentile_history"]),
    )
    ontology = add_state_ontology(scored)
    state = apply_phase_hysteresis(ontology, config_hash=config_hash)
    state = add_probability_predictors(state)
    state["prediction_position"] = range(len(state))
    if state.empty:
        raise RuntimeError("no complete four-index state sessions were produced")
    if progress is not None:
        progress("构建五事件 target ledger、顺序 OOF、校准与发布真值")
    ledger, oof, metrics, accepted = _probability_outputs(state)
    probability_config = model_config["probability"]
    state, probability_history, judgments_by_date = _add_outlooks(
        state,
        ledger,
        accepted_latest=accepted,
        base_rate_minimum_samples=int(probability_config["research_base_rate_minimum_samples"]),
        base_rate_maximum_samples=int(probability_config["base_rate_maximum_samples"]),
    )
    common_columns = {
        "revision_id": revision_id,
        "config_hash": config_hash,
        "source_manifest_hash": source_manifest_hash,
        "input_hash": input_hash,
        "engine_artifact_hash": engine_artifact_hash,
        "vintage_kind": "PROVIDER_RECONSTRUCTED",
    }
    _attach_table_contract(
        surfaces,
        version_field="surface_version",
        version=str(model_config["surface_version"]),
        common_columns=common_columns,
    )
    _attach_table_contract(
        expiry_surfaces,
        version_field="surface_version",
        version=str(model_config["surface_version"]),
        common_columns=common_columns,
    )
    _attach_table_contract(
        features,
        version_field="feature_version",
        version=str(model_config["feature_version"]),
        common_columns=common_columns,
    )
    _attach_table_contract(
        ledger,
        version_field="probability_version",
        version=str(model_config["probability_version"]),
        common_columns=common_columns,
    )
    _attach_table_contract(
        probability_history,
        version_field="probability_version",
        version=str(model_config["probability_version"]),
        common_columns=common_columns,
    )
    states_flat = flatten_market_states(state)
    index_states_flat = flatten_economic_index_states(state)
    _attach_table_contract(
        states_flat,
        version_field="state_version",
        version=str(model_config["state_version"]),
        common_columns=common_columns,
    )
    _attach_table_contract(
        index_states_flat,
        version_field="state_version",
        version=str(model_config["state_version"]),
        common_columns=common_columns,
    )
    issues = _issue_ledger(surfaces, expiry_surfaces)
    _attach_table_contract(
        issues,
        version_field="surface_version",
        version=str(model_config["surface_version"]),
        common_columns=common_columns,
    )
    write_parquet(surfaces, processed / "carrier_surface.parquet")
    write_parquet(expiry_surfaces, processed / "carrier_expiry_surface.parquet")
    write_parquet(features, processed / "economic_index_feature.parquet")
    write_parquet(index_states_flat, processed / "economic_index_state.parquet")
    write_parquet(states_flat, processed / "daily_market_state.parquet")
    write_parquet(ledger, processed / "target_ledger.parquet")
    write_parquet(probability_history, processed / "event_probability.parquet")
    write_parquet(issues, processed / "issue_ledger.parquet")
    if not oof.empty:
        for column, value in common_columns.items():
            oof[column] = value
        write_parquet(oof, processed / "oof_probability.parquet")
    write_parquet(coverage, processed / "coverage.parquet")
    if progress is not None:
        progress("生成逐日 JSON、正式 UNKNOWN 对照与 Dashboard 数据")
    snapshots_dir = project / "outputs/research/daily"
    coverage_summary = coverage.to_dict(orient="records")
    dashboard_days: list[dict[str, Any]] = []
    market_evidence_rows: list[dict[str, Any]] = []
    state_records = state.sort_values("session_date").to_dict(orient="records")
    latest_snapshot: dict[str, Any] | None = None
    for record in state_records:
        session = pd.Timestamp(record["session_date"]).normalize()
        session_key = session.date().isoformat()
        index_rows = _index_rows_for_session(features, session)
        snapshot = build_research_snapshot(
            state=record,
            index_rows=index_rows,
            judgments=judgments_by_date[session_key],
            source_manifest_hash=source_manifest_hash,
            config_hash=config_hash,
            input_hash=input_hash,
            engine_artifact_hash=engine_artifact_hash,
            revision_id=revision_id,
            coverage_summary=coverage_summary,
        )
        write_json(snapshots_dir / f"{session_key}.json", snapshot)
        evidence = rank_evidence(index_rows)
        dashboard_days.append(
            {
                "session_date": session_key,
                "primary_phase": snapshot["primary_phase"],
                "pressure_score": snapshot["pressure_score"],
                "pressure_level": snapshot["pressure_level"],
                "direction": snapshot["direction"],
                "confidence": snapshot["confidence"],
                "headline": snapshot["narrative"]["headline"],
                "answers": snapshot["answers"],
                "scores": snapshot["scores"],
                "breadth": snapshot["breadth"],
                "economic_indices": snapshot["economic_indices"],
                "probabilities": snapshot["probabilities"],
                "drivers": evidence["drivers"],
                "counter_evidence": evidence["counter_evidence"],
                "repair_evidence": evidence["repair_evidence"],
                "research_proxies": snapshot["narrative"]["research_proxies"],
                "what_changes_the_view": snapshot["narrative"]["what_changes_the_view"],
            }
        )
        for evidence_kind, values in (
            ("DRIVER", snapshot["narrative"]["drivers"]),
            ("COUNTER", snapshot["narrative"]["counter_evidence"]),
            ("REPAIR", snapshot["narrative"]["repair_evidence"]),
        ):
            for rank, value in enumerate(values, start=1):
                market_evidence_rows.append(
                    {
                        "session_date": session,
                        "evidence_kind": evidence_kind,
                        "evidence_rank": rank,
                        **value,
                    }
                )
        latest_snapshot = snapshot
    assert latest_snapshot is not None
    latest_path = project / "outputs/research/latest.json"
    write_json(latest_path, latest_snapshot)
    dashboard_path = project / "outputs/research/dashboard_data.json"
    write_json(
        dashboard_path,
        {
            "revision_id": revision_id,
            "evidence_tier": "RESEARCH_ONLY",
            "days": dashboard_days,
            "coverage": coverage_summary,
            "model_acceptance": metrics,
        },
    )
    market_evidence = pd.DataFrame(market_evidence_rows)
    _attach_table_contract(
        market_evidence,
        version_field="state_version",
        version=str(model_config["state_version"]),
        common_columns=common_columns,
    )
    write_parquet(market_evidence, processed / "market_evidence.parquet")
    formal_path = project / "outputs/formal/latest.json"
    formal = formal_unknown_snapshot(
        session_date=extraction.end_session,
        source_manifest_hash=source_manifest_hash,
        config_hash=config_hash,
        engine_artifact_hash=engine_artifact_hash,
        blockers=latest_snapshot["data_quality"]["formal_blockers"],
    )
    write_json(formal_path, formal)
    acceptance = _acceptance_payload(
        extraction=extraction,
        surfaces=surfaces,
        states=state,
        ledger=ledger,
        probability_history=probability_history,
        metrics=metrics,
        coverage=coverage,
        revision_id=revision_id,
    )
    acceptance_json = project / "outputs/acceptance/real_data_research.json"
    acceptance_md = project / "outputs/acceptance/REAL_DATA_RESEARCH_ACCEPTANCE.md"
    write_json(acceptance_json, acceptance)
    _write_acceptance_markdown(acceptance_md, acceptance)
    result = BuildResult(
        project_dir=str(project),
        start_session=extraction.start_session,
        end_session=extraction.end_session,
        extracted_sessions=extraction.session_count,
        state_sessions=len(state),
        latest_snapshot=str(latest_path),
        formal_snapshot=str(formal_path),
        acceptance_report=str(acceptance_md),
        dashboard_input=str(dashboard_path),
        engine_artifact_hash=engine_artifact_hash,
        revision_id=revision_id,
    )
    write_json(project / "outputs/build_result.json", asdict(result))
    return result
