import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

def calculate_percentiles(values):
    if not values:
        return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "p95", "p99", "max"]}
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    def get_p(p):
        idx = int(n * p / 100)
        return sorted_vals[min(idx, n - 1)]

    return {
        "count": n,
        "mean": sum(values) / n,
        "p50": get_p(50),
        "p75": get_p(75),
        "p90": get_p(90),
        "p95": get_p(95),
        "p99": get_p(99),
        "max": sorted_vals[-1]
    }

def run_score_component_diagnostics(opportunity_path, ws_path, config_path, output_json, output_txt):
    if not os.path.exists(opportunity_path):
        return {"ok": False, "reason": f"Opportunity file not found: {opportunity_path}"}
    if not os.path.exists(config_path):
        return {"ok": False, "reason": f"Config file not found: {config_path}"}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        with open(opportunity_path, "r", encoding="utf-8") as f:
            opp_data = json.load(f)
    except Exception as e:
        return {"ok": False, "reason": f"Failed to load data: {e}"}

    metrics_to_analyze = [
        "price_change_1s_pct",
        "price_change_3s_pct",
        "price_change_10s_pct",
        "buy_trade_value_3s",
        "buy_trade_value_10s",
        "sell_trade_value_3s",
        "sell_trade_value_10s",
        "spread_pct",
        "bid_ask_depth_ratio_5",
        "sweep_score",
        "continuation_score"
    ]

    all_values = {m: [] for m in metrics_to_analyze}
    market_values = defaultdict(lambda: {m: [] for m in metrics_to_analyze})

    markets_data = opp_data.get("markets", {})
    for m_name, m_data in markets_data.items():
        samples = m_data.get("samples", [])
        for s in samples:
            for m in metrics_to_analyze:
                val = s.get(m)
                if val is not None:
                    all_values[m].append(val)
                    market_values[m_name][m].append(val)

    global_stats = {m: calculate_percentiles(all_values[m]) for m in metrics_to_analyze}
    
    market_stats = {}
    for m_name, m_metrics in market_values.items():
        market_stats[m_name] = {m: calculate_percentiles(m_metrics[m]) for m in metrics_to_analyze}

    # Reason Analysis (Heuristics)
    sweep_bottleneck_reason = "Unknown"
    cont_bottleneck_reason = "Unknown"
    
    # Sweep score logic: score += _clamp(p1s * 25.0, 0, 25) + _clamp(p3s * 15.0, 0, 25) + ...
    # Target score is 40. 
    p1s_p90 = global_stats["price_change_1s_pct"]["p90"]
    p3s_p90 = global_stats["price_change_3s_pct"]["p90"]
    buy3s_p90 = global_stats["buy_trade_value_3s"]["p90"]
    
    if p1s_p90 < 0.1: # Less than 0.1% change in 1s
        sweep_bottleneck_reason = "Price momentum (1s) is too low (P90 < 0.1%)"
    elif buy3s_p90 < 1000000:
        sweep_bottleneck_reason = "Buy trade value (3s) is too low (P90 < 1M KRW)"
    else:
        sweep_bottleneck_reason = "Calculation formula weights are too conservative for current market volatility"

    # Continuation score logic: score += ofi * 0.35 + sweep * 0.35 + abs * 0.15 + ...
    cont_p90 = global_stats["continuation_score"]["p90"]
    if cont_p90 < 40:
        cont_bottleneck_reason = "Underlying scores (OFI/Sweep) are too low to sustain Continuation"
    else:
        cont_bottleneck_reason = "Market lacks steady price follow-through (price_change_10s vs 3s)"

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "global_stats": global_stats,
        "market_stats": market_stats,
        "diagnosis": {
            "sweep_bottleneck_reason": sweep_bottleneck_reason,
            "continuation_bottleneck_reason": cont_bottleneck_reason
        }
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== 점수 구성 요소 상세 진단 리포트 ===\n")
        f.write(f"분석 일시: {report['generated_at']}\n")
        f.write(f"대상 데이터: {opportunity_path}\n\n")
        
        f.write("--- [핵심 병목 분석] ---\n")
        f.write(f"1. Sweep Score 저조 원인: {sweep_bottleneck_reason}\n")
        f.write(f"2. Continuation Score 저조 원인: {cont_bottleneck_reason}\n\n")
        
        f.write("--- [주요 지표 분포 (통합)] ---\n")
        for m in metrics_to_analyze:
            s = global_stats[m]
            unit = "%" if "pct" in m or "spread" in m else "KRW" if "value" in m else "점"
            f.write(f"[{m.upper()}]\n")
            if unit == "KRW":
                f.write(f"  - 평균: {s['mean']:,.0f} / P50: {s['p50']:,.0f} / P90: {s['p90']:,.0f} / MAX: {s['max']:,.0f} {unit}\n")
            else:
                f.write(f"  - 평균: {s['mean']:.4f} / P50: {s['p50']:.4f} / P90: {s['p90']:.4f} / MAX: {s['max']:.4f} {unit}\n")
        
        f.write("\n--- [마켓별 차이 요약] ---\n")
        for m_name, m_s in market_stats.items():
            sweep_p90 = m_s["sweep_score"]["p90"]
            cont_p90 = m_s["continuation_score"]["p90"]
            p3s_p90 = m_s["price_change_3s_pct"]["p90"]
            f.write(f"- {m_name}: Sweep(P90)={sweep_p90:.2f}, Cont(P90)={cont_p90:.2f}, P3S_Change(P90)={p3s_p90:.4f}%\n")
            
        f.write("\n--- [진단 결론] ---\n")
        f.write("1. 시장의 변동성(Price Change)이 현재 점수 가중치에 비해 부족하거나, 체결 규모가 작아 점수가 쌓이지 않음.\n")
        f.write("2. 이는 시장 기회 자체가 부족한 것인지, 아니면 계산식이 '폭등' 수준의 예외적 상황만 찾고 있는지 검토 필요.\n")
        f.write("3. [주의] 조건 변경은 자동 적용하지 말고, paper 실험 후 수동으로 검토할 것.\n")

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--ws", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_score_component_diagnostics(args.opportunity, args.ws, args.config, args.output_json, args.output_txt)
