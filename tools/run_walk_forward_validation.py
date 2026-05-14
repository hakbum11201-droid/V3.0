"""
run_walk_forward_validation.py

Splits available event logs into time-based folds to perform Walk-forward Validation
(Rolling Out-of-Sample testing) for the Reversal Edge strategy.
"""

import os
import json
import subprocess
import glob
from datetime import datetime

# =============================================================================
# Constants & Configuration
# =============================================================================
INPUT_CANDIDATE = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"

INPUT_JSONL_FILES = [
    "logs/experiments/master/reversal_edge_master_dataset.jsonl",
    "logs/paper/reversal_edge_v2_paper_24h_events.jsonl",
    "logs/experiments/reversal_oos_chunks_merged.jsonl",
    "logs/experiments/reversal_oos_chunks_test_merged.jsonl",
    "logs/paper/reversal_edge_v2_paper_events.jsonl"
]

OUT_DIR = "logs/experiments/walk_forward"
REPORTS_DIR = "reports/experiments"

TRAIN_WINDOW_SEC = 36 * 3600  # 129600
TEST_WINDOW_SEC = 24 * 3600   # 86400
STEP_SEC = 24 * 3600          # 86400

# =============================================================================
# Functions
# =============================================================================

def get_timestamp(data):
    for key in ["timestamp", "trade_timestamp", "ts", "timestamp_ms", "received_at"]:
        if key in data:
            return float(data[key])
    if "raw" in data and isinstance(data["raw"], dict):
        for key in ["timestamp", "trade_timestamp", "ts"]:
            if key in data["raw"]:
                return float(data["raw"][key])
    return None

def load_and_sort_events(filepaths):
    """Load events from the highest priority file that has data."""
    events = []
    used_file = None
    parsed_success = 0
    total_lines = 0
    
    for fp in filepaths:
        if not os.path.exists(fp) or os.path.getsize(fp) == 0:
            print(f"[Info] File not found or empty, skipping: {fp}")
            continue
            
        print(f"[Info] Reading {fp}...")
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total_lines += 1
                    try:
                        data = json.loads(line)
                        ts = get_timestamp(data)
                        if ts is not None:
                            # Normalize MS timestamps if necessary
                            if ts > 1e11:
                                ts = ts / 1000.0
                            events.append((ts, line))
                            parsed_success += 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[Warning] Error reading {fp}: {e}")
            
        if len(events) > 0:
            used_file = fp
            break
            
    print(f"[Info] Total lines read: {total_lines}, Parsed success: {parsed_success}")
    if events:
        events.sort(key=lambda x: x[0])
    return events, used_file, total_lines, parsed_success


def run_backtest_on_fold(fold_idx, test_jsonl_path):
    """Run reversal-edge-backtest on a specific fold's jsonl file."""
    out_json = os.path.join(REPORTS_DIR, f"walk_forward_fold_{fold_idx:04d}_summary.json")
    out_txt = os.path.join(REPORTS_DIR, f"walk_forward_fold_{fold_idx:04d}_summary.txt")
    
    cmd = [
        "python", "-m", "coinb.main", "reversal-edge-backtest",
        "--ws", test_jsonl_path,
        "--candidate", INPUT_CANDIDATE,
        "--output-json", out_json,
        "--output-txt", out_txt
    ]
    
    print(f"[Fold {fold_idx:04d}] Running backtest...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[Fold {fold_idx:04d}] Backtest failed: {e}")
        return None
        
    if not os.path.exists(out_json):
        print(f"[Fold {fold_idx:04d}] JSON output not found.")
        return None
        
    try:
        with open(out_json, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Fold {fold_idx:04d}] Failed to load summary JSON: {e}")
        return None


def determine_fold_status(fold_summary, test_event_count):
    if not fold_summary:
        return "FAIL"
        
    trades = fold_summary.get("total_trades", fold_summary.get("paper_entries", 0))
    net_pnl = fold_summary.get("net_pnl_pct", fold_summary.get("avg_net_pnl_pct", 0.0))
    
    if test_event_count < 1000 or trades == 0:
        return "NEED_MORE_DATA"
        
    if net_pnl > 0:
        return "PASS"
    else:
        return "FAIL"


