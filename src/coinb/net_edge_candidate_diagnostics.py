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

    candidates = bt_data.get("top_candidates", [])
    if not candidates:
        return {"ok": False, "reason": "No candidates found in backtest data"}

    diag_results = []
    windows = [5, 10, 15, 30, 60]
    
    for cand in candidates:
        m = cand.get("market")
        t_entry = cand.get("ts")
        score = cand.get("total_score", 0)
        if not m or not t_entry or m not in history: continue
        
        # Find entry price index
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

    # Aggregates
    summary = {}
    for w in windows:
        mfes = [r["windows"][w]["mfe"] for r in diag_results]
        maes = [r["windows"][w]["mae"] for r in diag_results]
        finals = [r["windows"][w]["final"] for r in diag_results]
        
        summary[f"{w}s"] = {
            "mfe": calculate_percentiles(mfes),
            "mae": calculate_percentiles(maes),
            "final": calculate_percentiles(finals),
            "pass_counts": {
                "020": sum(1 for r in diag_results if r["windows"][w]["pass_020"]),
                "025": sum(1 for r in diag_results if r["windows"][w]["pass_025"]),
                "030": sum(1 for r in diag_results if r["windows"][w]["pass_030"])
            }
        }

    # Score vs MFE relationship
    # Group by score 70-80 and 80+
    score_groups = {"70-80": [], "80+": []}
    for r in diag_results:
        mfe_30s = r["windows"][30]["mfe"]
        if r["score"] >= 80: score_groups["80+"].append(mfe_30s)
        elif r["score"] >= 70: score_groups["70-80"].append(mfe_30s)

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "candidate_count": len(diag_results),
        "window_summary": summary,
        "score_correlation": {
            "70-80_mfe_avg": (sum(score_groups["70-80"]) / len(score_groups["70-80"])) if score_groups["70-80"] else 0,
            "80+_mfe_avg": (sum(score_groups["80+"]) / len(score_groups["80+"])) if score_groups["80+"] else 0
        },
        "details": diag_results
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== Net Edge 후보 상세 진단 리포트 (MFE/MAE 분석) ===\n")
        f.write(f"분석 일시: {report['generated_at']}\n")
        f.write(f"분석 대상 후보 수: {len(diag_results)}개\n\n")
        
        f.write("--- [보유 시간별 MFE 분포 (Gross 상승폭)] ---\n")
        for w in windows:
            s = summary[f"{w}s"]["mfe"]
            pc = summary[f"{w}s"]["pass_counts"]
            f.write(f"[{w}초 보유]\n")
            f.write(f"  - 평균 MFE: {s['mean']:.4f}% / P90: {s['p90']:.4f}% / MAX: {s['max']:.4f}%\n")
            f.write(f"  - 비용 기준 통과 수: 0.20%({pc['020']}회), 0.25%({pc['025']}회), 0.30%({pc['030']}회)\n")
        
        f.write("\n--- [점수와 MFE의 관계] ---\n")
        f.write(f"- Score 70~80 후보 평균 MFE (30s): {report['score_correlation']['70-80_mfe_avg']:.4f}%\n")
        f.write(f"- Score 80 이상 후보 평균 MFE (30s): {report['score_correlation']['80+_mfe_avg']:.4f}%\n\n")
        
        f.write("--- [진단 결론] ---\n")
        total_020 = sum(summary[f"{w}s"]["pass_counts"]["020"] for w in windows)
        if total_020 > 0:
            f.write("1. 일부 후보에서 0.20% 이상의 상승(MFE)이 관찰됨. 비용을 극복할 가능성이 있는 구간이 존재함.\n")
        else:
            f.write("1. 모든 후보에서 MFE가 0.20%에 미달함. 현재 가중치와 진입 기준으로는 수수료를 이기기 어려움.\n")
            
        f.write("2. Soft Score v1을 그대로 반영하기에는 '순수익(Net Edge)' 확보 능력이 부족함.\n")
        f.write("3. 다음 실험 방향: Threshold를 80 이상으로 상향하거나, Sweep/Cont 가중치를 높여 변동성이 큰 구간만 선별해야 함.\n")
        
        f.write("\n4. [주의] 본 시뮬레이션 결과는 config에 자동 반영되지 않습니다.\n")
        f.write("5. 실거래 반영 전, 실제 시장 상황에서의 추가적인 Paper 실험이 반드시 필요합니다.\n")

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
