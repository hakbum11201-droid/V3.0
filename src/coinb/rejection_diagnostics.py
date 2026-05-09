import json
import os
from collections import defaultdict
from typing import Any, Dict, List

def build_rejection_diagnostics(
    decisions_path: str,
    output_json_path: str,
    output_txt_path: str
):
    if not os.path.exists(decisions_path):
        print(f"Warning: Decisions file not found at {decisions_path}")
        # Create empty report
        empty_report = {
            "decision_count": 0,
            "buy_count": 0,
            "no_buy_count": 0,
            "reasons": {},
            "markets": {},
            "diagnostics": {}
        }
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(empty_report, f, indent=2)
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write("판단 데이터가 없습니다.\n")
        return

    decision_count = 0
    buy_count = 0
    no_buy_count = 0
    
    reasons = defaultdict(int)
    market_reasons = defaultdict(lambda: defaultdict(int))
    
    # Diagnostic aggregators: reason -> list of values
    diag_data = defaultdict(lambda: {
        "count": 0,
        "actual_sum": 0.0,
        "required_sum": 0.0,
        "gap_sum": 0.0,
        "gap_pct_sum": 0.0,
        "markets": defaultdict(lambda: {
            "count": 0,
            "actual_sum": 0.0,
            "required_sum": 0.0,
            "gap_sum": 0.0,
            "gap_pct_sum": 0.0
        })
    })

    with open(decisions_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                decision_count += 1
                
                market = data.get("market", "UNKNOWN")
                action = data.get("action", "UNKNOWN")
                reason = data.get("reason", "NONE")
                
                if action == "BUY":
                    buy_count += 1
                else:
                    no_buy_count += 1
                    reasons[reason] += 1
                    market_reasons[market][reason] += 1
                    
                    diag = data.get("diagnostic")
                    if diag and isinstance(diag, dict):
                        # Use reason as key for diagnostic grouping
                        d_key = reason
                        
                        actual = float(diag.get("actual_value", 0))
                        required = float(diag.get("required_value", 0))
                        gap = float(diag.get("gap", 0))
                        gap_pct = float(diag.get("gap_pct", 0))
                        
                        # Global reason stats
                        diag_data[d_key]["count"] += 1
                        diag_data[d_key]["actual_sum"] += actual
                        diag_data[d_key]["required_sum"] += required
                        diag_data[d_key]["gap_sum"] += gap
                        diag_data[d_key]["gap_pct_sum"] += gap_pct
                        
                        # Per market reason stats
                        diag_data[d_key]["markets"][market]["count"] += 1
                        diag_data[d_key]["markets"][market]["actual_sum"] += actual
                        diag_data[d_key]["markets"][market]["required_sum"] += required
                        diag_data[d_key]["markets"][market]["gap_sum"] += gap
                        diag_data[d_key]["markets"][market]["gap_pct_sum"] += gap_pct
            except Exception:
                continue

    # Finalize JSON structure
    report = {
        "decision_count": decision_count,
        "buy_count": buy_count,
        "no_buy_count": no_buy_count,
        "buy_ratio": round(buy_count / decision_count, 4) if decision_count > 0 else 0,
        "reasons": dict(reasons),
        "markets": {m: dict(r) for m, r in market_reasons.items()},
        "diagnostics": {}
    }

    for reason, data in diag_data.items():
        count = data["count"]
        if count > 0:
            avg_diag = {
                "count": count,
                "avg_actual": round(data["actual_sum"] / count, 6),
                "avg_required": round(data["required_sum"] / count, 6),
                "avg_gap": round(data["gap_sum"] / count, 6),
                "avg_gap_pct": round(data["gap_pct_sum"] / count, 2),
                "market_details": {}
            }
            for m, m_data in data["markets"].items():
                m_count = m_data["count"]
                avg_diag["market_details"][m] = {
                    "count": m_count,
                    "avg_actual": round(m_data["actual_sum"] / m_count, 6),
                    "avg_required": round(m_data["required_sum"] / m_count, 6),
                    "avg_gap": round(m_data["gap_sum"] / m_count, 6),
                    "avg_gap_pct": round(m_data["gap_pct_sum"] / m_count, 2)
                }
            report["diagnostics"][reason] = avg_diag

    # Save JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Save TXT (Korean Summary)
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("=== Orderflow 진입 거절 상세 진단 리포트 ===\n\n")
        f.write(f"총 판단 횟수: {decision_count}\n")
        f.write(f"매수 진입: {buy_count}\n")
        f.write(f"진입 거절: {no_buy_count}\n")
        if decision_count > 0:
            f.write(f"진입 성공률: {buy_count/decision_count*100:.2f}%\n")
        f.write("\n--- 거절 사유별 통계 ---\n")
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        for r, c in sorted_reasons:
            ratio = c / no_buy_count * 100 if no_buy_count > 0 else 0
            f.write(f"- {r}: {c}건 ({ratio:.2f}%)\n")

        f.write("\n--- 상세 진단 (Diagnostic) ---\n")
        for reason in ["LOW_VOLUME", "LOW_IMBALANCE", "SPREAD_TOO_WIDE"]:
            if reason in report["diagnostics"]:
                d = report["diagnostics"][reason]
                f.write(f"\n[{reason}]\n")
                f.write(f"  횟수: {d['count']}\n")
                f.write(f"  평균 실제값: {d['avg_actual']:.6f}\n")
                f.write(f"  평균 기준값: {d['avg_required']:.6f}\n")
                f.write(f"  평균 차이(Gap): {d['avg_gap']:.6f} ({d['avg_gap_pct']}%)\n")
                f.write("  마켓별 상세:\n")
                for m, md in d["market_details"].items():
                    f.write(f"    * {m}: {md['count']}건, 차이 {md['avg_gap_pct']}%\n")
            else:
                f.write(f"\n[{reason}] 데이터가 부족하거나 발견되지 않았습니다.\n")

        f.write("\n--- 결론 및 제언 ---\n")
        if no_buy_count > 0:
            top_reason = sorted_reasons[0][0]
            f.write(f"가장 빈번한 거절 사유는 '{top_reason}'입니다.\n")
            if top_reason == "LOW_VOLUME":
                f.write("거래량 기준(buy_trade_value_3s)이 시장 상황에 비해 너무 높을 수 있으니 관찰이 필요합니다.\n")
            elif top_reason == "SPREAD_TOO_WIDE":
                f.write("스프레드 허용치가 너무 낮아 변동성 장세에서 진입이 차단되고 있을 가능성을 검토하십시오.\n")
            elif top_reason == "LOW_IMBALANCE":
                f.write("매수/매도 불균형 조건이 너무 까다로운지 확인이 필요합니다.\n")
        else:
            f.write("진입 거절 사례가 없습니다.\n")
        
        f.write("\n(본 리포트는 진단용이며, 설정값 변경은 수동으로 검토 후 진행하십시오.)\n")

def run_rejection_diagnostics(
    decisions_path: str = "logs/orderflow_paper_decisions.jsonl",
    output_json_path: str = "reports/rejection_diagnostics.json",
    output_txt_path: str = "reports/rejection_diagnostics_summary.txt"
) -> Dict[str, Any]:
    build_rejection_diagnostics(decisions_path, output_json_path, output_txt_path)
    return {
        "ok": True,
        "command": "rejection-diagnostics",
        "output_json": output_json_path,
        "output_txt": output_txt_path
    }
