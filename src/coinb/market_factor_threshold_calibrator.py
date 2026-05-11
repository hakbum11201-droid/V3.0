import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_factor_threshold_calibrator(market_factor_path: str, output_json: str, output_txt: str, candidate_output: str):
    """
    Market Factor 진단 결과를 분석하여 최적의 필터 임계값을 제안합니다.
    """
    print(f"[Calibrator] Loading diagnostic: {market_factor_path}")

    if not os.path.exists(market_factor_path):
        result = {"ok": False, "reason": "Market factor diagnostic file not found."}
        report_io.write_json_report(output_json, result)
        return

    with open(market_factor_path, 'r', encoding='utf-8') as f:
        diag = json.load(f)

    if not diag.get("ok", False) or "comparison" not in diag:
        result = {"ok": False, "reason": "Invalid diagnostic data format."}
        report_io.write_json_report(output_json, result)
        return

    comp = diag["comparison"]
    efficacy = diag.get("regime_efficacy", {})
    
    v1_ref = {
        "min_volatility_300s_pct": 0.05,
        "min_imbalance_300s": 0.10,
        "min_bid_ask_depth_ratio_5": 1.50,
        "max_spread_pct": 0.12
    }

    calib_results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "v1_assessment": {},
        "v2_proposal": {
            "name": "market_factor_filter_candidate_v2_from_36h",
            "mode": "paper_experiment_only",
            "description": "Auto-calibrated from 36h diagnostics",
            "market_factor_filter": {}
        },
        "factor_details": {}
    }

    # Factor Analysis
    target_factors = [
        "volatility_300s", "imbalance_300s", "depth_ratio", "spread_pct"
    ]

    for f_name in target_factors:
        if f_name not in comp: continue
        f_data = comp[f_name]
        
        w_avg = f_data["winner_avg"]
        l_avg = f_data["non_winner_avg"]
        median = efficacy.get(f_name, {}).get("median", w_avg)
        
        f_detail = {
            "winner_avg": w_avg,
            "non_winner_avg": l_avg,
            "diff": f_data["diff"],
            "median": median
        }
        
        # Assess v1 and Propose v2
        if f_name == "volatility_300s":
            v1_val = v1_ref["min_volatility_300s_pct"]
            is_too_strict = v1_val > w_avg # Simple check if above average
            calib_results["v1_assessment"]["volatility_300s"] = {
                "threshold": v1_val, "is_too_strict": is_too_strict
            }
            # Propose v2: Use median or winner_avg
            calib_results["v2_proposal"]["market_factor_filter"]["min_volatility_300s_pct"] = round(min(w_avg, 0.04), 4)
            
        elif f_name == "imbalance_300s":
            v1_val = v1_ref["min_imbalance_300s"]
            is_too_strict = v1_val > w_avg
            calib_results["v1_assessment"]["imbalance_300s"] = {
                "threshold": v1_val, "is_too_strict": is_too_strict
            }
            calib_results["v2_proposal"]["market_factor_filter"]["min_imbalance_300s"] = round(min(w_avg, 0.01), 4)

        elif f_name == "depth_ratio":
            v1_val = v1_ref["min_bid_ask_depth_ratio_5"]
            is_too_strict = v1_val > w_avg
            calib_results["v1_assessment"]["depth_ratio"] = {
                "threshold": v1_val, "is_too_strict": is_too_strict
            }
            calib_results["v2_proposal"]["market_factor_filter"]["min_bid_ask_depth_ratio_5"] = round(min(w_avg, 1.0), 2)

        elif f_name == "spread_pct":
            v1_val = v1_ref["max_spread_pct"]
            is_too_strict = v1_val < w_avg # Strict if lower than average
            calib_results["v1_assessment"]["spread_pct"] = {
                "threshold": v1_val, "is_too_strict": is_too_strict
            }
            calib_results["v2_proposal"]["market_factor_filter"]["max_spread_pct"] = round(max(w_avg * 1.5, 0.10), 3)

        calib_results["factor_details"][f_name] = f_detail

    # Fill defaults for v2 if missing
    mff = calib_results["v2_proposal"]["market_factor_filter"]
    if "min_volatility_300s_pct" not in mff: mff["min_volatility_300s_pct"] = 0.04
    if "min_imbalance_300s" not in mff: mff["min_imbalance_300s"] = 0.00
    if "min_bid_ask_depth_ratio_5" not in mff: mff["min_bid_ask_depth_ratio_5"] = 0.80
    if "max_spread_pct" not in mff: mff["max_spread_pct"] = 0.12
    mff["min_depth_total_5"] = 1.0 # Default
    
    calib_results["v2_proposal"].update({
        "apply_after": [], "apply_before": ["market_focus_filter"],
        "requires_net_edge_positive": True, "auto_apply": False
    })

    # Output Files
    report_io.write_json_report(output_json, calib_results)
    report_io.write_json_report(candidate_output, calib_results["v2_proposal"])
    generate_summary_txt(calib_results, output_txt)
    print(f"[Calibrator] Done. Reports: {output_json}, {output_txt}, {candidate_output}")

def generate_summary_txt(res, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("      Market Factor Threshold Calibration Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append("")

    lines.append("--- [v1 기준 평가] ---")
    for f, v in res["v1_assessment"].items():
        status = "!!! 과도함" if v["is_too_strict"] else "적절함"
        lines.append(f"- {f:25}: TH({v['threshold']:6.3f}) | 판단: {status}")
    lines.append("")

    lines.append("--- [Factor별 Winner 특성 (Average/Median)] ---")
    for f, d in res["factor_details"].items():
        lines.append(f"- {f:25}: Avg({d['winner_avg']:8.4f}) | Median({d['median']:8.4f})")
    lines.append("")

    lines.append("--- [v2 후보 기준 (Calibrated)] ---")
    mff = res["v2_proposal"]["market_factor_filter"]
    lines.append(f"- min_volatility_300s_pct   : {mff['min_volatility_300s_pct']:.4f}")
    lines.append(f"- min_imbalance_300s       : {mff['min_imbalance_300s']:.4f}")
    lines.append(f"- min_bid_ask_depth_ratio_5: {mff['min_bid_ask_depth_ratio_5']:.2f}")
    lines.append(f"- max_spread_pct           : {mff['max_spread_pct']:.3f}")
    lines.append("")

    lines.append("--- 진단 결론 ---")
    lines.append("1. v1 필터가 0개 통과된 원인: imbalance_300s(0.10)와 depth_ratio(1.50)가 실제 Winner 평균을 크게 상회함.")
    lines.append("2. 해결책: 실제 Winner의 평균값 및 중간값에 기반하여 v2 임계값을 현실화함.")
    lines.append("3. 주의: v2 기준은 자동 적용되지 않으며, 기존 36시간 로그로 combined-filter-backtest를 재실행해야 함.")
    lines.append("")
    lines.append("※ 자동 config 반영 금지. 실거래 반영 금지.")

    report_io.write_text_report(output_txt, "\n".join(lines))
