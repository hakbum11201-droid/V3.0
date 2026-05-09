import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

def run_soft_score_net_edge_sim(opportunity_path, backtest_path, candidate_path, ws_path, output_json, output_txt):
    if not os.path.exists(opportunity_path):
        return {"ok": False, "reason": f"Opportunity file not found: {opportunity_path}"}
    if not os.path.exists(backtest_path):
        return {"ok": False, "reason": f"Backtest file not found: {backtest_path}"}
    if not os.path.exists(ws_path):
        return {"ok": False, "reason": f"WS file not found: {ws_path}"}

    try:
        with open(opportunity_path, "r", encoding="utf-8") as f:
            opp_data = json.load(f)
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

    fee_rate = 0.0005 
    slippage_rate = 0.0005 
    try:
        with open("config/config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
            fee_rate = cfg.get("risk", {}).get("fee_rate", 0.0005)
            slippage_rate = cfg.get("risk", {}).get("slippage_pct", 0.05) / 100.0
    except: pass

    # Analyze ALL candidates from all_results
    all_results = bt_data.get("all_results", [])
    candidates = [r for r in all_results if r.get("total_score", 0) >= 60]
    
    sim_results = []
    missing_future_price_count = 0
    valid_future_price_count = 0
    total_tick_count = 0
    
    for cand in candidates:
        m = cand.get("market")
        t_entry = cand.get("ts")
        score = cand.get("total_score", 0)
        if not m or not t_entry or m not in history: continue
        
        p_entry = 0
        entry_idx = -1
        for i, (t, p) in enumerate(history[m]):
            if t >= t_entry:
                p_entry = p
                entry_idx = i
                break
        if p_entry == 0:
            missing_future_price_count += 1
            continue
        
        windows = [5, 10, 15, 30, 60]
        p_exits = {}
        for w in windows:
            t_target = t_entry + w
            p_exit = 0
            ticks_found = 0
            for i in range(entry_idx, len(history[m])):
                t, p = history[m][i]
                if t >= t_target:
                    p_exit = p
                    ticks_found = i - entry_idx
                    break
            if p_exit == 0: 
                p_exit = history[m][-1][1]
                ticks_found = len(history[m]) - 1 - entry_idx
            
            p_exits[w] = p_exit
            total_tick_count += ticks_found

        valid_future_price_count += 1
        spread_cost_pct = 0.05 
        costs_total_pct = (fee_rate * 2 * 100) + (spread_cost_pct) + (slippage_rate * 100)
        
        cand_perf = {
            "market": m,
            "ts": t_entry,
            "score": score,
            "p_entry": p_entry,
            "costs_pct": costs_total_pct,
            "windows": {}
        }
        
        for w, p_exit in p_exits.items():
            gross_pnl = (p_exit - p_entry) / p_entry * 100
            net_pnl = gross_pnl - costs_total_pct
            cand_perf["windows"][w] = {
                "gross": round(gross_pnl, 4),
                "net": round(net_pnl, 4),
                "win": net_pnl > 0
            }
        
        sim_results.append(cand_perf)

    # Threshold comparison logic
    thresh_summary = {}
    for thresh in [60, 70, 80]:
        t_cands = [r for r in sim_results if r["score"] >= thresh]
        w_stats = {}
        for w in [5, 10, 15, 30, 60]:
            nets = [r["windows"][w]["net"] for r in t_cands]
            wins = [r["windows"][w]["win"] for r in t_cands]
            w_stats[f"{w}s"] = {
                "count": len(t_cands),
                "win_rate": (sum(wins) / len(wins) * 100) if wins else 0,
                "avg_net_pnl": (sum(nets) / len(nets)) if nets else 0
            }
        thresh_summary[str(thresh)] = w_stats

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "total_candidates_analyzed": len(sim_results),
        "missing_future_price_count": missing_future_price_count,
        "valid_future_price_count": valid_future_price_count,
        "avg_future_tick_count": (total_tick_count / (valid_future_price_count * 5)) if valid_future_price_count > 0 else 0,
        "threshold_comparison": thresh_summary,
        "top_20_sample": sim_results[:20]
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== Soft Score Net Edge Simulation Report (All Candidates) ===\n")
        f.write(f"Generated At: {report['generated_at']}\n")
        f.write(f"Total Candidates (>= 60): {len(sim_results)}개\n")
        f.write(f"Valid Candidates Analyzed: {valid_future_price_count}개\n")
        f.write(f"Missing Future Price: {missing_future_price_count}개\n\n")
        
        for thresh in [60, 70, 80]:
            f.write(f"--- [Threshold {thresh} Stats] ---\n")
            stats = thresh_summary[str(thresh)]
            f.write(f"Candidate Count: {stats['5s']['count']}개\n")
            for w in [5, 10, 15, 30, 60]:
                s = stats[f"{w}s"]
                f.write(f"  {w}s: WinRate {s['win_rate']:.2f}%, AvgNetPnL {s['avg_net_pnl']:.4f}%\n")
            f.write("\n")
            
        f.write("--- [Note] ---\n")
        f.write("1. Statistics above are based on ALL candidates matching each threshold.\n")
        f.write("2. The Top 20 samples in JSON are for reference only.\n")
        f.write("3. [CAUTION] Config is not automatically updated.\n")

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--backtest", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--ws", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_soft_score_net_edge_sim(args.opportunity, args.backtest, args.candidate, args.ws, args.output_json, args.output_txt)
