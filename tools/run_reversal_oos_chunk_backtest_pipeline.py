"""
run_reversal_oos_chunk_backtest_pipeline.py
End-to-End Pipeline for Reversal Edge v2 OOS Chunk Data.

Steps:
1. Merge OOS chunks using tools/merge_ws_chunks.py.
2. Run reversal-edge-backtest with the merged JSONL and a candidate config.
3. Generate a pipeline summary evaluating the final OOS performance.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[Pipeline] {ts}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[Pipeline] {ts}  {msg}".encode("ascii", errors="replace").decode(), flush=True)

def run_subprocess(cmd: list) -> tuple:
    """Run a subprocess and return (success, returncode, stderr)."""
    try:
        log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"Process failed with code {result.returncode}")
            if result.stderr:
                log(f"STDERR:\n{result.stderr.strip()}")
        else:
            log("Process completed successfully.")
            # Print stdout if needed, but could be large. 
            # if result.stdout:
            #     log(result.stdout.strip())
        return result.returncode == 0, result.returncode, result.stderr
    except Exception as e:
        log(f"Subprocess exception: {e}")
        return False, -1, str(e)

def determine_final_judgement(backtest_json_path: str) -> str:
    if not os.path.exists(backtest_json_path):
        return "FAILED (No backtest summary found)"
    try:
        with open(backtest_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        trades = data.get("total_trades", 0)
        if trades == 0:
            return "NEED_MORE_DATA (Trades 0)"
            
        net_pnl = data.get("net_pnl_pct", 0.0)
        if net_pnl > 0:
            return "PROMISING_BUT_PAPER_REQUIRED (Net PnL > 0)"
        else:
            return "HOLD_AND_ANALYZE_FAILURES (Net PnL <= 0)"
    except Exception as e:
        return f"FAILED (Error parsing backtest summary: {e})"

def main():
    parser = argparse.ArgumentParser(description="Reversal Edge OOS Chunk Backtest Pipeline")
    
    # Input arguments
    parser.add_argument("--input-dir", type=str, default="logs/experiments/chunks")
    parser.add_argument("--manifest", type=str, default="logs/experiments/chunks/reversal_oos_chunk_manifest.jsonl")
    parser.add_argument("--candidate", type=str, default="configs/experiments/reversal_edge_candidate_v2_from_36h.json")
    
    # Merge output arguments
    parser.add_argument("--merged-output", type=str, default="logs/experiments/reversal_oos_chunks_merged.jsonl")
    parser.add_argument("--merge-summary-json", type=str, default="reports/experiments/reversal_oos_chunk_merge_summary.json")
    parser.add_argument("--merge-summary-txt", type=str, default="reports/experiments/reversal_oos_chunk_merge_summary.txt")
    
    # Backtest output arguments
    parser.add_argument("--backtest-summary-json", type=str, default="reports/experiments/reversal_oos_chunk_backtest_summary.json")
    parser.add_argument("--backtest-summary-txt", type=str, default="reports/experiments/reversal_oos_chunk_backtest_summary.txt")
    
    # Pipeline output arguments
    parser.add_argument("--pipeline-summary-json", type=str, default="reports/experiments/reversal_oos_chunk_pipeline_summary.json")
    parser.add_argument("--pipeline-summary-txt", type=str, default="reports/experiments/reversal_oos_chunk_pipeline_summary.txt")
    
    args = parser.parse_args()
    start_time = time.time()
    run_time = datetime.now().isoformat()

    log("=== STARTING OOS CHUNK BACKTEST PIPELINE ===")
    
    # Pre-checks
    if not os.path.exists(args.candidate):
        log(f"ERROR: Candidate file not found: {args.candidate}")
        sys.exit(1)

    # 1. Run Merge
    merge_cmd = [
        sys.executable, "tools/merge_ws_chunks.py",
        "--input-dir", args.input_dir,
        "--manifest", args.manifest,
        "--output", args.merged_output,
        "--summary-json", args.merge_summary_json,
        "--summary-txt", args.merge_summary_txt
    ]
    
    log(">>> STEP 1: Merging OOS Chunks")
    merge_success, merge_rc, merge_stderr = run_subprocess(merge_cmd)
    
    if not merge_success:
        log("ERROR: Merge step failed. Aborting pipeline.")
        backtest_success = False
        final_judgement = "FAILED (Merge Error)"
    elif not os.path.exists(args.merged_output):
        log("ERROR: Merged output file not found. Aborting pipeline.")
        merge_success = False
        backtest_success = False
        final_judgement = "FAILED (Merged file missing)"
    else:
        # 2. Run Backtest
        backtest_cmd = [
            sys.executable, "-m", "coinb.main",
            "reversal-edge-backtest",
            "--ws", args.merged_output,
            "--candidate", args.candidate,
            "--output-json", args.backtest_summary_json,
            "--output-txt", args.backtest_summary_txt
        ]
        
        log(">>> STEP 2: Running Reversal Edge Backtest")
        backtest_success, bt_rc, bt_stderr = run_subprocess(backtest_cmd)
        
        log(">>> STEP 3: Evaluating Results")
        final_judgement = determine_final_judgement(args.backtest_summary_json)

    # 3. Generate Pipeline Summary
    log(">>> STEP 4: Generating Pipeline Summary")
    
    pipeline_data = {
        "run_time": run_time,
        "input_dir": args.input_dir,
        "manifest_path": args.manifest,
        "candidate_path": args.candidate,
        "merged_jsonl_path": args.merged_output,
        "merge_success": merge_success,
        "backtest_success": backtest_success,
        "merge_summary_json": args.merge_summary_json,
        "backtest_summary_json": args.backtest_summary_json,
        "final_judgement": final_judgement
    }
    
    os.makedirs(os.path.dirname(args.pipeline_summary_json), exist_ok=True)
    try:
        with open(args.pipeline_summary_json, "w", encoding="utf-8") as f:
            json.dump(pipeline_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Error writing pipeline summary JSON: {e}")

    summary_txt_lines = [
        "=" * 60,
        "  Reversal Edge v2 OOS Pipeline Summary",
        "=" * 60,
        f"실행 시각        : {run_time}",
        f"입력 디렉토리    : {args.input_dir}",
        f"매니페스트       : {args.manifest}",
        f"후보 전략 파일   : {args.candidate}",
        f"병합 데이터 파일 : {args.merged_output}",
        "",
        f"Merge 성공 여부  : {merge_success}",
        f"Backtest 성공 여부: {backtest_success}",
        "",
        f"최종 판단 결과   : {final_judgement}",
        "",
        "--- [안전 경고] ---",
        "🚫 실거래 반영 금지: 본 결과는 OOS 백테스트 결과일 뿐입니다.",
        "항상 관리자(사람)의 승인 및 Paper 검증(72h 이상)이 필요합니다.",
        "live.enabled=false 상태를 유지하십시오."
    ]
    
    try:
        with open(args.pipeline_summary_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_txt_lines) + "\n")
    except Exception as e:
        log(f"Error writing pipeline summary TXT: {e}")
        
    log("=== PIPELINE FINISHED ===")
    log(f"Final Judgement: {final_judgement}")


if __name__ == "__main__":
    main()
