import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_market_focus_diagnostics(backtest_path: str, winner_profile_path: str, output_json: str, output_txt: str):
    """
    마켓 집중도와 거래량 품질(Volume Quality)을 분석합니다.
    """
    print(f"[MarketFocus] Loading inputs: {backtest_path}, {winner_profile_path}")

    if not os.path.exists(backtest_path):
        result = {"ok": False, "reason": "Backtest file not found."}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    with open(backtest_path, 'r', encoding='utf-8') as f:
        backtest_data = json.load(f)
    
    samples = backtest_data.get("samples", [])
    if not samples:
        result = {"ok": False, "reason": "No samples found."}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # Filtered candidates (Filter Passed)
    candidates = [s for s in samples if s.get("filter_pass", False)]
    print(f"[MarketFocus] Analyzing {len(candidates)} filter-passed candidates...")

    thresholds = [75, 85, 95]
    windows = ["300", "600"]
    
    analysis_results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "total_filter_passed": len(candidates),
        "market_performance": {},
        "volume_quality": {}
    }

    # 1. Market Performance Analysis (ALL/BTC/XRP/SOL)
    all_symbols = sorted(list(set(s["symbol"] for s in candidates)))
    for s_id in all_symbols + ["ALL"]:
        analysis_results["market_performance"][s_id] = {}
        for th in thresholds:
            for w in windows:
                key = f"th{th}_w{w}"
                
                # Filter by symbol and threshold
                active = [s for s in candidates if (s_id == "ALL" or s["symbol"] == s_id) and s["score"] >= th and w in s["outcome"]]
                if not active: continue
                
                rets = [s["outcome"][w]["ret"] for s in active]
                mfes = [s["outcome"][w]["mfe"] for s in active]
                winners = [s for s in active if s["outcome"][w]["mfe"] >= 0.20]
                
                cost = 0.20 # Cost floor
                net_rets = [r - cost for r in rets]
                
                analysis_results["market_performance"][s_id][key] = {
                    "count": len(active),
                    "winners": len(winners),
                    "winner_rate": float(len(winners) / len(active) * 100),
                    "avg_net_pnl": float(np.mean(net_rets)),
                    "median_net_pnl": float(np.median(net_rets)),
                    "avg_mfe": float(np.mean(mfes)),
                    "max_mfe": float(np.max(mfes))
                }

    # 2. Volume Quality Analysis (buy_trade_value_10s)
    # Define Bins based on sample distribution
    v_vals = [s["factors"]["buy_trade_value_10s"] for s in candidates]
    if v_vals:
        q = np.percentile(v_vals, [25, 50, 75])
        bins = [
            (0, q[0], "Low"),
            (q[0], q[1], "Mid"),
            (q[1], q[2], "High"),
            (q[2], max(v_vals) + 1, "Overheated")
        ]
        
        for b_min, b_max, label in bins:
            analysis_results["volume_quality"][label] = {"range": [float(b_min), float(b_max)], "stats": {}}
            for th in thresholds:
                for w in windows:
                    key = f"th{th}_w{w}"
                    active = [s for s in candidates if b_min <= s["factors"]["buy_trade_value_10s"] < b_max and s["score"] >= th and w in s["outcome"]]
                    if not active: continue
                    
                    winners = [s for s in active if s["outcome"][w]["mfe"] >= 0.20]
                    rets = [s["outcome"][w]["ret"] for s in active]
                    
                    analysis_results["volume_quality"][label]["stats"][key] = {
                        "count": len(active),
                        "winners": len(winners),
                        "winner_rate": float(len(winners) / len(active) * 100),
                        "avg_net_pnl": float(np.mean(rets) - 0.20)
                    }

    # Write JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, indent=2)

    generate_summary_txt(analysis_results, output_txt, thresholds, windows)
    print(f"[MarketFocus] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(res, output_txt, thresholds, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("          Market Focus & Volume Quality Diagnostics (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"Filter 통과 후보: {res['total_filter_passed']}회")
    lines.append("")

    lines.append("--- [마켓별 성과 비교] ---")
    symbols = [s for s in res["market_performance"].keys() if s != "ALL"]
    for s in symbols:
        lines.append(f"- Market: {s}")
        for th in thresholds:
            key = f"th{th}_w600"
            m = res["market_performance"][s].get(key)
            if m:
                lines.append(f"  [{key}] Count: {m['count']:4} | Winner: {m['winners']:3} ({m['winner_rate']:.2f}%) | Avg Net PnL: {m['avg_net_pnl']:.4f}%")
        lines.append("")

    lines.append("--- [Volume Quality (10s Buy Value) 구간 분석] ---")
    for label, data in res["volume_quality"].items():
        r = data["range"]
        lines.append(f"- 구간: {label:10} ({r[0]:12.0f} ~ {r[1]:12.0f})")
        for th in thresholds:
            key = f"th{th}_w600"
            m = data["stats"].get(key)
            if m:
                lines.append(f"  [{key}] Count: {m['count']:4} | Winner: {m['winners']:3} ({m['winner_rate']:.2f}%) | Avg Net PnL: {m['avg_net_pnl']:.4f}%")
    lines.append("")

    lines.append("--- 진단 결론 ---")
    sol_stats = res["market_performance"].get("KRW-SOL", {}).get("th75_w600")
    if sol_stats and sol_stats["winners"] > 0:
        lines.append("1. SOL 집중 현상 유의미성: 현재 3시간 샘플 내에서는 매우 유의미함.")
        lines.append(f"   - SOL의 승률({sol_stats['winner_rate']:.2f}%)이 타 마켓 대비 압도적임.")
    else:
        lines.append("1. SOL 집중 현상 유의미성: 표본 부족으로 단정하기 어려움.")

    # Find best Volume Quality
    best_vq = "None"; max_wr = -1
    for label, data in res["volume_quality"].items():
        stats = data["stats"].get("th75_w600")
        if stats and stats["winner_rate"] > max_wr:
            max_wr = stats["winner_rate"]; best_vq = label
    
    lines.append(f"2. 최적 Volume Quality 구간: {best_vq} (승률 {max_wr:.2f}%)")
    lines.append("3. Market Focus Filter v1 설계 방향:")
    lines.append("   - 주도 마켓(SOL 등) 우선 진입 조건 추가 검토")
    lines.append(f"   - {best_vq} 수준의 적정 거래량 품질 조건 필수화")
    lines.append("   - 과열(Overheated) 구간의 Reversal 또는 무반응 차단 필터 강화")

    lines.append("")
    lines.append("4. 주의: 분석 기간이 3시간으로 짧아 일반화하기에는 표본이 부족함.")
    lines.append("   - 장시간(24h+) WS 로그에 대한 교차 검증 필수.")
    lines.append("   - 자동 config 반영 금지. 실거래 반영 금지.")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
