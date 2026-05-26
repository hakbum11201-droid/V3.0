"""
run_reversal_candidate_sensitivity.py

Reversal Edge v2 Candidate Sensitivity Analysis Tool
원본 candidate를 수정하지 않고 실험용 candidate를 생성하여
진입 조건 완화 시 trades가 발생하는지 확인한다.
"""

import os
import json
import copy
import sqlite3
import subprocess
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# Constants
# =============================================================================
ORIGINAL_CANDIDATE = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"

SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
MASTER_JSONL = "logs/experiments/master/reversal_edge_master_dataset.jsonl"
TEMP_JSONL_REUSE = "logs/experiments/temp_cost_randomization.jsonl"
TEMP_JSONL_EXTRACT = "logs/experiments/temp_candidate_sensitivity_master.jsonl"

TMP_CANDIDATES_DIR = "reports/experiments/candidate_sensitivity/tmp_candidates"
SENSITIVITY_DIR = "reports/experiments/candidate_sensitivity"
REPORTS_DIR = "reports/experiments"

JSON_REPORT = os.path.join(REPORTS_DIR, "reversal_candidate_sensitivity_latest.json")
TXT_REPORT = os.path.join(REPORTS_DIR, "reversal_candidate_sensitivity_latest.txt")

# =============================================================================
# Experiment Definitions
# =============================================================================
EXPERIMENTS = [
    {
        "name": "A_original",
        "label": "원본 그대로",
        "threshold_candidates": None,   # None = use original
        "cost_floor_pct": None,
    },
    {
        "name": "B_threshold_50_60_70",
        "label": "Threshold 50-60-70 완화",
        "threshold_candidates": [50, 60, 70],
        "cost_floor_pct": None,
    },
    {
        "name": "C_threshold_40_50_60",
        "label": "Threshold 40-50-60 대폭 완화",
        "threshold_candidates": [40, 50, 60],
        "cost_floor_pct": None,
    },
    {
        "name": "D_cost_015",
        "label": "Cost Floor 0.15% 완화",
        "threshold_candidates": None,
        "cost_floor_pct": 0.15,
    },
    {
        "name": "E_cost_010",
        "label": "Cost Floor 0.10% 대폭 완화",
        "threshold_candidates": None,
        "cost_floor_pct": 0.10,
    },
    {
        "name": "F_threshold_50_cost_015",
        "label": "Threshold 50-60-70 + Cost 0.15% 동시 완화",
        "threshold_candidates": [50, 60, 70],
        "cost_floor_pct": 0.15,
    },
    {
        "name": "G_threshold_40_cost_010",
        "label": "Threshold 40-50-60 + Cost 0.10% 대폭 완화",
        "threshold_candidates": [40, 50, 60],
        "cost_floor_pct": 0.10,
    },
]

# =============================================================================
# Helpers
# =============================================================================

def load_original_candidate():
    with open(ORIGINAL_CANDIDATE, "r", encoding="utf-8") as f:
        return json.load(f)

def prepare_tmp_candidate(original, experiment):
    """
    Create a modified candidate dict. Does NOT touch original.
    Returns (candidate_dict, warnings[])
    """
    candidate = copy.deepcopy(original)
    warnings = []

    # Threshold
    if experiment["threshold_candidates"] is not None:
        if "threshold_candidates" in candidate:
            candidate["threshold_candidates"] = experiment["threshold_candidates"]
        else:
            warnings.append("threshold_candidates: key 없음 / 수정 불가")

    # Cost Floor
    if experiment["cost_floor_pct"] is not None:
        if "cost_floor_pct" in candidate:
            candidate["cost_floor_pct"] = experiment["cost_floor_pct"]
        else:
            warnings.append("cost_floor_pct: key 없음 / 수정 불가")

    candidate["_experiment_name"] = experiment["name"]
    candidate["_experiment_label"] = experiment["label"]
    candidate["_generated_at"] = datetime.now().isoformat()
    candidate["auto_apply"] = False  # safety

    return candidate, warnings

