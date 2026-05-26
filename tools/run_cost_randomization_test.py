"""
run_cost_randomization_test.py

거래 비용 랜덤화 테스트 (Cost Randomization Test)
Reversal Edge v2 전략의 순수익이 작아 슬리피지/체결 비용이 증가했을 때
전략이 무너지는지(Fragility) 확인하기 위한 시나리오 분석 도구.
"""

import os
import json
import subprocess
import sqlite3
import argparse
from datetime import datetime

# Import cache_manager
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import cache_manager

# =============================================================================
# Constants & Configuration
# =============================================================================
INPUT_CANDIDATE = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"

INPUT_JSONL_FILES = [
    "logs/experiments/master/reversal_edge_master_dataset.jsonl",
    "logs/paper/reversal_edge_v2_paper_24h_events.jsonl",
    "logs/experiments/reversal_oos_chunks_merged.jsonl",
    "logs/experiments/reversal_oos_chunks_test_merged.jsonl"
]

REPORTS_DIR = "reports/experiments"

BASE_COST_PCT = 0.20
COST_SCENARIOS = [
    {"name": "Base (0.20%)", "cost_pct": 0.20},
    {"name": "Slight Slippage (0.22%)", "cost_pct": 0.22},
    {"name": "Moderate Slippage (0.25%)", "cost_pct": 0.25},
    {"name": "High Slippage (0.30%)", "cost_pct": 0.30},
    {"name": "Extreme Slippage (0.35%)", "cost_pct": 0.35}
]

# =============================================================================
# Functions
# =============================================================================

