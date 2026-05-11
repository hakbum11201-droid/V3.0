import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_factor_filter_winner_profile(backtest_json: str, output_json: str, output_txt: str):
    """
    Market Factor Filter를 통과한 후보 중 수익이 난 후보(Winner)와 그렇지 못한 후보의 차이를 분석합니다.
    """
    print(f"[WinnerProfile] Loading backtest results: {backtest_json}")

    if not os.path.exists(backtest_json):
        result = {"ok": False, "reason": "Backtest file not found."}
        report_io.write_json_report(output_json, result)
        return

    with open(backtest_json, 'r', encoding='utf-8') as f:
        bt_data = json.load(f)

    samples = bt_data.get("samples", [])
    if not samples:
        result = {"ok": False, "reason": "No samples found in backtest results."}
        report_io.write_json_report(output_json, result)
        return

    winners = [s for s in samples if s["mfe"] >= 0.20]
    losers = [s for s in samples if s["mfe"] < 0.20]

    print(f"[WinnerProfile] Winners: {len(winners)} | Losers: {len(losers)}")

    stats = {}
    if winners and samples:
        # Extract factor keys from the first sample
        factor_keys = samples[0]["factors"].keys()
        for k in factor_keys:
            w_vals = [s["factors"][k] for s in winners]
            l_vals = [s["factors"][k] for s in losers]
            
            stats[k] = {
                "winner_avg": float(np.mean(w_vals)),
                "loser_avg": float(np.mean(l_vals)) if l_vals else 0,
                "diff": float(np.mean(w_vals) - np.mean(l_vals)) if l_vals else 0
            }

    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(samples),
        "winners_count": len(winners),
        "stats": stats
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[WinnerProfile] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("      Market Factor Filter Winner Profile Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append(f"전체 필터 통과 후보: {out['total_samples']} | 수익 후보(Winner): {out['winners_count']}")
    lines.append("")
    lines.append(f"{'Factor':25} | {'Winner Avg':12} | {'Loser Avg':12} | {'Diff':10}")
    lines.append("-" * 70)
    for k, v in out["stats"].items():
        lines.append(f"{k:25} | {v['winner_avg']:12.4f} | {v['loser_avg']:12.4f} | {v['diff']:10.4f}")
    lines.append("")
    lines.append("--- 진단 결론 ---")
    lines.append("1. Winner와 Loser 간의 차이가 큰 Factor를 추가 필터나 가중치에 반영하십시오.")
    lines.append("2. 주의: 본 결과는 필터링된 집단 내에서의 상대적 차이입니다.")
    report_io.write_text_report(output_txt, "\n".join(lines))
