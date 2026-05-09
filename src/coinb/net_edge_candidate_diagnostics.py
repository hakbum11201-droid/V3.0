import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

def calculate_percentiles(values):
    if not values:
        return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "max"]}
    
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
        "max": sorted_vals[-1]
    }

def run_net_edge_candidate_diagnostics(opportunity_path, backtest_path, net_edge_path, ws_path, output_json, output_txt):
    if not os.path.exists(backtest_path):
        return {"ok": False, "reason": f"Backtest file not found: {backtest_path}"}
    if not os.path.exists(ws_path):
        return {"ok": False, "reason": f"WS file not found: {ws_path}"}

    try:
        with open(backtest_path, "r", encoding="utf-8") as f:
            bt_data = json.load(f)
        
        history = defaultdict(list)
        with open(ws_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                    if ev.get("event_type") == "trade":
                        raw = ev.get("raw", {})
                        p = float(raw.get("trade_price", raw.get("tp", 0.0)))
                        t = float(ev.get("received_at", 0.0))
                        m = ev.get("market")
                        if m and p > 0:
                            history[m].append((t, p))
                except: continue
        
        for m in history:
            history[m].sort(key=lambda x: x[0])

    except Exception as e:
        return {"ok": False, "reason": f"Failed to load data: {e}"}

    # Use all results
    all_results = bt_data.get("all_results", [])
    candidates = [r for r in all_results if r.get("total_score", 0) >= 60]
    
    if not candidates:
        return {"ok": False, "reason": "No candidates found (score >= 60)"}

    diag_results = []
    windows = [5, 10, 15, 30, 60]
    
    for cand in candidates:
        m = cand.get("market")
        t_entry = cand.get("ts")
        score = cand.get("total_score", 0)
        if not m or not t_entry or m not in history: continue
        
        entry_idx = -1
        p_entry = 0
        for i, (t, p) in enumerate(history[m]):
            if t >= t_entry:
                entry_idx = i
                p_entry = p
                break
        if entry_idx == -1: continue
        
        cand_diag = {
            "market": m,
            "ts": t_entry,
            "score": score,
            "p_entry": p_entry,
            "windows": {}
        }
        
        for w in windows:
            t_max = t_entry + w
            sub_history = []
            for i in range(entry_idx, len(history[m])):
                t, p = history[m][i]
                if t > t_max: break
                sub_history.append(p)
            
            if not sub_history:
                mfe = 0
                mae = 0
                final_ret = 0
            else:
                mfe = (max(sub_history) - p_entry) / p_entry * 100
                mae = (min(sub_history) - p_entry) / p_entry * 100
                final_ret = (sub_history[-1] - p_entry) / p_entry * 100
            
            cand_diag["windows"][w] = {
                "mfe": round(mfe, 4),
                "mae": round(mae, 4),
                "final": round(final_ret, 4),
                "pass_020": mfe >= 0.20,
                "pass_025": mfe >= 0.25,
                "pass_030": mfe >= 0.30
            }
            
        diag_results.append(cand_diag)

    # Multi-threshold aggregates
    thresh_diag = {}
    for thresh in [60, 70, 80]:
        t_cands = [r for r in diag_results if r["score"] >= thresh]
        w_summary = {}
        for w in windows:
            mfes = [r["windows"][w]["mfe"] for r in t_cands]
            w_summary[f"{w}s"] = {
                "count": len(t_cands),
                "mfe": calculate_percentiles(mfes),
                "pass_counts": {
                    "020": sum(1 for r in t_cands if r["windows"][w]["pass_020"]),
                    "025": sum(1 for r in t_cands if r["windows"][w]["pass_025"]),
                    "030": sum(1 for r in t_cands if r["windows"][w]["pass_030"])
                }
            }
        thresh_diag[str(thresh)] = w_summary

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "total_analyzed": len(diag_results),
        "threshold_diagnostics": thresh_diag,
        "top_20_sample": diag_results[:20],
        "details": diag_results
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== Net Edge Candidate Diagnostics (All Candidates) ===\n")
        f.write(f"Generated At: {report['generated_at']}\n")
        f.write(f"Total Candidates Analyzed: {len(diag_results)}개\n\n")
        
        for thresh in [60, 70, 80]:
            f.write(f"--- [Threshold {thresh} Diagnostics] ---\n")
            stats = thresh_diag[str(thresh)]
            f.write(f"Count: {stats['30s']['count']}개\n")
            for w in [30, 60]:
                s = stats[f"{w}s"]
                f.write(f"  {w}s MFE: Avg {s['mfe']['mean']:.4f}%, P90 {s['mfe']['p90']:.4f}%, Max {s['mfe']['max']:.4f}%\n")
                f.write(f"  {w}s Pass: 0.20%({s['pass_counts']['020']}회), 0.25%({s['pass_counts']['025']}회), 0.30%({s['pass_counts']['030']}회)\n")
            f.write("\n")
            
        f.write("--- [Note] ---\n")
        f.write("1. Analysis includes ALL candidates matching thresholds.\n")
        f.write("2. [CAUTION] Settings are for analysis and not auto-applied.\n")

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--backtest", required=True)
    parser.add_argument("--net-edge-sim", required=True)
    parser.add_argument("--ws", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_net_edge_candidate_diagnostics(args.opportunity, args.backtest, args.net_edge_sim, args.ws, args.output_json, args.output_txt)
