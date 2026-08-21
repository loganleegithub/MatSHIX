from __future__ import annotations

from typing import Any

import pandas as pd

from matshix.constants import ECONOMIC_WEIGHTS, INDEX_ORDER

HEADLINES = {
    "SYSTEMIC_ACUTE_STRESS": "大盘、中盘与科创期权同步进入急性保险重定价。",
    "LOCALIZED_ACUTE_STRESS": "急性重定价已出现，但尚未获得三段同步急性跳升确认。",
    "REPAIR_IN_PROGRESS": "高压后的边际修复得到多项证据确认。",
    "BROAD_PERSISTENT_PRESSURE": "压力已跨风险段扩散并进入持续层。",
    "BROAD_PRESSURE": "多个风险段的保险价格正在同步承压。",
    "LOCAL_STYLE_PRESSURE": "中盘或科创成长保险价格显著承压，大盘尚未完全确认。",
    "BLUE_CHIP_PRESSURE": "大盘权重相关保险价格显著承压，中盘与科创尚未完全确认。",
    "DOWNSIDE_TAIL_RICH": "总体冲击尚不高，但下行尾部相对中心明显偏贵。",
    "UPSIDE_CONVEXITY_PRICED": "上行凸性相对突出，当前更像认购侧事件定价。",
    "CALM_POSITIVE_VRP": "多数风险段平稳，保险价格相对事前实现方差仍有正补偿。",
    "FRAGMENTED_TRANSITION": "经济指数或期限证据分化，市场处于过渡状态。",
    "BALANCED_MARKET": "当前没有急性、广泛或显著尾部主导证据，市场处于相对均衡状态。",
}

AXIS_WEIGHTS = {
    "InsuranceLevel": 0.20,
    "Shock": 0.25,
    "DownTail": 0.20,
    "Persistence": 0.15,
    "UpTail": 0.20,
}
COMPONENTS: dict[str, tuple[tuple[str, str, float, str, str], ...]] = {
    "InsuranceLevel": (("iv30_level", "p_iv30", 1.00, "iv30_mf", "percent_iv"),),
    "Shock": (
        ("iv30_change_1d", "p_d1_log_iv30", 0.35, "d1_log_iv30", "log_return"),
        ("iv30_change_5d", "p_d5_log_iv30", 0.25, "d5_log_iv30", "log_return"),
        ("iv_vol_of_vol20", "p_iv_vol_of_vol20", 0.20, "iv_vol_of_vol20", "annualized"),
        ("negative_etf_return_1d", "p_neg_etf_return_1d", 0.20, "etf_return_1d", "log_return"),
    ),
    "DownTail": (
        ("down_skew25", "p_down_skew25", 0.65, "down_skew25", "iv_points"),
        ("down_skew25_change_5d", "p_d5_down_skew25", 0.35, "d5_down_skew25", "iv_points"),
    ),
    "UpTail": (
        ("up_skew25", "p_up_skew25", 0.65, "up_skew25", "iv_points"),
        ("up_skew25_change_5d", "p_d5_up_skew25", 0.35, "d5_up_skew25", "iv_points"),
    ),
    "Persistence": (
        ("forward_vol_30_90", "p_fvol_30_90", 0.40, "fvol_30_90", "percent_iv"),
        ("iv90_level", "p_iv90", 0.25, "iv90_mf", "percent_iv"),
        ("forward_vol_change_5d", "p_d5_fvol_30_90", 0.20, "d5_fvol_30_90", "iv_points"),
        ("term_log_ratio", "p_term_log_ratio_30_90", 0.15, "term_log_ratio_30_90", "log_ratio"),
    ),
    "Repair": (
        ("iv30_fall_5d", "p_neg_d5_log_iv30", 0.30, "d5_log_iv30", "log_return"),
        ("down_skew_fall_5d", "p_neg_d5_down_skew25", 0.25, "d5_down_skew25", "iv_points"),
        ("forward_vol_fall_5d", "p_neg_d5_fvol_30_90", 0.20, "d5_fvol_30_90", "iv_points"),
        ("etf_rebound_5d", "p_etf_return_5d", 0.15, "etf_return_5d", "log_return"),
        (
            "iv_vov_fall_5d",
            "p_neg_d5_iv_vol_of_vol20",
            0.10,
            "d5_iv_vol_of_vol20",
            "annualized_change",
        ),
    ),
}
MEANINGS = {
    "iv30_level": "30日保险价格处于自身历史高分位",
    "iv30_change_1d": "30日隐含波动率单日重定价处于自身历史高分位",
    "iv30_change_5d": "30日隐含波动率五日重定价处于自身历史高分位",
    "iv_vol_of_vol20": "隐含波动率自身不稳定度处于历史高分位",
    "negative_etf_return_1d": "同步ETF下行变化处于历史高分位",
    "down_skew25": "25D下行保险参考相对中心偏贵程度处于历史高分位",
    "down_skew25_change_5d": "25D下行尾翼参考五日变贵速度处于历史高分位",
    "up_skew25": "25D上行凸性参考相对中心偏贵程度处于历史高分位",
    "up_skew25_change_5d": "25D上行尾翼参考五日变贵速度处于历史高分位",
    "forward_vol_30_90": "30至90日远期波动处于历史高分位",
    "iv90_level": "90日保险价格处于历史高分位",
    "forward_vol_change_5d": "中期波动五日扩散速度处于历史高分位",
    "term_log_ratio": "近端相对中期的期限结构处于历史高分位",
    "iv30_fall_5d": "30日隐含波动率五日回落处于修复方向高分位",
    "down_skew_fall_5d": "下行尾翼五日回落处于修复方向高分位",
    "forward_vol_fall_5d": "中期远期波动五日回落处于修复方向高分位",
    "etf_rebound_5d": "ETF五日反弹处于修复方向高分位",
    "iv_vov_fall_5d": "隐含波动不稳定度五日回落处于修复方向高分位",
}


