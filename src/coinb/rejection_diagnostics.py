import json
import os
from collections import defaultdict
from typing import Any, Dict, List
from . import report_io

def build_rejection_diagnostics(decisions_path: str, output_json_path: str, output_txt_path: str):
    if not os.path.exists(decisions_path):
        empty = {"decision_count": 0, "buy_count": 0, "no_buy_count": 0, "reasons": {}}
        report_io.write_json_report(output_json_path, empty)
        report_io.write_text_report(output_txt_path, "판단 데이터가 없습니다.")
        return

    decision_count, buy_count, no_buy_count = 0, 0, 0
    reasons = defaultdict(int)
    diag_data = defaultdict(lambda: {"count": 0, "gap_sum": 0.0, "gap_pct_sum": 0.0, "markets": defaultdict(lambda: {"count": 0, "gap_pct_sum": 0.0})})

    with open(decisions_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                decision_count += 1
                market, action, reason = data.get("market", "UKN"), data.get("action", "UKN"), data.get("reason", "NONE")
                if action == "BUY": buy_count += 1
                else:
                    no_buy_count += 1
                    reasons[reason] += 1
                    diag = data.get("diagnostic")
                    if diag and isinstance(diag, dict):
                        gap, gap_pct = float(diag.get("gap", 0)), float(diag.get("gap_pct", 0))
                        diag_data[reason]["count"] += 1
                        diag_data[reason]["gap_sum"] += gap
                        diag_data[reason]["gap_pct_sum"] += gap_pct
                        diag_data[reason]["markets"][market]["count"] += 1
                        diag_data[reason]["markets"][market]["gap_pct_sum"] += gap_pct
            except: continue

    report = {"decision_count": decision_count, "buy_count": buy_count, "no_buy_count": no_buy_count, "reasons": dict(reasons), "diagnostics": {}}
    for reason, data in diag_data.items():
        if data["count"] > 0:
            report["diagnostics"][reason] = {"count": data["count"], "avg_gap": round(data["gap_sum"] / data["count"], 6), "avg_gap_pct": round(data["gap_pct_sum"] / data["count"], 2)}

    report_io.write_json_report(output_json_path, report)

    lines = []
    lines.append("=== Orderflow 진입 거절 상세 진단 리포트 ===")
    lines.append(f"총 판단 횟수: {decision_count} | 매수 진입: {buy_count} | 진입 거절: {no_buy_count}")
    if decision_count > 0: lines.append(f"진입 성공률: {buy_count/decision_count*100:.2f}%")
    lines.append("\n--- 거절 사유별 통계 ---")
    for r, c in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {r}: {c}건 ({c/no_buy_count*100 if no_buy_count > 0 else 0:.2f}%)")
    lines.append("\n--- 상세 진단 ---")
    for r in ["LOW_VOLUME", "LOW_IMBALANCE", "SPREAD_TOO_WIDE"]:
        if r in report["diagnostics"]:
            d = report["diagnostics"][r]
            lines.append(f"[{r}] 횟수: {d['count']} | 평균 차이(Gap): {d['avg_gap']:.6f} ({d['avg_gap_pct']}%)")
    lines.append("\n(본 리포트는 진단용이며, 설정값 변경은 수동 검토 후 진행하십시오.)")
    report_io.write_text_report(output_txt_path, "\n".join(lines))

def run_rejection_diagnostics(decisions_path: str = "logs/orderflow_paper_decisions.jsonl", output_json_path: str = "reports/rejection_diagnostics.json", output_txt_path: str = "reports/rejection_diagnostics_summary.txt") -> Dict[str, Any]:
    build_rejection_diagnostics(decisions_path, output_json_path, output_txt_path)
    return {"ok": True, "output_json": output_json_path, "output_txt": output_txt_path}
