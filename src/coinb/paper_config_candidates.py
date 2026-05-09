from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .jsonl import ensure_parent


def build_paper_config_candidates(
    decisions_path: str,
    loss_analysis_path: str,
    output_json_path: str,
    output_txt_path: str,
) -> Dict[str, Any]:
    if not os.path.exists(loss_analysis_path):
        raise FileNotFoundError(f"Loss analysis not found: {loss_analysis_path}")

    with open(loss_analysis_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    summary = report.get("summary", {})
    trade_count = summary.get("trade_count", 0)
    decision_count = summary.get("decision_count", 0)
    reason_summary = report.get("reason_summary", {})

    candidates: Dict[str, Any] = {
        "risk_note": "실제 승률/손익 검증 전이므로 config 자동 반영 금지" if trade_count == 0 else "자동 반영을 권장하지 않습니다. 반드시 수동 검토 후 반영하세요.",
        "candidates": [],
    }

    lines = []
    lines.append("=" * 50)
    lines.append(" PAPER CONFIG CANDIDATES SUMMARY")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"RISK NOTE: {candidates['risk_note']}")
    lines.append("")

    if decision_count == 0:
        lines.append("데이터가 부족하여 후보를 생성할 수 없습니다.")
        _write_outputs(output_json_path, output_txt_path, candidates, lines)
        return {"ok": True, "command": "paper-config-candidates", "output_json": output_json_path, "output_txt": output_txt_path}

    for key, info in reason_summary.items():
        action = info.get("action", "")
        reason = info.get("reason", "")
        if action != "NO_BUY":
            continue

        diagnostics = info.get("diagnostics_sample", [])
        if not diagnostics:
            continue

        # Get average required and actual to formulate suggestions
        reqs = [d.get("required_value", 0) for d in diagnostics if d.get("required_value") is not None]
        acts = [d.get("actual_value", 0) for d in diagnostics if d.get("actual_value") is not None]

        if not reqs or not acts:
            continue

        req_avg = sum(reqs) / len(reqs)
        act_avg = sum(acts) / len(acts)

        suggestion = None

        if reason == "LOW_VOLUME":
            suggestion = {
                "reason": reason,
                "target_config": "microstructure.min_trade_value_3s",
                "current_avg_req": req_avg,
                "current_avg_act": act_avg,
                "conservative": req_avg * 0.8,
                "moderate": req_avg * 0.5,
                "aggressive": req_avg * 0.2,
                "note": "LOW_VOLUME 거절이 많아 min_trade_value_3s 하향 제안",
            }
        elif reason == "SPREAD_TOO_WIDE":
            markets = info.get("markets", {})
            top_market = max(markets, key=markets.get) if markets else "ALL"
            suggestion = {
                "reason": reason,
                "target_config": "microstructure.max_spread_pct",
                "current_avg_req": req_avg,
                "current_avg_act": act_avg,
                "conservative": req_avg * 1.1,
                "moderate": req_avg * 1.3,
                "aggressive": req_avg * 1.5,
                "note": f"SPREAD_TOO_WIDE 거절이 많음 (특히 {top_market} 마켓). 기준 상향 또는 해당 마켓 제외 제안",
            }
        elif reason == "LOW_IMBALANCE":
            suggestion = {
                "reason": reason,
                "target_config": "microstructure.bid_ask_depth_ratio_min",
                "current_avg_req": req_avg,
                "current_avg_act": act_avg,
                "conservative": req_avg * 0.9,
                "moderate": req_avg * 0.7,
                "aggressive": req_avg * 0.5,
                "note": "LOW_IMBALANCE 거절이 많아 bid_ask_depth_ratio_min 하향 제안",
            }
        elif reason == "LOW_MOMENTUM":
            suggestion = {
                "reason": reason,
                "target_config": "microstructure.continuation_score_min (or sweep/ofi)",
                "current_avg_req": req_avg,
                "current_avg_act": act_avg,
                "conservative": req_avg * 0.9,
                "moderate": req_avg * 0.8,
                "aggressive": req_avg * 0.7,
                "note": "LOW_MOMENTUM 거절이 많아 모멘텀 점수 기준 하향 제안",
            }

        if suggestion:
            candidates["candidates"].append(suggestion)
            lines.append(f"[{reason}]")
            lines.append(f"  - Target Config: {suggestion['target_config']}")
            lines.append(f"  - Note: {suggestion['note']}")
            lines.append(f"  - Conservative: {suggestion['conservative']:.4f}")
            lines.append(f"  - Moderate    : {suggestion['moderate']:.4f}")
            lines.append(f"  - Aggressive  : {suggestion['aggressive']:.4f}")
            lines.append("")

    if not candidates["candidates"]:
        lines.append("조정 후보를 생성할 충분한 진단 데이터가 없습니다.")

    lines.append("=" * 50)

    _write_outputs(output_json_path, output_txt_path, candidates, lines)

    return {
        "ok": True,
        "command": "paper-config-candidates",
        "output_json": output_json_path,
        "output_txt": output_txt_path,
        "candidates_count": len(candidates["candidates"]),
    }


def _write_outputs(json_path: str, txt_path: str, json_data: Dict[str, Any], txt_lines: List[str]) -> None:
    ensure_parent(json_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    ensure_parent(txt_path)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))
