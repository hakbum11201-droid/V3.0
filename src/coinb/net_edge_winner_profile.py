import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List
from . import report_io

def average(values):
    return sum(values) / len(values) if values else 0

def run_net_edge_winner_profile(opportunity_path, backtest_path, net_edge_diag_path, output_json, output_txt):
    if not os.path.exists(backtest_path):
        return {"ok": False, "reason": f"Backtest file not found: {backtest_path}"}
    if not os.path.exists(net_edge_diag_path):
        return {"ok": False, "reason": f"Diagnostics file not found: {net_edge_diag_path}"}

    try:
        with open(backtest_path, "r", encoding="utf-8") as f:
            bt_data = json.load(f)
        with open(net_edge_diag_path, "r", encoding="utf-8") as f:
            diag_data = json.load(f)
    except Exception as e:
        return {"ok": False, "reason": f"Failed to load data: {e}"}

    all_results = bt_data.get("all_results", [])
    diag_details = diag_data.get("details", [])
    diag_map = {(d["market"], d["ts"]): d for d in diag_details}
    
    winners = []; non_winners = []
    
    for res in all_results:
        key = (res["market"], res["ts"])
        if key not in diag_map: continue
        diag = diag_map[key]
        mfe = diag["windows"].get("30", {}).get("mfe", 0)
        res["mfe"] = mfe
        res["mae"] = diag["windows"].get("30", {}).get("mae", 0)
        if mfe >= 0.20: winners.append(res)
        else: non_winners.append(res)

    def get_avg_profile(items):
        if not items: return {}
        raw_keys = ["buy_trade_value_3s", "buy_trade_value_10s", "spread_pct", "bid_ask_depth_ratio_5", "continuation_score", "sweep_score"]
        profile = {
            "total_score": average([i["total_score"] for i in items]),
            "mfe": average([i["mfe"] for i in items]),
            "mae": average([i["mae"] for i in items])
        }
        for k in raw_keys:
            profile[k] = average([i.get("raw", {}).get(k, 0) for i in items if i.get("raw")])
        return profile

    winner_profile = get_avg_profile(winners)
    non_winner_profile = get_avg_profile(non_winners)
    
    differences = {}
    for k in winner_profile:
        if isinstance(winner_profile[k], (int, float)):
            w_val = winner_profile[k]
            nw_val = non_winner_profile.get(k, 0)
            differences[k] = (w_val - nw_val) / abs(nw_val) * 100 if nw_val != 0 else 100
    sorted_diffs = sorted(differences.items(), key=lambda x: abs(x[1]), reverse=True)

    report = {
        "ok": True, "generated_at": datetime.now().isoformat(),
        "winner_count": len(winners), "non_winner_count": len(non_winners),
        "winner_profile": winner_profile, "non_winner_profile": non_winner_profile,
        "top_differences_pct": sorted_diffs[:10]
    }

    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("=== Net Edge Winner Profile 진단 리포트 ===")
    lines.append(f"분석 일시: {report['generated_at']}")
    lines.append(f"Winner (MFE >= 0.20%): {len(winners)}개")
    lines.append(f"Non-Winner: {len(non_winners)}개\n")
    
    if not winners:
        lines.append("[주의] 0.20% 이상 수익을 낸 후보가 없습니다. 현재 가중치로는 비용 극복이 불가능합니다.")
    else:
        lines.append("--- [Winner vs Non-Winner 비교] ---")
        lines.append(f"- Total Score: Winner({winner_profile['total_score']:.2f}) vs Non({non_winner_profile['total_score']:.2f})")
        lines.append(f"- 3s Buy Value: Winner({winner_profile['buy_trade_value_3s']:,.0f}) vs Non({non_winner_profile['buy_trade_value_3s']:,.0f})")
        lines.append(f"- Continuation: Winner({winner_profile['continuation_score']:.2f}) vs Non({non_winner_profile['continuation_score']:.2f})")
        lines.append(f"- Sweep Score: Winner({winner_profile['sweep_score']:.2f}) vs Non({non_winner_profile['sweep_score']:.2f})\n")
        
        lines.append("--- [주요 차이점 (상위 5개)] ---")
        for k, v in sorted_diffs[:5]:
            lines.append(f"- {k}: {v:+.2f}%")
    
    lines.append("\n--- [진단 결론] ---")
    if len(winners) < 5:
        lines.append("1. [경고] 성공 표본이 매우 부족(5개 미만)하여 확정적인 결론 도출이 어렵습니다.")
    
    if winners:
        best_indicator = sorted_diffs[0][0]
        lines.append(f"2. 성공 후보들은 실패 후보들보다 '{best_indicator}' 지표가 월등히 높은 경향을 보입니다.")
        lines.append("3. Soft Score v2 설계 시 해당 지표의 가중치를 대폭 상향하는 것을 검토하십시오.")
    
    lines.append("\n4. [주의] 본 시뮬레이션 결과는 config에 자동 반영되지 않습니다.")

    report_io.write_text_report(output_txt, "\n".join(lines))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--backtest", required=True)
    parser.add_argument("--net-edge-diagnostics", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_net_edge_winner_profile(args.opportunity, args.backtest, args.net_edge_diagnostics, args.output_json, args.output_txt)
