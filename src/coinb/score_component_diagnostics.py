import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List
from . import report_io

def calculate_percentiles(values):
    if not values: return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "p95", "p99", "max"]}
    sorted_vals = sorted(values); n = len(sorted_vals)
    def get_p(p): return sorted_vals[min(int(n * p / 100), n - 1)]
    return {"count": n, "mean": sum(values) / n, "p50": get_p(50), "p75": get_p(75), "p90": get_p(90), "p95": get_p(95), "p99": get_p(99), "max": sorted_vals[-1]}

def run_score_component_diagnostics(opportunity_path, ws_path, config_path, output_json, output_txt):
    if not os.path.exists(opportunity_path) or not os.path.exists(config_path): return {"ok": False}
    with open(config_path, "r", encoding="utf-8") as f: cfg = json.load(f)
    with open(opportunity_path, "r", encoding="utf-8") as f: opp_data = json.load(f)
    
    metrics = ["price_change_1s_pct", "price_change_3s_pct", "price_change_10s_pct", "buy_trade_value_3s", "buy_trade_value_10s", "sell_trade_value_3s", "sell_trade_value_10s", "spread_pct", "bid_ask_depth_ratio_5", "sweep_score", "continuation_score"]
    all_vals = {m: [] for m in metrics}
    m_vals = defaultdict(lambda: {m: [] for m in metrics})

    for m_name, m_data in opp_data.get("markets", {}).items():
        for s in m_data.get("samples", []):
            for m in metrics:
                if s.get(m) is not None:
                    all_vals[m].append(s[m]); m_vals[m_name][m].append(s[m])

    global_stats = {m: calculate_percentiles(all_vals[m]) for m in metrics}
    m_stats = {m_n: {m: calculate_percentiles(mv[m]) for m in metrics} for m_n, mv in m_vals.items()}

    report = {"ok": True, "generated_at": datetime.now().isoformat(), "global_stats": global_stats, "market_stats": m_stats}
    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("=== 점수 구성 요소 상세 진단 리포트 ===")
    lines.append(f"분석 일시: {report['generated_at']} | 대상: {opportunity_path}\n")
    for m in metrics:
        s = global_stats[m]; unit = "%" if "pct" in m or "spread" in m else "KRW" if "value" in m else "점"
        lines.append(f"[{m.upper()}] Avg: {s['mean']:,.4f} | P50: {s['p50']:,.4f} | P90: {s['p90']:,.4f} {unit}")
    lines.append("\n(본 리포트는 진단용이며 설정값 변경은 수동 검토 후 진행하십시오.)")
    report_io.write_text_report(output_txt, "\n".join(lines))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True); parser.add_argument("--ws", required=True); parser.add_argument("--config", required=True); parser.add_argument("--output-json", required=True); parser.add_argument("--output-txt", required=True)
    args = parser.parse_args(); run_score_component_diagnostics(args.opportunity, args.ws, args.config, args.output_json, args.output_txt)
