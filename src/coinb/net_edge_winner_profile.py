import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

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

    # Join data
    all_results = bt_data.get("all_results", [])
    diag_details = diag_data.get("details", [])
    
    # Map diagnostics by market and ts
    diag_map = {(d["market"], d["ts"]): d for d in diag_details}
    
    winners = []
    non_winners = []
    
    for res in all_results:
        key = (res["market"], res["ts"])
        if key not in diag_map: continue
        
        diag = diag_map[key]
        # Check MFE at 30s (default)
        mfe = diag["windows"].get("30", {}).get("mfe", 0)
        res["mfe"] = mfe
        res["mae"] = diag["windows"].get("30", {}).get("mae", 0)
        
        if mfe >= 0.20:
            winners.append(res)
        else:
            non_winners.append(res)

    def get_avg_profile(items):
        if not items: return {}
        raw_keys = [
            "buy_trade_value_3s", "buy_trade_value_10s", 
            "sell_trade_value_3s", "sell_trade_value_10s",
            "spread_pct", "bid_ask_depth_ratio_5",
            "price_change_1s_pct", "price_change_3s_pct", "price_change_10s_pct",
            "ofi_score", "sweep_score", "absorption_score", "continuation_score"
        ]
        profile = {
            "total_score": average([i["total_score"] for i in items]),
            "mfe": average([i["mfe"] for i in items]),
            "mae": average([i["mae"] for i in items]),
            "markets": dict(defaultdict(int))
        }
        for i in items:
            profile["markets"][i["market"]] = profile["markets"].get(i["market"], 0) + 1
            
        for k in raw_keys:
            profile[k] = average([i.get("raw", {}).get(k, 0) for i in items if i.get("raw")])
        
        return profile

    winner_profile = get_avg_profile(winners)
    non_winner_profile = get_avg_profile(non_winners)
    
    # Find significant differences
    differences = {}
    for k in winner_profile:
        if isinstance(winner_profile[k], (int, float)):
            w_val = winner_profile[k]
            nw_val = non_winner_profile.get(k, 0)
            if nw_val != 0:
                diff_pct = (w_val - nw_val) / abs(nw_val) * 100
            else:
                diff_pct = 100 if w_val > 0 else 0
            differences[k] = diff_pct

    sorted_diffs = sorted(differences.items(), key=lambda x: abs(x[1]), reverse=True)

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "winner_count": len(winners),
        "non_winner_count": len(non_winners),
        "winner_profile": winner_profile,
        "non_winner_profile": non_winner_profile,
        "top_differences_pct": sorted_diffs[:10],
        "winners_list": winners[:10]
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== Net Edge Winner Profile 진단 리포트 ===\n")
        f.write(f"분석 일시: {report['generated_at']}\n")
        f.write(f"Winner (MFE >= 0.20%): {len(winners)}개\n")
        f.write(f"Non-Winner: {len(non_winners)}개\n\n")
        
        if not winners:
            f.write("[주의] 0.20% 이상 수익을 낸 후보가 없습니다. 현재 가중치로는 비용 극복이 불가능합니다.\n")
        else:
            f.write("--- [Winner vs Non-Winner 비교] ---\n")
            f.write(f"- Total Score: Winner({winner_profile['total_score']:.2f}) vs Non({non_winner_profile['total_score']:.2f})\n")
            f.write(f"- 3s Buy Value: Winner({winner_profile['buy_trade_value_3s']:,.0f}) vs Non({non_winner_profile['buy_trade_value_3s']:,.0f})\n")
            f.write(f"- Continuation: Winner({winner_profile['continuation_score']:.2f}) vs Non({non_winner_profile['continuation_score']:.2f})\n")
            f.write(f"- Sweep Score: Winner({winner_profile['sweep_score']:.2f}) vs Non({non_winner_profile['sweep_score']:.2f})\n\n")
            
            f.write("--- [주요 차이점 (상위 5개)] ---\n")
            for k, v in sorted_diffs[:5]:
                f.write(f"- {k}: {v:+.2f}%\n")
        
        f.write("\n--- [진단 결론] ---\n")
        if len(winners) < 5:
            f.write("1. [경고] 성공 표본이 매우 부족(5개 미만)하여 확정적인 결론 도출이 어렵습니다.\n")
        
        if winners:
            best_indicator = sorted_diffs[0][0]
            f.write(f"2. 성공 후보들은 실패 후보들보다 '{best_indicator}' 지표가 월등히 높은 경향을 보입니다.\n")
            f.write("3. Soft Score v2 설계 시 해당 지표의 가중치를 대폭 상향하는 것을 검토하십시오.\n")
        
        f.write("\n4. [주의] 본 시뮬레이션 결과는 config에 자동 반영되지 않습니다.\n")
        f.write("5. 결과 신뢰도 확보를 위해 최소 3~7시간 이상의 추가 데이터 검증이 필요합니다.\n")

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
