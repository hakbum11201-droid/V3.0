import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_market_factor_filter_winner_profile(backtest_path: str, output_json: str, output_txt: str):
    """
    Market Factor Filter를 통과한 후보 중 Winner와 Non-Winner의 특징을 분석합니다.
    """
    print(f"[WinnerProfile] Loading backtest results: {backtest_path}")

    if not os.path.exists(backtest_path):
        result = {"ok": False, "reason": f"Backtest file not found: {backtest_path}"}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    with open(backtest_path, 'r', encoding='utf-8') as f:
        backtest_data = json.load(f)

    samples = backtest_data.get("samples", [])
    if not samples:
        result = {"ok": False, "reason": "No samples found in backtest data."}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # Filtered candidates (those that passed the market factor filter)
    candidates = [s for s in samples if s.get("filter_pass", False)]
    print(f"[WinnerProfile] Analyzing {len(candidates)} filter-passed candidates...")

    thresholds = [75, 85, 95]
    windows = ["300", "600"]
    
    analysis_results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "total_filter_passed": len(candidates),
        "by_config": {}
    }

    factor_keys = [
        "volatility_300s", "imbalance_300s", "imbalance_10s", "depth_ratio", 
        "spread_pct", "price_chg_10s", "buy_trade_value_10s"
    ]

    for th in thresholds:
        for w in windows:
            key = f"th{th}_w{w}"
            
            # Select samples that pass both Filter and Threshold
            active_samples = [s for s in candidates if s["score"] >= th and w in s["outcome"]]
            if not active_samples: continue
            
            winners = [s for s in active_samples if s["outcome"][w]["mfe"] >= 0.20]
            losers = [s for s in active_samples if s["outcome"][w]["mfe"] < 0.20]
            
            w_count = len(winners)
            l_count = len(losers)
            wr = w_count / (w_count + l_count) * 100 if (w_count + l_count) > 0 else 0
            
            config_stats = {
                "winner_count": w_count,
                "loser_count": l_count,
                "winner_rate": float(wr),
                "factors": {},
                "market_dist": {}
            }
            
            # Market Distribution
            for s in winners:
                m = s["symbol"]
                config_stats["market_dist"][m] = config_stats["market_dist"].get(m, 0) + 1
            
            # Factor Comparison
            for fk in factor_keys:
                w_vals = [s["factors"][fk] for s in winners]
                l_vals = [s["factors"][fk] for s in losers]
                
                w_avg = np.mean(w_vals) if w_vals else 0
                l_avg = np.mean(l_vals) if l_vals else 0
                diff = w_avg - l_avg
                
                config_stats["factors"][fk] = {
                    "winner_avg": float(w_avg),
                    "loser_avg": float(l_avg),
                    "diff": float(diff),
                    "importance": float(abs(diff) / (abs(l_avg) + 1e-9))
                }
            
            analysis_results["by_config"][key] = config_stats

    # Output JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, indent=2)

    generate_summary_txt(analysis_results, output_txt)
    print(f"[WinnerProfile] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(res, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("      Market Factor Filter Winner Profile Analysis (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"Filter 통과 후보 수: {res['total_filter_passed']}회")
    lines.append("")
    lines.append("※ 이 도구는 필터 통과 후보 내부의 Winner/Non-Winner를 정밀 비교합니다.")
    lines.append("")

    for key, stats in res["by_config"].items():
        lines.append(f"--- [Configuration: {key}] ---")
        lines.append(f"Winner: {stats['winner_count']}회 | Loser: {stats['loser_count']}회 | WR: {stats['winner_rate']:.2f}%")
        
        # Top factors
        sorted_f = sorted(stats["factors"].items(), key=lambda x: x[1]["importance"], reverse=True)
        lines.append("  [주요 지표 차이 (Winner vs Loser)]")
        for fk, v in sorted_f[:5]:
            lines.append(f"  - {fk:20}: W({v['winner_avg']:10.4f}) vs L({v['loser_avg']:10.4f}) | Diff: {v['diff']:.4f}")
        
        # Market
        m_dist = stats["market_dist"]
        if m_dist:
            m_str = ", ".join([f"{m}({c})" for m, c in m_dist.items()])
            lines.append(f"  [Winner 마켓 분포]: {m_str}")
        lines.append("")

    lines.append("--- 진단 결론 ---")
    # Identify common factors across configs
    all_diffs = {}
    for key, stats in res["by_config"].items():
        for fk, v in stats["factors"].items():
            all_diffs[fk] = all_diffs.get(fk, 0) + v["diff"]
    
    if all_diffs:
        top_diff = sorted(all_diffs.items(), key=lambda x: abs(x[1]), reverse=True)[0][0]
        lines.append(f"1. Winner를 결정짓는 핵심 차이 Factor: {top_diff}")
        lines.append("2. Market Factor Filter v2 설계 방향:")
        lines.append(f"   - {top_diff} 임계값을 현재보다 상향하여 정밀도 개선 필요")
        lines.append("   - 특정 마켓(Winner 집중 마켓)에 대한 가중치 차등 적용 검토")
    else:
        lines.append("1. 분석 결과: 유효한 차이점을 도출할 샘플이 부족합니다.")

    lines.append("")
    lines.append("3. 판단: Market Factor Filter v1에 위 지표를 결합하여 v2 후보를 설계하십시오.")
    lines.append("")
    lines.append("※ 자동 config 반영 금지. orderflow_paper.py 수정 전 추가 paper 실험 필수.")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