def get_master_temp_jsonl():
    """Determine the best temp JSONL to use, extracting from SQLite if needed."""
    # Try reusing temp_cost_randomization.jsonl if it's fresh
    if os.path.exists(TEMP_JSONL_REUSE) and os.path.getsize(TEMP_JSONL_REUSE) > 0:
        sqlite_mtime = os.path.getmtime(SQLITE_CACHE) if os.path.exists(SQLITE_CACHE) else 0
        temp_mtime = os.path.getmtime(TEMP_JSONL_REUSE)
        if temp_mtime >= sqlite_mtime:
            print(f"[Info] Reusing existing temp JSONL: {TEMP_JSONL_REUSE}")
            return TEMP_JSONL_REUSE, "reused"

    # Extract from SQLite
    if os.path.exists(SQLITE_CACHE):
        print(f"[Info] Extracting master data from SQLite cache to {TEMP_JSONL_EXTRACT} ...")
        try:
            conn = sqlite3.connect(SQLITE_CACHE)
            cursor = conn.cursor()
            cursor.execute("SELECT raw_json FROM events ORDER BY ts ASC")
            rows = cursor.fetchall()
            conn.close()
            with open(TEMP_JSONL_EXTRACT, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(row[0] + "\n")
            print(f"[Info] Extracted {len(rows)} rows to {TEMP_JSONL_EXTRACT}")
            return TEMP_JSONL_EXTRACT, "sqlite_extracted"
        except Exception as e:
            print(f"[Warning] SQLite extraction failed: {e}. Falling back to JSONL.")

    # Fallback to master JSONL
    if os.path.exists(MASTER_JSONL) and os.path.getsize(MASTER_JSONL) > 0:
        print(f"[Info] Falling back to master JSONL: {MASTER_JSONL}")
        return MASTER_JSONL, "jsonl_fallback"

    return None, "no_data"

def run_backtest(ws_path, candidate_path, out_json, out_txt):
    """Run the reversal-edge-backtest command via subprocess."""
    cmd = [
        sys.executable, "-m", "coinb.main",
        "reversal-edge-backtest",
        "--ws", ws_path,
        "--candidate", candidate_path,
        "--output-json", out_json,
        "--output-txt", out_txt
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
        if result.returncode != 0:
            print(f"[Warning] Backtest returned exit code {result.returncode}")
            print(f"[Warning] STDERR: {result.stderr[:500]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[Error] Backtest timed out after 600 seconds.")
        return False
    except Exception as e:
        print(f"[Error] Backtest subprocess error: {e}")
        return False

def parse_backtest_result(out_json, candidate_name, original):
    """Parse backtest JSON output and return structured result."""
    result = {
        "candidate_name": candidate_name,
        "threshold_candidates": original.get("threshold_candidates"),
        "cost_floor_pct": original.get("cost_floor_pct"),
        "trades": 0,
        "avg_net_pnl_pct": 0.0,
        "win_rate": 0.0,
        "tp_count": 0,
        "sl_count": 0,
        "timeout_count": 0,
        "judgement": "NO_ENTRY",
        "error": None
    }

    if not os.path.exists(out_json):
        result["error"] = "output_json_missing"
        return result

    try:
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data.get("ok", True) == False:
            rankings = data.get("rankings", {})
            top_exit = rankings.get("top_20_exit_policy_by_avg_net_pnl", [])
            top_fixed = rankings.get("top_20_fixed_holding_by_avg_net_pnl", [])

            total_raw = data.get("total_raw_candidates", 0)
            result["trades"] = total_raw

            if top_exit:
                best = top_exit[0]
                result["avg_net_pnl_pct"] = best.get("avg_net_pnl_pct", 0.0)
                result["win_rate"] = best.get("win_rate_net_positive", 0.0)
                result["tp_count"] = best.get("tp_hit_count", 0)
                result["sl_count"] = best.get("sl_hit_count", 0)
                result["timeout_count"] = best.get("timeout_count", 0)
            elif top_fixed:
                best = top_fixed[0]
                result["avg_net_pnl_pct"] = best.get("avg_net_pnl_pct", 0.0)
                result["win_rate"] = best.get("win_rate_net_positive", 0.0)

        # Determine judgement
        trades = result["trades"]
        pnl = result["avg_net_pnl_pct"]
        if trades == 0:
            result["judgement"] = "NO_ENTRY"
        elif trades < 5:
            result["judgement"] = "TOO_FEW_TRADES"
        elif pnl > 0:
            result["judgement"] = "PROMISING"
        else:
            result["judgement"] = "ENTRY_BUT_NEGATIVE"

    except Exception as e:
        result["error"] = str(e)

    return result

def judgement_symbol(j):
    symbols = {
        "NO_ENTRY": "❌",
        "TOO_FEW_TRADES": "⚠️",
        "PROMISING": "✅",
        "ENTRY_BUT_NEGATIVE": "📉",
    }
    return symbols.get(j, "?")

# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 60)
    print(" Reversal Edge v2 Candidate Sensitivity Analysis")
    print("=" * 60)

    os.makedirs(TMP_CANDIDATES_DIR, exist_ok=True)
    os.makedirs(SENSITIVITY_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # 1. Load original candidate
    print(f"\n[Step 1] Loading original candidate: {ORIGINAL_CANDIDATE}")
    original = load_original_candidate()
    orig_threshold = original.get("threshold_candidates", "KEY_MISSING")
    orig_cost = original.get("cost_floor_pct", "KEY_MISSING")
    print(f"  Threshold: {orig_threshold}")
    print(f"  Cost Floor: {orig_cost}%")

    # 2. Prepare master JSONL
    print(f"\n[Step 2] Preparing master JSONL...")
    ws_path, ws_source = get_master_temp_jsonl()
    if not ws_path:
        print("[Error] No master data available. Aborting.")
        return
    print(f"  Using: {ws_path} (source: {ws_source})")

    # 3. Run experiments
    print(f"\n[Step 3] Running {len(EXPERIMENTS)} experiments...")
    all_results = []
    created_candidates = []

    for exp in EXPERIMENTS:
        print(f"\n  --- [{exp['name']}] {exp['label']} ---")

        # Build candidate
        exp_candidate, warnings = prepare_tmp_candidate(original, exp)

        # Snapshot the actual params used
        exp_threshold = exp_candidate.get("threshold_candidates", "KEY_MISSING")
        exp_cost = exp_candidate.get("cost_floor_pct", "KEY_MISSING")

        if warnings:
            for w in warnings:
                print(f"  [Warning] {w}")

        # Write tmp candidate
        candidate_path = os.path.join(TMP_CANDIDATES_DIR, f"{exp['name']}.json")
        with open(candidate_path, "w", encoding="utf-8") as f:
            json.dump(exp_candidate, f, ensure_ascii=False, indent=2)
        created_candidates.append(candidate_path)

        # Run backtest
        out_json = os.path.join(SENSITIVITY_DIR, f"{exp['name']}_result.json")
        out_txt = os.path.join(SENSITIVITY_DIR, f"{exp['name']}_result.txt")
        print(f"  Running backtest...")
        success = run_backtest(ws_path, candidate_path, out_json, out_txt)

        # Parse result
        result = parse_backtest_result(out_json, exp["name"], exp_candidate)
        result["threshold_candidates"] = exp_threshold
        result["cost_floor_pct"] = exp_cost
        result["warnings"] = warnings
        result["backtest_success"] = success

        all_results.append(result)

        symbol = judgement_symbol(result["judgement"])
        print(f"  Result: Trades={result['trades']} | PnL={result['avg_net_pnl_pct']:.4f}% | {symbol} {result['judgement']}")

    # 4. Analyze results
    print("\n[Step 4] Analyzing results...")

    first_entry = next((r for r in all_results if r["trades"] > 0), None)
    promising = [r for r in all_results if r["judgement"] == "PROMISING"]
    all_zero = all(r["trades"] == 0 for r in all_results)

    # 5. Generate reports
    print("\n[Step 5] Generating reports...")

    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "original_candidate": ORIGINAL_CANDIDATE,
        "master_input_path": ws_path,
        "master_input_source": ws_source,
        "original_threshold_candidates": orig_threshold,
        "original_cost_floor_pct": orig_cost,
        "experiment_count": len(EXPERIMENTS),
        "created_candidates": created_candidates,
        "all_zero_trades": all_zero,
        "first_entry_condition": first_entry["candidate_name"] if first_entry else None,
        "promising_count": len(promising),
        "results": all_results
    }

    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)

    # TXT Report
    txt_lines = [
        "============================================================",
        " Reversal Edge v2 Candidate Sensitivity Analysis Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        f"원본 Candidate: {ORIGINAL_CANDIDATE}",
        f"Master 입력 파일: {ws_path} (source: {ws_source})",
        f"원본 Threshold: {orig_threshold}",
        f"원본 Cost Floor: {orig_cost}%",
        "",
        "[ 실험 결과 요약 ]",
        "-" * 72,
        f"{'Candidate':<30} {'Threshold':<16} {'Cost':<6} {'Trades':>7} {'AvgPnL':>8} {'WinR':>6} {'판정':<22}",
        "-" * 72,
    ]

    for r in all_results:
        sym = judgement_symbol(r["judgement"])
        thresh_str = str(r["threshold_candidates"]) if r["threshold_candidates"] != "KEY_MISSING" else "KEY_MISSING"
        if len(thresh_str) > 15:
            thresh_str = thresh_str[:14] + "…"
        txt_lines.append(
            f"{r['candidate_name']:<30} {thresh_str:<16} {str(r['cost_floor_pct']):<6} "
            f"{r['trades']:>7} {r['avg_net_pnl_pct']:>8.4f} {r['win_rate']:>5.1f}% "
            f"{sym} {r['judgement']}"
        )

    txt_lines.append("-" * 72)
    txt_lines.append("")

    if first_entry:
        txt_lines.append(f"✅ 최초 Trades 발생 조건: [{first_entry['candidate_name']}]")
        txt_lines.append(f"   Threshold: {first_entry['threshold_candidates']}")
        txt_lines.append(f"   Cost Floor: {first_entry['cost_floor_pct']}%")
        txt_lines.append(f"   Trades: {first_entry['trades']}, PnL: {first_entry['avg_net_pnl_pct']:.4f}%")
    else:
        txt_lines.append("❌ 모든 실험 후보에서 Trades 0건 - 진입 조건이 극도로 타이트함")

    txt_lines.append("")

    if promising:
        txt_lines.append("[ Net PnL 양수 후보 ]")
        for r in promising:
            txt_lines.append(f"  ✅ {r['candidate_name']} | Trades={r['trades']} | PnL={r['avg_net_pnl_pct']:.4f}%")
    else:
        txt_lines.append("[ Net PnL 양수 후보: 없음 ]")

    txt_lines.append("")

    if all_zero:
        txt_lines.extend([
            "[ Trades 0건 지속 원인 후보 분석 ]",
            "",
            "1. Threshold만의 문제가 아닐 가능성",
            "   - 현재 threshold를 40까지 낮췄음에도 trades가 0이라면,",
            "     reversal_conditions의 진입 필터 자체가 병목일 수 있음.",
            "   - max_price_chg_10s, min_sell_buy_ratio_10s 등이 너무 엄격함.",
            "",
            "2. Cost Floor만의 문제가 아닐 가능성",
            "   - cost_floor는 이미 발생한 trade의 PnL 판단에 사용됨.",
            "   - trade 자체가 0건이면 cost_floor 완화는 의미 없음.",
            "",
            "3. Scoring Weights 또는 Market Scope 병목 가능성",
            "   - market_sync_score 계산 시 여러 마켓 데이터가 필요하나",
            "     SOL_ONLY 모드에서 타 마켓 데이터가 없으면 점수가 낮게 산출됨.",
            "   - weights 조정이 필요한 구간일 수 있음.",
            "",
            "4. RANGE/횡보 장세 조건 미발생 가능성",
            "   - 수집 기간 동안 강한 일방향 추세장이 지속되었다면",
            "     Reversal 신호의 전제 조건 (급락 후 반등 구조)이 발생하지 않았을 수 있음.",
            "   - 다음 단계: 가격 변화율 히스토그램 진단 필요.",
            "",
            "[ 다음 행동 제안 ]",
            "1. reversal_conditions 개별 필터 완화 실험 (2차)",
            "2. market_sync_score 비중 완화 또는 제거 실험 (2차)",
            "3. 특정 급락 구간 데이터 추가 수집 후 재실험",
            "4. KRW-SOL 이외의 마켓 추가 병행 (STATIC_MULTI_MARKET 모드)",
        ])
    else:
        txt_lines.extend([
            "[ 다음 행동 제안 ]",
            "1. 최초 진입 발생 조건을 Paper Runner에 반영하여 30분~1H Paper 실험",
            "2. Net PnL 양수 후보는 Walk-forward 검증으로 승격 검토",
            "3. 기존 원본 candidate는 절대 자동 교체하지 말 것",
        ])

    txt_lines.extend([
        "",
        "=" * 60,
        " ⚠️  안전 경고 및 금지 사항",
        "=" * 60,
        " 🚫 이 결과는 실거래 승인이 아님",
        " 🚫 기존 candidate 자동 교체 금지",
        " 🚫 config 자동 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 사람 승인 전 tiny_live 금지",
    ])

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")

    print(f"\n[Done] JSON report: {JSON_REPORT}")
    print(f"[Done] TXT report: {TXT_REPORT}")

    if first_entry:
        print(f"\n최초 진입 발생: [{first_entry['candidate_name']}] Trades={first_entry['trades']}")
    else:
        print("\n⚠️ 모든 후보에서 Trades 0건. 2차 분석 필요.")

if __name__ == "__main__":
    main()