def find_input_file_or_cache(filepaths, market_filter="ALL"):
    cache_path = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
    used_cache = False
    temp_jsonl = "logs/experiments/temp_cost_randomization.jsonl"
    
    if os.path.exists(cache_path):
        print(f"[Info] Found SQLite cache at {cache_path}. Extracting data...")
        try:
            conn = sqlite3.connect(cache_path)
            cursor = conn.cursor()
            if market_filter == "ALL":
                cursor.execute("SELECT raw_json FROM events ORDER BY ts ASC")
            else:
                cursor.execute("SELECT raw_json FROM events WHERE market=? ORDER BY ts ASC", (market_filter,))
                
            rows = cursor.fetchall()
            lines = len(rows)
            
            with open(temp_jsonl, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(row[0] + "\n")
                    
            conn.close()
            print(f"[Info] Extracted {lines} rows from cache to {temp_jsonl}")
            return temp_jsonl, lines, True
        except Exception as e:
            print(f"[Warning] Failed to use SQLite cache: {e}. Falling back to JSONL.")
            
    for fp in filepaths:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            lines = 0
            try:
                with open(temp_jsonl, "w", encoding="utf-8") as out_f:
                    with open(fp, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip(): continue
                            if market_filter != "ALL":
                                try:
                                    data = json.loads(line)
                                    market = data.get("market") or data.get("code") or (data.get("raw", {}).get("code"))
                                    if market != market_filter: continue
                                except: pass
                            out_f.write(line)
                            lines += 1
            except Exception as e:
                print(f"[Warning] Error filtering {fp}: {e}")
                pass
            if lines > 0:
                return temp_jsonl, lines, False
    return None, 0, False

def run_base_backtest(input_jsonl):
    out_json = os.path.join(REPORTS_DIR, "cost_randomization_base_summary.json")
    out_txt = os.path.join(REPORTS_DIR, "cost_randomization_base_summary.txt")
    
    cmd = [
        "python", "-m", "coinb.main", "reversal-edge-backtest",
        "--ws", input_jsonl,
        "--candidate", INPUT_CANDIDATE,
        "--output-json", out_json,
        "--output-txt", out_txt
    ]
    
    print(f"[Info] Running baseline backtest on {input_jsonl}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[Warning] Backtest failed: {e}")
        return None
        
    if not os.path.exists(out_json):
        print("[Warning] JSON output not found after backtest.")
        return None
        
    try:
        with open(out_json, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Failed to load summary JSON: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="ALL", help="Specific market to filter, default ALL")
    args = parser.parse_args()
    
    print("============================================================")
    print(" Cost Randomization Test for Reversal Edge v2")
    print(f" Market Filter: {args.market}")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 0. Ensure cache is valid
    print("[Info] Checking Master Dataset Cache...")
    cache_success, cache_reason = cache_manager.ensure_cache()
    if not cache_success:
        print(f"[Warning] Cache manager returned {cache_reason}. Will attempt fallback to JSONL.")
    
    # 1. Find Data
    input_file, total_lines, used_cache = find_input_file_or_cache(INPUT_JSONL_FILES, args.market)
    
    if not input_file or total_lines == 0:
        print("[Error] No valid input events loaded. Cannot perform test.")
        _write_empty_summary("파일을 찾을 수 없거나 파일 내용이 비어있습니다.", None, 0, False, args.market)
        return
        
    # 2. Run Baseline Backtest
    base_summary = run_base_backtest(input_file)
    
    if not base_summary:
        print("[Error] Baseline backtest failed.")
        _write_empty_summary("Baseline 백테스트 실행에 실패했습니다.", input_file, total_lines, used_cache, args.market)
        return
        
    trades = base_summary.get("total_trades", base_summary.get("paper_entries", 0))
    original_net_pnl = base_summary.get("net_pnl_pct", base_summary.get("avg_net_pnl_pct", 0.0))
    win_rate = base_summary.get("win_rate", 0.0)
    
    if trades == 0:
        print("[Info] No trades occurred. Need more data.")
        _write_empty_summary("파일은 읽었지만 조건 미발생 (Trades = 0)", input_file, total_lines, used_cache, args.market)
        return
        
    # 3. Apply Cost Scenarios
    scenario_results = []
    
    for sc in COST_SCENARIOS:
        additional_cost = sc["cost_pct"] - BASE_COST_PCT
        adjusted_pnl = original_net_pnl - additional_cost
        
        if adjusted_pnl > 0:
            if sc["cost_pct"] >= 0.25:
                judgement = "ROBUST"
            else:
                judgement = "SURVIVES_COST"
        else:
            judgement = "FAILS_COST"
            
        res = {
            "scenario_name": sc["name"],
            "cost_pct": sc["cost_pct"],
            "base_cost_pct": BASE_COST_PCT,
            "additional_cost_pct": round(additional_cost, 4),
            "trades": trades,
            "original_avg_net_pnl_pct": round(original_net_pnl, 4),
            "adjusted_avg_net_pnl_pct": round(adjusted_pnl, 4),
            "win_rate": round(win_rate, 2),
            "judgement": judgement
        }
        scenario_results.append(res)
        
    # 4. Determine Final Judgement
    robust_count = sum(1 for r in scenario_results if r["judgement"] == "ROBUST")
    survives_count = sum(1 for r in scenario_results if r["judgement"] in ("SURVIVES_COST", "ROBUST"))
    
    if robust_count > 0:
        final_judgement = "ROBUST_TO_COST"
    elif survives_count > 1: # Base + 0.22% survive
        final_judgement = "SURVIVES_BASE_ONLY"
    elif survives_count == 1: # Only Base survives
        final_judgement = "FRAGILE_EDGE"
    else:
        final_judgement = "FAILED"
        
    # 5. Output Results
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "input_file": input_file,
        "used_sqlite_cache": used_cache,
        "cache_rebuilt": cache_reason == "cache_rebuilt",
        "cache_valid": cache_success,
        "cache_rows": total_lines if used_cache else 0,
        "source_jsonl_path": cache_manager.MASTER_JSONL,
        "market_filter": args.market,
        "input_lines": total_lines,
        "candidate": INPUT_CANDIDATE,
        "final_judgement": final_judgement,
        "base_trades": trades,
        "base_win_rate": round(win_rate, 2),
        "scenarios": scenario_results
    }
    
    json_path = os.path.join(REPORTS_DIR, "cost_randomization_test_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "cost_randomization_test_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  거래 비용 랜덤화 테스트 (Cost Randomization Test)",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        f"입력 파일: {input_file} (라인 수: {total_lines})",
        f"SQLite 캐시 사용: {used_cache}",
        f"자동 Rebuild 수행: {cache_reason == 'cache_rebuilt'}",
        f"캐시 정상 판단: {cache_success}",
        f"읽은 캐시 Row: {total_lines if used_cache else 0}",
        f"원본 JSONL 소스: {cache_manager.MASTER_JSONL}",
        f"Market 필터: {args.market}",
        f"사용 후보: {INPUT_CANDIDATE}",
        "",
        "[비용 시나리오별 결과]",
        "| 시나리오 | 적용비용 | 추가비용 | Trades | 원본 PnL | 조정 PnL | 승률 | 판단 |",
        "|:---|:---|:---|:---|:---|:---|:---|:---|"
    ]
    
    for r in scenario_results:
        txt_lines.append(
            f"| {r['scenario_name']} | {r['cost_pct']:.2f}% | {r['additional_cost_pct']:+.2f}% | "
            f"{r['trades']} | {r['original_avg_net_pnl_pct']:+.4f}% | "
            f"{r['adjusted_avg_net_pnl_pct']:+.4f}% | {r['win_rate']:.2f}% | {r['judgement']} |"
        )
        
    txt_lines.extend([
        "",
        "[최종 진단 결과]",
        f" 🎯 최종 판단 : {final_judgement}",
        "",
        "[다음 행동 제안]"
    ])
    
    if final_judgement == "ROBUST_TO_COST":
        txt_lines.append(" - 전략의 엣지가 견고합니다. 3D Paper 등 다음 검증 단계로 넘어가십시오.")
    elif final_judgement == "SURVIVES_BASE_ONLY":
        txt_lines.append(" - 비용 증가에 민감합니다. 슬리피지를 최소화할 수 있는 체결 개선 로직을 연구하십시오.")
    elif final_judgement == "FRAGILE_EDGE":
        txt_lines.append(" - 엣지가 매우 취약합니다. 현재 상태로는 실거래 시 손실 위험이 큽니다. 전략 파라미터를 전면 재조정하십시오.")
    else:
        txt_lines.append(" - 전략이 비용을 감당하지 못합니다. Candidate를 전면 폐기하거나 새로운 아이디어를 구상하십시오.")
        
    txt_lines.extend([
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 실거래 반영 금지",
        " 🚫 config 자동 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 사람 승인 전 tiny_live 금지",
        "------------------------------------------------------------"
    ])
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print(f"\n[Done] Final Judgement: {final_judgement}")
    print(f"Report saved to: {txt_path}")

def _write_empty_summary(reason, input_file=None, total_lines=0, used_cache=False, market_filter="ALL"):
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "input_file": input_file,
        "used_sqlite_cache": used_cache,
        "market_filter": market_filter,
        "input_lines": total_lines,
        "final_judgement": "NEED_MORE_DATA",
        "reason": reason
    }
    json_path = os.path.join(REPORTS_DIR, "cost_randomization_test_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "cost_randomization_test_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("거래 비용 랜덤화 테스트 Report\n")
        if input_file:
            f.write(f"입력 파일: {input_file} (라인 수: {total_lines})\n")
            f.write(f"SQLite 캐시 사용: {used_cache}\n")
            f.write(f"Market 필터: {market_filter}\n")
        f.write(f"결과: NEED_MORE_DATA ({reason})\n")
        f.write("------------------------------------------------------------\n")
        f.write(" 🚫 실거래 반영 금지\n")
        f.write(" 🚫 config 자동 반영 금지\n")
        f.write(" 🚫 live.enabled=false 유지\n")
        f.write(" 🚫 사람 승인 전 tiny_live 금지\n")

if __name__ == "__main__":
    main()
