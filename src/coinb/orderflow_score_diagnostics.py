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

def run_orderflow_score_diagnostics(snapshot_path, opportunity_path, config_path, output_json, output_txt):
    if not os.path.exists(opportunity_path) or not os.path.exists(config_path): return {"ok": False}
    with open(config_path, "r", encoding="utf-8") as f: cfg = json.load(f)
    with open(opportunity_path, "r", encoding="utf-8") as f: opp_data = json.load(f)
    
    strat = cfg.get("strategy", {})
    th = {"ofi_score": strat.get("min_ofi_score", 40), "sweep_score": strat.get("min_sweep_score", 40), "absorption_score": strat.get("min_absorption_score", 40), "continuation_score": strat.get("min_continuation_score", 60)}
    
    all_s = {k: [] for k in th}
    m_reports = {}
    for m_n, m_d in opp_data.get("markets", {}).items():
        m_s = {k: [] for k in th}
        for s in m_d.get("samples", []):
            for k in th:
                if s.get(k) is not None: m_s[k].append(s[k]); all_s[k].append(s[k])
        m_reports[m_n] = {"pass_rates": {k: sum(1 for v in m_s[k] if v >= th[k])/len(m_s[k])*100 if m_s[k] else 0 for k in th}}

    g_dist = {k: calculate_percentiles(v) for k, v in all_s.items()}
    g_pass = {k: sum(1 for v in all_s[k] if v >= th[k])/len(all_s[k])*100 if all_s[k] else 0 for k in th}
    
    report = {"ok": True, "generated_at": datetime.now().isoformat(), "thresholds": th, "global": {"distributions": g_dist, "pass_rates": g_pass}, "markets": m_reports}
    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("=== Orderflow 점수 상세 진단 리포트 ===")
    lines.append(f"분석 일시: {report['generated_at']} | 대상: {opportunity_path}\n")
    for k in th:
        lines.append(f"[{k.upper()}] (기준: >= {th[k]}) | 통과율: {g_pass[k]:.2f}% | Avg: {g_dist[k]['mean']:.2f}")
    lines.append("\n(본 리포트는 진단용이며 설정값 변경은 수동 검토 후 진행하십시오.)")
    report_io.write_text_report(output_txt, "\n".join(lines))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True); parser.add_argument("--opportunity", required=True); parser.add_argument("--config", required=True); parser.add_argument("--output-json", required=True); parser.add_argument("--output-txt", required=True)
    args = parser.parse_args(); run_orderflow_score_diagnostics(args.snapshot, args.opportunity, args.config, args.output_json, args.output_txt)
