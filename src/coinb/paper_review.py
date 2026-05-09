from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .jsonl import ensure_parent


def build_paper_review(
    loss_analysis_path: str = "reports/orderflow_loss_analysis.json",
    output_path: str = "reports/paper_review_latest.txt",
) -> Dict[str, Any]:
    if not os.path.exists(loss_analysis_path):
        raise FileNotFoundError(f"Loss analysis report not found: {loss_analysis_path}")

    with open(loss_analysis_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    summary = report.get("summary", {})
    decision_count = summary.get("decision_count", 0)
    trade_count = summary.get("trade_count", 0)

    reason_summary = report.get("reason_summary", {})
    blocked_candidates = report.get("blocked_candidates", {})

    lines: List[str] = []
    lines.append("=" * 50)
    lines.append(" PAPER LOOP AUTOMATIC REVIEW SUMMARY")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"1. OVERVIEW")
    lines.append(f"   - Total Decisions : {decision_count}")
    lines.append(f"   - Total Trades    : {trade_count}")
    lines.append("")
    
    lines.append("2. TOP REJECTION REASONS")
    sorted_reasons = sorted(
        reason_summary.values(),
        key=lambda x: x.get("count", 0),
        reverse=True
    )
    
    top_reasons_info = []
    
    for r in sorted_reasons[:5]:
        reason = r.get("reason", "UNKNOWN")
        count = r.get("count", 0)
        pct = (count / decision_count * 100) if decision_count > 0 else 0
        top_reasons_info.append({"reason": reason, "count": count, "pct": pct})
        lines.append(f"   - {reason}: {count} ({pct:.1f}%)")
        
        diagnostics = r.get("diagnostics_sample", [])
        if diagnostics:
            lines.append("     [Diagnostic Samples]")
            for i, diag in enumerate(diagnostics[:3]):
                field = diag.get("checked_field", "")
                actual = diag.get("actual_value", 0)
                req = diag.get("required_value", 0)
                gap_pct = diag.get("gap_pct", 0)
                lines.append(f"       {i+1}) {field} -> Actual: {actual}, Req: {req}, Gap: {gap_pct}%")
    lines.append("")

    lines.append("3. BLOCKED CANDIDATES SUMMARY")
    blocked_markets = blocked_candidates.get("markets", [])
    blocked_reasons = blocked_candidates.get("reasons", [])
    
    if blocked_markets:
        lines.append("   - Blocked Markets:")
        for m in blocked_markets:
            market = m.get("market", "")
            reasons = ", ".join(m.get("reasons", []))
            lines.append(f"     {market} ({reasons})")
    else:
        lines.append("   - Blocked Markets: None")
        
    if blocked_reasons:
        lines.append("   - Blocked Reasons (High Frequency):")
        for br in blocked_reasons:
            lines.append(f"     {br.get('reason')} (Count: {br.get('count')})")
    else:
        lines.append("   - Blocked Reasons: None")
    lines.append("")

    lines.append("4. NEXT ACTION SUGGESTIONS")
    suggestions = []
    
    if trade_count == 0 and decision_count > 0:
        suggestions.append("- [조건 완화] trade_count가 0입니다. 진입 조건(OFI, Sweep, 연속성 점수) 완화 검토가 필요합니다.")
        
    for info in top_reasons_info:
        r_name = info["reason"]
        r_pct = info["pct"]
        
        if "SPREAD_TOO_WIDE" in r_name and r_pct > 20:
            suggestions.append(f"- [스프레드 조정] SPREAD_TOO_WIDE 비중이 높습니다({r_pct:.1f}%). 특정 코인 스프레드 문제일 수 있으므로 해당 코인 제외나 스프레드 기준 상향 검토 후보입니다.")
        elif ("LOW_VOLUME" in r_name or "LOW_IMBALANCE" in r_name) and r_pct > 30:
            suggestions.append(f"- [유동성 기준 완화] {r_name} 비중이 높습니다({r_pct:.1f}%). 해당 기준(min_trade_value_3s 등)이 현재 시장과 맞지 않을 수 있어 재검토/조정할 후보입니다.")

    if not suggestions:
        suggestions.append("- 특이사항 없음. 데이터 수집을 지속하거나 실거래 기준 분석 진행 가능합니다.")

    for s in suggestions:
        lines.append(f"   {s}")
        
    lines.append("")
    lines.append("=" * 50)
    
    content = "\n".join(lines)
    
    ensure_parent(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return {
        "ok": True,
        "command": "paper-review",
        "output_path": output_path,
        "decision_count": decision_count,
        "trade_count": trade_count,
    }
