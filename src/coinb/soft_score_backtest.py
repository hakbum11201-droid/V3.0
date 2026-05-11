import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List
from . import report_io

def calculate_percentiles(values):
    if not values:
        return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "p95", "max"]}
    
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
        "max": sorted_vals[-1]
    }

def run_soft_score_backtest(opportunity_path, candidate_path, output_json, output_txt):
    if not os.path.exists(opportunity_path):
        return {"ok": False, "reason": f"Opportunity file not found: {opportunity_path}"}
    if not os.path.exists(candidate_path):
        return {"ok": False, "reason": f"Candidate file not found: {candidate_path}"}

    try:
        with open(opportunity_path, "r", encoding="utf-8") as f:
            opp_data = json.load(f)
        with open(candidate_path, "r", encoding="utf-8") as f:
            cand_cfg = json.load(f)
    except Exception as e:
        return {"ok": False, "reason": f"Failed to load data: {e}"}

    weights = cand_cfg.get("weights", {})
    entry_thresh = cand_cfg.get("entry_threshold", 70)
    opp_thresholds = opp_data.get("thresholds", {})
    
    min_val_3s = opp_thresholds.get("min_trade_value_3s", 1500000)
    max_spread = opp_thresholds.get("max_spread_pct", 0.2)
    min_ratio = opp_thresholds.get("bid_ask_depth_ratio_min", 1.5)

    all_results = []
    total_samples = 0
    total_candidate_count = 0
    total_hard_pass_count = 0
    
    market_stats = defaultdict(lambda: {"total": 0, "candidates": 0, "hard_pass": 0})
    scores = []
    threshold_counts = {60: 0, 70: 0, 80: 0}

    markets_data = opp_data.get("markets", {})
    for m_name, m_data in markets_data.items():
        samples = m_data.get("samples", [])
        for s in samples:
            total_samples += 1
            market_stats[m_name]["total"] += 1
            
            v_score = min(1.0, s.get("buy_trade_value_3s", 0) / min_val_3s)
            s_score = max(0.0, min(1.0, (max_spread - s.get("spread_pct", 1.0)) / max_spread))
            i_score = min(1.0, s.get("bid_ask_depth_ratio_5", 0) / min_ratio)
            a_score = s.get("absorption_score", 0) / 100.0
            c_score = s.get("continuation_score", 0) / 100.0
            sw_score = s.get("sweep_score", 0) / 100.0
            
            total_score = (
                v_score * weights.get("volume_score", 25) +
                s_score * weights.get("spread_score", 20) +
                i_score * weights.get("imbalance_score", 20) +
                a_score * weights.get("absorption_score", 20) +
                c_score * weights.get("continuation_score", 10) +
                sw_score * weights.get("sweep_score", 5)
            )
            
            scores.append(total_score)
            
            if total_score >= 60: threshold_counts[60] += 1
            if total_score >= 70: threshold_counts[70] += 1
            if total_score >= 80: threshold_counts[80] += 1
            
            is_candidate = total_score >= entry_thresh
            if is_candidate:
                total_candidate_count += 1
                market_stats[m_name]["candidates"] += 1
            
            if s.get("all_pass"):
                total_hard_pass_count += 1
                market_stats[m_name]["hard_pass"] += 1
                
            all_results.append({
                "market": m_name,
                "ts": s.get("timestamp"),
                "total_score": round(total_score, 2),
                "is_candidate": is_candidate,
                "hard_pass": s.get("all_pass"),
                "components": {
                    "v": round(v_score, 4), "s": round(s_score, 4), "i": round(i_score, 4),
                    "a": round(a_score, 4), "c": round(c_score, 4), "sw": round(sw_score, 4)
                }
            })

    score_dist = calculate_percentiles(scores)
    top_candidates = sorted([r for r in all_results if r["is_candidate"]], 
                            key=lambda x: x["total_score"], reverse=True)[:20]

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "total_samples": total_samples,
        "candidate_count": total_candidate_count,
        "candidate_rate": (total_candidate_count / total_samples * 100) if total_samples > 0 else 0,
        "hard_pass_count": total_hard_pass_count,
        "improvement_ratio": (total_candidate_count / total_hard_pass_count) if total_hard_pass_count > 0 else 0,
        "score_distribution": score_dist,
        "threshold_comparison": threshold_counts,
        "markets": dict(market_stats),
        "top_candidates": top_candidates
    }

    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("=== Soft Score 전환 시뮬레이션 결과 요약 (Backtest) ===")
    lines.append(f"분석 일시: {report['generated_at']}")
    lines.append(f"대상 Opportunity: {opportunity_path}")
    lines.append(f"사용 가중치 설정: {candidate_path}\n")
    
    lines.append("--- [핵심 통계] ---")
    lines.append(f"전체 샘플 수 (1초 단위): {total_samples:,}개")
    lines.append(f"Soft Score 후보 발생 수: {total_candidate_count:,}회")
    lines.append(f"후보 발생률: {report['candidate_rate']:.2f}%")
    lines.append(f"기존 Hard Gate 통과 수: {total_hard_pass_count:,}회")
    if total_hard_pass_count > 0:
        lines.append(f"진입 기회 증가율: {report['improvement_ratio']:.1f}배")
    lines.append("")
    
    lines.append("--- [점수 분포 (Total Score)] ---")
    sd = report["score_distribution"]
    lines.append(f"평균: {sd['mean']:.2f} / P50: {sd['p50']:.2f} / P90: {sd['p90']:.2f} / MAX: {sd['max']:.2f}\n")
    
    lines.append("--- [Threshold별 후보 수 비교] ---")
    lines.append(f"- Thresh 60: {threshold_counts[60]:,}회 ({(threshold_counts[60]/total_samples*100):.2f}%)")
    lines.append(f"- Thresh 70: {threshold_counts[70]:,}회 ({(threshold_counts[70]/total_samples*100):.2f}%) <- 권장")
    lines.append(f"- Thresh 80: {threshold_counts[80]:,}회 ({(threshold_counts[80]/total_samples*100):.2f}%)\n")
    
    lines.append("--- [마켓별 후보 발생 수] ---")
    for m, s in market_stats.items():
        rate = (s["candidates"] / s["total"] * 100) if s["total"] > 0 else 0
        lines.append(f"- {m}: {s['candidates']:,}회 ({rate:.2f}%)")
        
    lines.append("\n--- [진단 결론] ---")
    if report["candidate_rate"] > 5.0:
        lines.append("1. [경고] 후보 발생률이 5%를 초과하여 거래가 너무 빈번할 수 있음. Threshold 상향 검토 필요.")
    elif total_candidate_count == 0:
        lines.append("1. [경고] Soft Score 전환 후에도 진입 후보가 0건임. 가중치나 정규화 방식 재검토 필요.")
    else:
        lines.append("1. Soft Score 전환 시 기존 Hard Gate 방식보다 유연하게 진입 기회를 포착함.")
        
    lines.append("2. 실제 전략 반영 전, 포지션 유지 시간 및 손익 시뮬레이션(Paper Backtest)이 반드시 선행되어야 함.")
    lines.append("3. [주의] 본 시뮬레이션 결과는 config에 자동 반영되지 않으며, 수동 검토용임.")

    report_io.write_text_report(output_txt, "\n".join(lines))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_soft_score_backtest(args.opportunity, args.candidate, args.output_json, args.output_txt)
