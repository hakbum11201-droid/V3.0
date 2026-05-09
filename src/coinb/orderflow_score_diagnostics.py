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

def run_orderflow_score_diagnostics(snapshot_path, opportunity_path, config_path, output_json, output_txt):
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

    strat_cfg = cfg.get("strategy", {})
    
    # Thresholds
    min_ofi = strat_cfg.get("min_ofi_score", 40)
    min_sweep = strat_cfg.get("min_sweep_score", 40)
    min_abs = strat_cfg.get("min_absorption_score", 40)
    min_cont = strat_cfg.get("min_continuation_score", 60)
    
    using_fallbacks = []
    if "min_ofi_score" not in strat_cfg: using_fallbacks.append("min_ofi_score")
    if "min_sweep_score" not in strat_cfg: using_fallbacks.append("min_sweep_score")
    if "min_absorption_score" not in strat_cfg: using_fallbacks.append("min_absorption_score")
    if "min_continuation_score" not in strat_cfg: using_fallbacks.append("min_continuation_score")

    all_scores = {
        "ofi_score": [],
        "sweep_score": [],
        "absorption_score": [],
        "continuation_score": []
    }
    
    market_stats = {}

    markets = opp_data.get("markets", {})
    for m_name, m_data in markets.items():
        samples = m_data.get("samples", [])
        m_scores = {k: [] for k in all_scores}
        
        for s in samples:
            for k in all_scores:
                val = s.get(k)
                if val is not None:
                    m_scores[k].append(val)
                    all_scores[k].append(val)
        
        m_dist = {k: calculate_percentiles(v) for k, v in m_scores.items()}
        
        def calc_rates(scores_dict):
            rates = {}
            for k, vals in scores_dict.items():
                if not vals: 
                    rates[k] = 0
                    continue
                thresh = min_ofi if "ofi" in k else min_sweep if "sweep" in k else min_abs if "absorption" in k else min_cont
                passed = sum(1 for v in vals if v >= thresh)
                rates[k] = (passed / len(vals)) * 100
            return rates

        market_stats[m_name] = {
            "distributions": m_dist,
            "pass_rates": calc_rates(m_scores)
        }

    global_dist = {k: calculate_percentiles(v) for k, v in all_scores.items()}
    
    def calc_global_rates():
        rates = {}
        for k, vals in all_scores.items():
            if not vals: 
                rates[k] = 0
                continue
            thresh = min_ofi if "ofi" in k else min_sweep if "sweep" in k else min_abs if "absorption" in k else min_cont
            passed = sum(1 for v in vals if v >= thresh)
            rates[k] = (passed / len(vals)) * 100
        return rates

    global_pass_rates = calc_global_rates()
    
    # Bottleneck ranking
    sorted_bottlenecks = sorted(global_pass_rates.items(), key=lambda x: x[1])

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "using_fallbacks": using_fallbacks,
        "thresholds": {
            "min_ofi_score": min_ofi,
            "min_sweep_score": min_sweep,
            "min_absorption_score": min_abs,
            "min_continuation_score": min_cont
        },
        "global": {
            "distributions": global_dist,
            "pass_rates": global_pass_rates,
            "bottleneck_rank": [k for k, v in sorted_bottlenecks]
        },
        "markets": market_stats
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== Orderflow 점수 상세 진단 리포트 ===\n")
        f.write(f"분석 일시: {report['generated_at']}\n")
        f.write(f"대상 데이터: {opportunity_path}\n\n")
        
        if using_fallbacks:
            f.write(f"[주의] 다음 기준값은 Config에 없어 기본값(fallback)을 사용함: {', '.join(using_fallbacks)}\n\n")
            
        f.write("--- 전체 점수 분포 및 통과율 ---\n")
        for k in report["global"]["distributions"]:
            d = report["global"]["distributions"][k]
            rate = report["global"]["pass_rates"][k]
            thresh = report["thresholds"][f"min_{k}"]
            f.write(f"[{k.upper()}] (기준: >= {thresh})\n")
            f.write(f"  - 통과율: {rate:.2f}%\n")
            f.write(f"  - 평균: {d['mean']:.2f} / P50: {d['p50']:.2f} / P90: {d['p90']:.2f} / MAX: {d['max']:.2f}\n")
        
        f.write(f"\n--- 병목 분석 결과 ---\n")
        f.write(f"가장 강력한 병목 점수: {report['global']['bottleneck_rank'][0].upper()}\n")
        f.write(f"두 번째 병목 점수: {report['global']['bottleneck_rank'][1].upper()}\n\n")
        
        f.write("--- 마켓별 통과율 요약 (Continuation 기준) ---\n")
        for m, stats in market_stats.items():
            rate = stats["pass_rates"]["continuation_score"]
            f.write(f"- {m}: {rate:.2f}%\n")
            
        f.write("\n--- 진단 결론 및 권고 ---\n")
        f.write("1. 특정 점수의 통과율이 극단적으로 낮다면 해당 가중치나 로직의 현실성을 검토해야 함.\n")
        f.write("2. 'Continuation'은 OFI/Sweep/Absorption의 결합이므로 하위 점수 개선이 선행되어야 함.\n")
        f.write("3. [주의] 본 진단 결과에 따른 조건 변경은 자동 적용하지 말고, paper 실험 후 수동으로 검토할 것.\n")

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_orderflow_score_diagnostics(args.snapshot, args.opportunity, args.config, args.output_json, args.output_txt)