def _number(row: dict[str, Any], field: str) -> float | None:
    value = row.get(field)
    return None if value is None or pd.isna(value) else float(value)


def rank_evidence(index_rows: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    risk: list[dict[str, Any]] = []
    repair: list[dict[str, Any]] = []
    order = 0
    for index in INDEX_ORDER:
        row = index_rows[index]
        for axis in ("InsuranceLevel", "Shock", "DownTail", "Persistence", "UpTail", "Repair"):
            for component, percentile_field, within_weight, raw_field, unit in COMPONENTS[axis]:
                percentile = _number(row, percentile_field)
                raw = _number(row, raw_field)
                tie_order = order
                order += 1
                if percentile is None:
                    continue
                axis_weight = 1.0 if axis == "Repair" else AXIS_WEIGHTS[axis]
                contribution = (
                    ECONOMIC_WEIGHTS[index] * axis_weight * within_weight * (percentile - 0.5)
                )
                record = {
                    "evidence_id": f"{index.lower()}.{axis.lower()}.{component}",
                    "identity": "DERIVED",
                    "carrier_or_index": index,
                    "raw_value": raw,
                    "unit": unit,
                    "percentile": percentile,
                    "contribution": round(contribution, 6),
                    "meaning": f"{index}的{MEANINGS[component]}",
                    "_order": tie_order,
                }
                (repair if axis == "Repair" else risk).append(record)
    drivers = sorted(
        [value for value in risk if value["percentile"] >= 0.75],
        key=lambda value: (-float(value["contribution"]), int(value["_order"])),
    )[:3]
    counter = sorted(
        [value for value in risk if value["percentile"] <= 0.35],
        key=lambda value: (float(value["contribution"]), int(value["_order"])),
    )[:2]
    repairs = sorted(
        [value for value in repair if value["percentile"] >= 0.75],
        key=lambda value: (-float(value["contribution"]), int(value["_order"])),
    )[:3]
    for values in (drivers, counter, repairs):
        for value in values:
            value.pop("_order", None)
    return {"drivers": drivers, "counter_evidence": counter, "repair_evidence": repairs}


def structural_triggers(state: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if state.get("hard_acute") is True:
        output.append({"trigger_id": "hard_acute", "identity": "DERIVED", "value": True})
    for segment, value in state.get("breadth_metrics", {}).get("segment_stressed", {}).items():
        if value is True:
            output.append(
                {"trigger_id": f"segment_stressed.{segment}", "identity": "DERIVED", "value": True}
            )
    tail = state.get("answers", {}).get("tail")
    if tail not in {None, "UNKNOWN", "NEUTRAL", "MIXED"}:
        output.append({"trigger_id": "tail_side", "identity": "DERIVED", "value": tail})
    return output


def headline(state: dict[str, Any]) -> str:
    if state.get("data_status") != "OK":
        return "今日研究曲面不足，暂不形成完整上交所期权市场天气。"
    phase = str(state.get("primary_phase"))
    if phase == "UNKNOWN":
        return "今日研究曲面完整，但关键历史基线或状态谓词仍不可判，暂不发布市场天气分类。"
    return HEADLINES[phase]


def what_changes_the_view(state: dict[str, Any]) -> list[str]:
    phase = state.get("primary_phase")
    if phase in {"SYSTEMIC_ACUTE_STRESS", "LOCALIZED_ACUTE_STRESS"}:
        return [
            "hard_acute释放且Shock回落到75以下",
            "随后连续两个完整研究交易日出现同一非急性raw phase",
        ]
    if phase == "REPAIR_IN_PROGRESS":
        return ["Repair不再满足确认条件，或Pressure/Breadth重新上升", "hard_acute重新成立"]
    if phase == "BROAD_PERSISTENT_PRESSURE":
        return ["persistent_now或broad_confirmed不再成立", "新的更高优先级phase成立"]
    if phase == "UNKNOWN":
        return ["恢复四载体曲面与所需历史基线后顺序重放"]
    return ["更高优先级phase成立，或新普通raw phase连续两个完整研究交易日确认"]


def build_narrative(
    state: dict[str, Any],
    evidence: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    answers = state["answers"]
    drivers = "；".join(value["meaning"] for value in evidence["drivers"])
    if not drivers:
        drivers = "当前没有单项风险贡献超过75%历史分位"
    counter = "；".join(value["meaning"] for value in evidence["counter_evidence"])
    repair = "；".join(value["meaning"] for value in evidence["repair_evidence"])
    if not repair:
        repair = "暂无高分位修复证据"
    lines = [
        headline(state),
        f"保险价格：{answers['level']}。",
        f"重定价与期限：Shock={answers['shock']}，Term={answers['term']}。",
        f"尾部与宽度：Tail={answers['tail']}，Breadth={answers['breadth']}。",
        f"修复：{answers['repair']}；{repair}。",
        f"主要驱动：{drivers}。",
    ]
    if counter:
        lines.append(f"反向证据：{counter}。")
    lines.extend(
        [
            f"未来判断：{answers.get('outlook', 'UNKNOWN')}。",
            f"判断改变条件：{'；'.join(what_changes_the_view(state))}。",
            "数据边界：真实14:56分钟收盘研究曲面；不是同步bid/ask，也不是正式可成交盘口。",
        ]
    )
    return {
        "headline": headline(state),
        "drivers": evidence["drivers"],
        "counter_evidence": evidence["counter_evidence"],
        "repair_evidence": evidence["repair_evidence"],
        "structural_triggers": structural_triggers(state),
        "what_changes_the_view": what_changes_the_view(state),
        "narrative": "\n".join(lines),
    }
