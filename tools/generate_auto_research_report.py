"""
generate_auto_research_report.py
Auto Research Report Generator.

Reads backtest, OOS chunk, and paper summary results.
Synthesizes the data into a single structured report.
Determines the current status and recommends the next action.
"""

import glob
import json
import os
import sys
from datetime import datetime


def load_json(path):
    """Safely load JSON file. Returns {} if failed or not found."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Failed to load JSON {path}: {e}")
        return {}


def load_txt_tail(path, max_bytes=65536):
    """Safely load tail of TXT file."""
    if not os.path.exists(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
            return f.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Warning] Failed to load TXT {path}: {e}")
        return ""


def find_latest_file(patterns):
    """Find the most recently modified file matching the given patterns."""
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def evaluate_action(paper_data, oos_data, master_data):
    """Determine the next action based on the rules."""
    if not paper_data:
        return "WAIT_FOR_PAPER_RESULT", "Paper 결과가 아직 없으므로 현재 실행이 끝날 때까지 대기"

    trades = paper_data.get("total_trades")
    # Some summaries use paper_entries instead of total_trades
    if trades is None:
        trades = paper_data.get("paper_entries", 0)

    if trades == 0:
        return "NEED_MORE_PAPER_OR_CONDITION_REVIEW", "조건 미발생 / 조건 병목 분석 필요"

    master_count = master_data.get("after_dedup_count", master_data.get("master_event_count", 0))
    if master_count > 0:
        dataset_msg = " (데이터셋 구성 완료)"
    else:
        dataset_msg = ""

    if trades < 5:
        return "NEED_MORE_DATA", f"표본 부족. 24H~72H 추가 Paper 필요{dataset_msg}"

    net_pnl = paper_data.get("avg_net_pnl_pct") or paper_data.get("net_pnl_pct", 0.0)
    
    if net_pnl < 0:
        return "HOLD_AND_ANALYZE_FAILURES", f"실패 조건 분석 필요{dataset_msg}"

    sl_count = paper_data.get("sl_count", 0)
    if trades > 0 and sl_count / trades > 0.6:  # High SL ratio (>60%)
        return "RISK_REVIEW_REQUIRED", f"SL 또는 진입 조건 재검토 필요{dataset_msg}"

    if oos_data and oos_data.get("final_judgement", "").startswith("NEED_MORE_DATA"):
         return "RUN_MORE_OOS_CHUNKS", f"OOS chunk 추가 수집 필요{dataset_msg}"

    if net_pnl > 0 and trades >= 10:
        return "PROMISING_RUN_3D_PAPER", f"유망하지만 실거래 금지. 3일 Paper 검증 권장{dataset_msg}"
        
    return "CONTINUE_MONITORING", f"현재 상태 유지 및 모니터링{dataset_msg}"


def main():
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "candidate": {
            "strategy": "Reversal Edge v2",
            "candidate_file": "configs/experiments/reversal_edge_candidate_v2_from_36h.json",
            "mode": "STATIC_SOL_ONLY",
            "market": "KRW-SOL",
            "tp": "0.4%",
            "sl": "-0.1%",
            "timeout": "300s",
            "cost_floor": "0.20%"
        },
        "files_read": {},
        "summary": {
            "paper": {},
            "oos": {},
            "backtest": {},
            "master_dataset": {},
            "holdout": {},
            "htf_regime": {},
            "funnel": {},
            "schema": {}
        },
        "judgement": {
            "action": "",
            "reason": ""
        }
    }

    # 1. Paper Summary
    paper_patterns = [
        "reports/paper/reversal_edge_v2_paper_24h_summary.json",
        "reports/experiments/reversal_edge_v2_paper_run_summary_*.json"
    ]
    latest_paper_json = find_latest_file(paper_patterns)
    if latest_paper_json:
        report_data["files_read"]["paper_json"] = latest_paper_json
        report_data["summary"]["paper"] = load_json(latest_paper_json)
    else:
        report_data["files_read"]["paper_json"] = "없음"

    # New latest files
    latest_files = {
        "master_dataset": "reports/experiments/master_dataset_builder_latest.json",
        "holdout": "reports/experiments/independent_holdout_validation_latest.json",
        "htf_regime": "reports/experiments/htf_regime_gate_analysis_latest.json",
        "funnel": "reports/experiments/reversal_entry_funnel_diagnostics_latest.json",
        "schema": "reports/experiments/candidate_schema_inspection_latest.json",
        "walk_forward": "reports/experiments/walk_forward_validation_latest.json",
        "cost_randomization": "reports/experiments/cost_randomization_test_latest.json"
    }

    for key, path in latest_files.items():
        if os.path.exists(path):
            report_data["files_read"][key] = path
            report_data["summary"][key] = load_json(path)
        else:
            report_data["files_read"][key] = "없음"

    # Evaluate action
    paper_data = report_data["summary"]["paper"]
    oos_data = report_data["summary"].get("walk_forward", {})
    master_data = report_data["summary"].get("master_dataset", {})
    
    action, reason = evaluate_action(paper_data, oos_data, master_data)
    
    report_data["judgement"]["action"] = action
    report_data["judgement"]["reason"] = reason

    # Generate JSON output
    out_json = "reports/experiments/auto_research_report_latest.json"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    # Generate TXT output
    lines = [
        "============================================================",
        "  CoinB Auto Research Report",
        "============================================================",
        f"생성 시각: {report_data['generated_at']}",
        "",
        "[현재 전략 후보]",
        f" - 전략    : {report_data['candidate']['strategy']}",
        f" - 파일    : {report_data['candidate']['candidate_file']}",
        f" - 모드    : {report_data['candidate']['mode']}",
        f" - 마켓    : {report_data['candidate']['market']}",
        f" - TP      : {report_data['candidate']['tp']}",
        f" - SL      : {report_data['candidate']['sl']}",
        f" - Timeout : {report_data['candidate']['timeout']}",
        f" - Cost Flr: {report_data['candidate']['cost_floor']}",
        "",
        "[읽은 파일 목록]"
    ]
    
    for k, v in report_data["files_read"].items():
        lines.append(f" - {k}: {v}")

    lines.extend([
        "",
        "[핵심 결과]"
    ])
    
    if paper_data:
        trades = paper_data.get("paper_entries", paper_data.get("total_trades", 0))
        net_pnl = paper_data.get("avg_net_pnl_pct", paper_data.get("net_pnl_pct", 0.0))
        win_rate = paper_data.get("win_rate", 0.0)
        sl_count = paper_data.get("sl_count", 0)
        timeout_count = paper_data.get("timeout_count", 0)
        
        lines.extend([
            " (Paper)",
            f"   * Trades 수    : {trades}",
            f"   * Net PnL (%)  : {net_pnl:.4f}",
            f"   * Win Rate (%) : {win_rate:.2f}",
            f"   * SL hit       : {sl_count}",
            f"   * Timeout hit  : {timeout_count}"
        ])
    else:
        lines.append(" (Paper) 데이터 없음")

    lines.append(" (Validation Pipeline)")
    
    wf = report_data["summary"].get("walk_forward", {})
    if wf:
        lines.extend([
            f"   * Walk-forward : {wf.get('final_judgement', 'N/A')} (Folds: {wf.get('total_folds')}, PnL: {wf.get('avg_net_pnl_pct')}%)",
        ])
        
    cr = report_data["summary"].get("cost_randomization", {})
    if cr:
        lines.extend([
            f"   * Cost Test    : {cr.get('final_judgement', 'N/A')} (Base Trades: {cr.get('base_trades')})",
        ])

    md = report_data["summary"].get("master_dataset", {})
    if md:
        lines.extend([
            f"   * Master Dataset: Events {md.get('master_event_count', 'N/A')}, Holdout {md.get('holdout_event_count', 'N/A')}",
        ])

    lines.extend([
        "",
        "[Promotion Guard / 다음 행동]",
        f" ACTION : {action}",
        f" REASON : {reason}",
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 실거래 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 config 자동 반영 금지",
        " 🚫 사람 승인 전 tiny_live 금지",
        "------------------------------------------------------------"
    ])

    out_txt = "reports/experiments/auto_research_report_latest.txt"
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")
        
    print(f"Report generated successfully.")
    print(f"JSON: {out_json}")
    print(f"TXT : {out_txt}")


if __name__ == "__main__":
    main()