def main():
    print("============================================================")
    print(" Walk-forward Validation for Reversal Edge")
    print("============================================================")
    
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 1. Load data
    events, used_file, total_lines, parsed_success = load_and_sort_events(INPUT_JSONL_FILES)
    if not events:
        print("[Error] No events loaded. Cannot perform validation.")
        _write_empty_summary()
        return

    min_ts = events[0][0]
    max_ts = events[-1][0]
    total_duration = max_ts - min_ts
    
    print(f"[Info] Using file: {used_file}")
    print(f"[Info] Time range: {datetime.fromtimestamp(min_ts)} ~ {datetime.fromtimestamp(max_ts)}")
    print(f"[Info] Total duration: {total_duration/3600:.2f} hours")
    
    # 2. Create folds
    folds = []
    current_start = min_ts
    fold_idx = 1
    
    while current_start + TRAIN_WINDOW_SEC + TEST_WINDOW_SEC <= max_ts:
        train_start = current_start
        train_end = current_start + TRAIN_WINDOW_SEC
        test_start = train_end
        test_end = test_start + TEST_WINDOW_SEC
        
        # Extract test events
        test_lines = [ev[1] for ev in events if test_start <= ev[0] < test_end]
        
        fold_test_path = os.path.join(OUT_DIR, f"fold_{fold_idx:04d}_test.jsonl")
        with open(fold_test_path, "w", encoding="utf-8") as f:
            for line in test_lines:
                f.write(line + "\n")
                
        folds.append({
            "fold_num": fold_idx,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "test_event_count": len(test_lines),
            "test_jsonl": fold_test_path
        })
        
        current_start += STEP_SEC
        fold_idx += 1
        
    print(f"[Info] Generated {len(folds)} folds.")
    
    # 3. Run backtest per fold
    fold_results = []
    pass_count = 0
    fail_count = 0
    nmd_count = 0
    total_net_pnl = 0.0
    total_win_rate = 0.0
    total_trades = 0
    
    for fold in folds:
        summary = run_backtest_on_fold(fold["fold_num"], fold["test_jsonl"])
        status = determine_fold_status(summary, fold["test_event_count"])
        
        trades = 0
        net_pnl = 0.0
        win_rate = 0.0
        
        if summary:
            trades = summary.get("total_trades", summary.get("paper_entries", 0))
            net_pnl = summary.get("net_pnl_pct", summary.get("avg_net_pnl_pct", 0.0))
            win_rate = summary.get("win_rate", 0.0)
            
            total_net_pnl += net_pnl
            total_win_rate += win_rate
            total_trades += trades
            
        if status == "PASS":
            pass_count += 1
        elif status == "FAIL":
            fail_count += 1
        else:
            nmd_count += 1
            
        fold_result = {
            "fold": fold["fold_num"],
            "train_range": f"{datetime.fromtimestamp(fold['train_start'])} ~ {datetime.fromtimestamp(fold['train_end'])}",
            "test_range": f"{datetime.fromtimestamp(fold['test_start'])} ~ {datetime.fromtimestamp(fold['test_end'])}",
            "test_events": fold["test_event_count"],
            "trades": trades,
            "net_pnl_pct": net_pnl,
            "win_rate": win_rate,
            "status": status
        }
        fold_results.append(fold_result)
        
    # 4. Final Aggregation
    num_folds = len(folds)
    avg_net_pnl = total_net_pnl / num_folds if num_folds > 0 else 0.0
    avg_win_rate = total_win_rate / num_folds if num_folds > 0 else 0.0
    
    # Final Judgement
    if num_folds == 0:
        final_judgement = "NEED_MORE_DATA"
    elif nmd_count > num_folds / 2:
        final_judgement = "NEED_MORE_DATA"
    elif pass_count >= num_folds / 2 and avg_net_pnl > 0:
        final_judgement = "PROMISING_BUT_MORE_DATA_REQUIRED"
    elif pass_count > 0 and fail_count > 0 and abs(pass_count - fail_count) <= 2:
        # High variance in results
        final_judgement = "UNSTABLE"
    elif avg_net_pnl < 0:
        final_judgement = "FAILED"
    else:
        final_judgement = "UNSTABLE"
        
    # 5. Output
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "used_input_file": used_file,
        "total_lines_read": total_lines,
        "parsed_success": parsed_success,
        "time_range_start": datetime.fromtimestamp(min_ts).isoformat(),
        "time_range_end": datetime.fromtimestamp(max_ts).isoformat(),
        "total_folds": num_folds,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "need_more_data_count": nmd_count,
        "avg_net_pnl_pct": round(avg_net_pnl, 4),
        "avg_win_rate": round(avg_win_rate, 2),
        "total_trades": total_trades,
        "final_judgement": final_judgement,
        "folds": fold_results
    }
    
    json_path = os.path.join(REPORTS_DIR, "walk_forward_validation_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "walk_forward_validation_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  Walk-forward Validation Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[입력 데이터 파싱 요약]",
        f" - 사용된 파일: {used_file}",
        f" - 총 라인 수 : {total_lines}",
        f" - 파싱 성공  : {parsed_success}",
        f" - 시간 범위  : {datetime.fromtimestamp(min_ts)} ~ {datetime.fromtimestamp(max_ts)}",
        "",
        "[총괄 성과]",
        f" - 총 Fold 수   : {num_folds}",
        f" - 총 거래 수   : {total_trades}",
        f" - 평균 PnL     : {avg_net_pnl:.4f}%",
        f" - 평균 승률    : {avg_win_rate:.2f}%",
        f" - PASS         : {pass_count}",
        f" - FAIL         : {fail_count}",
        f" - 데이터 부족  : {nmd_count}",
        "",
        f"🎯 최종 판단: {final_judgement}",
        "",
        "[Fold별 상세]"
    ]
    
    for fr in fold_results:
        txt_lines.append(f" - Fold {fr['fold']:04d}: {fr['status']} (Trades: {fr['trades']}, PnL: {fr['net_pnl_pct']:.4f}%, Events: {fr['test_events']})")
        txt_lines.append(f"   Test Range: {fr['test_range']}")
        
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
        
    print(f"\n[Done] Judgement: {final_judgement}")
    print(f"Report saved to: {txt_path}")


def _write_empty_summary():
    """Fallback when no data is available."""
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "total_folds": 0,
        "final_judgement": "NEED_MORE_DATA",
        "reason": "입력 데이터(jsonl)가 없거나 부족합니다."
    }
    json_path = os.path.join(REPORTS_DIR, "walk_forward_validation_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "walk_forward_validation_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Walk-forward Validation Report\n")
        f.write("결과: NEED_MORE_DATA (데이터 부족)\n")
        f.write("------------------------------------------------------------\n")
        f.write(" 🚫 실거래 반영 금지\n")
        f.write(" 🚫 config 자동 반영 금지\n")
        f.write(" 🚫 live.enabled=false 유지\n")
        f.write(" 🚫 사람 승인 전 tiny_live 금지\n")


if __name__ == "__main__":
    main()
