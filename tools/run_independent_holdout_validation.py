"""
run_independent_holdout_validation.py

Independent Holdout Validation
Master 데이터셋과 Holdout 데이터셋을 독립적으로 평가하여,
전략 엣지가 Holdout 데이터에서도 검증되는지 확인합니다.
"""

import os
import json
import subprocess
from datetime import datetime

# =============================================================================
# Constants & Configuration
# =============================================================================
MASTER_JSONL = "logs/experiments/master/reversal_edge_master_dataset.jsonl"
HOLDOUT_JSONL = "logs/experiments/master/reversal_edge_holdout_dataset.jsonl"
CANDIDATE_JSON = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"

REPORTS_DIR = "reports/experiments"

# =============================================================================
# Functions
# =============================================================================

def run_backtest(dataset_path, prefix):
    out_json = os.path.join(REPORTS_DIR, f"{prefix}_summary.json")
    out_txt = os.path.join(REPORTS_DIR, f"{prefix}_summary.txt")
    
    cmd = [
        "python", "-m", "coinb.main", "reversal-edge-backtest",
        "--ws", dataset_path,
        "--candidate", CANDIDATE_JSON,
        "--output-json", out_json,
        "--output-txt", out_txt
    ]
    
    print(f"[Info] Running backtest on {dataset_path}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[Warning] Backtest failed: {e}")
        return None
        
    if not os.path.exists(out_json):
        return None
        
    try:
        with open(out_json, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Failed to load {out_json}: {e}")
        return None

def extract_metrics(summary):
    if not summary:
        return 0, 0.0, 0.0
    trades = summary.get("total_trades", summary.get("paper_entries", 0))
    pnl = summary.get("net_pnl_pct", summary.get("avg_net_pnl_pct", 0.0))
    wr = summary.get("win_rate", 0.0)
    return trades, pnl, wr

def main():
    print("============================================================")
    print(" Independent Holdout Validation")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Check data existence
    has_master = os.path.exists(MASTER_JSONL) and os.path.getsize(MASTER_JSONL) > 0
    has_holdout = os.path.exists(HOLDOUT_JSONL) and os.path.getsize(HOLDOUT_JSONL) > 0
    
    if not has_holdout:
        print("[Warning] Holdout dataset not found or empty.")
        judgement = "NEED_HOLDOUT_DATA"
        m_trades, m_pnl, m_wr = 0, 0.0, 0.0
        h_trades, h_pnl, h_wr = 0, 0.0, 0.0
        pnl_gap = 0.0
        wr_gap = 0.0
    else:
        # 1. Run Master Backtest
        master_summary = run_backtest(MASTER_JSONL, "master_validation") if has_master else None
        m_trades, m_pnl, m_wr = extract_metrics(master_summary)
        
        # 2. Run Holdout Backtest
        holdout_summary = run_backtest(HOLDOUT_JSONL, "holdout_validation")
        h_trades, h_pnl, h_wr = extract_metrics(holdout_summary)
        
        # 3. Compare
        pnl_gap = h_pnl - m_pnl
        wr_gap = h_wr - m_wr
        
        if h_trades == 0:
            judgement = "NEED_MORE_HOLDOUT_TRADES"
        elif m_trades == 0:
            judgement = "NEED_MORE_DATA"
        elif m_pnl > 0 and h_pnl > 0:
            judgement = "PASSES_INDEPENDENT_HOLDOUT"
        elif m_pnl > 0 and h_pnl <= 0:
            judgement = "FAILS_HOLDOUT"
        else:
            judgement = "UNSTABLE"
            
    # 4. Output
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "candidate": CANDIDATE_JSON,
        "master_trades": m_trades,
        "master_avg_net_pnl_pct": m_pnl,
        "master_win_rate": m_wr,
        "holdout_trades": h_trades,
        "holdout_avg_net_pnl_pct": h_pnl,
        "holdout_win_rate": h_wr,
        "pnl_gap": pnl_gap,
        "win_rate_gap": wr_gap,
        "judgement": judgement
    }
    
    json_path = os.path.join(REPORTS_DIR, "independent_holdout_validation_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "independent_holdout_validation_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  Independent Holdout Validation Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[Master Dataset 결과]",
        f" - 총 거래 수 : {m_trades}",
        f" - 평균 PnL   : {m_pnl:+.4f}%",
        f" - 평균 승률  : {m_wr:.2f}%",
        "",
        "[Holdout Dataset 결과]",
        f" - 총 거래 수 : {h_trades}",
        f" - 평균 PnL   : {h_pnl:+.4f}%",
        f" - 평균 승률  : {h_wr:.2f}%",
        "",
        "[성과 차이 (Holdout - Master)]",
        f" - PnL 차이   : {pnl_gap:+.4f}%",
        f" - 승률 차이  : {wr_gap:+.2f}%",
        "",
        f"🎯 최종 판단: {judgement}",
        "",
        "[주의 및 안전 규정]",
        " ⚠️ Holdout 결과를 보고 조건(Candidate)을 수정하는 것은 과최적화입니다. 절대 수정하지 마십시오.",
        " 🚫 이 결과는 실거래 승인이 아닙니다.",
        " 🚫 live.enabled=false 유지.",
        " 🚫 사람 승인 전 tiny_live 금지."
    ]
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print(f"\n[Done] Judgement: {judgement}")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
