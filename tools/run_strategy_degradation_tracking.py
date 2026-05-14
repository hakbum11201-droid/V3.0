"""
run_strategy_degradation_tracking.py

Strategy Degradation Tracking Tool
시간 경과에 따라 전략의 성과(PnL, Win Rate)가 망가지고 있는지 감시하고 평가합니다.
"""

import os
import json
from datetime import datetime

# =============================================================================
# Constants & Configuration
# =============================================================================
TRADES_JSONL = "logs/paper/reversal_edge_v2_paper_trades.jsonl"
SUMMARY_JSON_FILES = [
    "reports/paper/reversal_edge_v2_paper_24h_summary.json",
    "reports/experiments/auto_research_report_latest.json",
    "reports/experiments/cost_randomization_test_latest.json",
    "reports/experiments/walk_forward_validation_latest.json",
    "reports/experiments/reversal_oos_chunk_pipeline_summary.json"
]

REPORTS_DIR = "reports/experiments"

# =============================================================================
# Functions
# =============================================================================

def load_trades(filepath):
    trades = []
    if not os.path.exists(filepath):
        return trades
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # trades jsonl usually has entry_ts, exit_ts, net_pnl_pct, exit_type etc.
                    trades.append(data)
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"[Warning] Failed to read trades jsonl: {e}")
        
    return trades

def load_summaries():
    summaries = {}
    for fp in SUMMARY_JSON_FILES:
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    summaries[fp] = json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to load {fp}: {e}")
    return summaries

def calculate_metrics(trades):
    if not trades:
        return {}
        
    total_trades = len(trades)
    
    # Sort trades chronologically by exit time or entry time
    # assuming trades are appended chronologically, we just take the list order.
    
    def get_metrics(trade_list):
        if not trade_list:
            return 0.0, 0.0
            
        pnl_sum = 0.0
        win_count = 0
        for t in trade_list:
            pnl = t.get("net_pnl_pct", 0.0)
            pnl_sum += pnl
            if pnl > 0:
                win_count += 1
                
        avg_pnl = pnl_sum / len(trade_list)
        win_rate = (win_count / len(trade_list)) * 100.0
        return avg_pnl, win_rate

    recent_10 = trades[-10:]
    recent_30 = trades[-30:]
    
    r10_avg_pnl, r10_win_rate = get_metrics(recent_10)
    r30_avg_pnl, r30_win_rate = get_metrics(recent_30)
    
    sl_count = sum(1 for t in trades if t.get("exit_type") in ("SL", "STOP_LOSS"))
    tp_count = sum(1 for t in trades if t.get("exit_type") in ("TP", "TAKE_PROFIT"))
    timeout_count = sum(1 for t in trades if t.get("exit_type") in ("TIMEOUT", "TIME_LIMIT"))
    
    # If exit_type is missing, try to infer from net_pnl
    if sl_count == 0 and tp_count == 0 and timeout_count == 0:
        for t in trades:
            pnl = t.get("net_pnl_pct", 0.0)
            if pnl <= -0.1:  # Assuming SL is -0.1%
                sl_count += 1
            elif pnl >= 0.3: # Assuming TP is 0.4%
                tp_count += 1
            else:
                timeout_count += 1
                
    return {
        "total_trades": total_trades,
        "recent_10_trades": len(recent_10),
        "recent_30_trades": len(recent_30),
        "recent_10_avg_net_pnl": r10_avg_pnl,
        "recent_30_avg_net_pnl": r30_avg_pnl,
        "recent_10_win_rate": r10_win_rate,
        "recent_30_win_rate": r30_win_rate,
        "sl_count": sl_count,
        "tp_count": tp_count,
        "timeout_count": timeout_count,
        "sl_ratio": sl_count / total_trades if total_trades > 0 else 0.0,
        "timeout_ratio": timeout_count / total_trades if total_trades > 0 else 0.0
    }

def evaluate_degradation(metrics):
    if not metrics or metrics.get("total_trades", 0) == 0:
        return "NEED_MORE_DATA", "데이터 부족으로 판단 불가"
        
    r10_pnl = metrics.get("recent_10_avg_net_pnl", 0.0)
    sl_ratio = metrics.get("sl_ratio", 0.0)
    timeout_ratio = metrics.get("timeout_ratio", 0.0)
    r10_wr = metrics.get("recent_10_win_rate", 0.0)
    r30_wr = metrics.get("recent_30_win_rate", 0.0)
    
    if r10_pnl < 0:
        return "DEGRADED", "최근 10건 성과(Net PnL) 음수"
        
    if sl_ratio >= 0.5:
        return "RISK_DEGRADED", f"SL 비율 과다 ({sl_ratio*100:.1f}%)"
        
    if timeout_ratio >= 0.7:
        return "WEAK_SIGNAL", f"Timeout 비율 과다 ({timeout_ratio*100:.1f}%)"
        
    if metrics["recent_30_trades"] > 10 and (r30_wr - r10_wr) >= 15.0:
        return "POSSIBLE_DEGRADATION", "최근 승률 크게 하락"
        
    return "HEALTHY", "양수 유지 및 리스크 한도 내 안정적"

def determine_action(judgement):
    actions = {
        "NEED_MORE_DATA": "24H Paper 종료 후 재실행",
        "HEALTHY": "3D Paper 검증 후보",
        "DEGRADED": "최근 손실 구간 분석 필요",
        "RISK_DEGRADED": "SL 조건 또는 진입 조건 재검토",
        "WEAK_SIGNAL": "Timeout 과다. 진입 조건 또는 TP/Timeout 재검토",
        "POSSIBLE_DEGRADATION": "최근 성과 하락. 추가 Paper 또는 구간별 분석 필요",
        "UNKNOWN": "데이터 확인 필요"
    }
    return actions.get(judgement, "알 수 없음")

def main():
    print("============================================================")
    print(" Strategy Degradation Tracking Tool")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Load Data
    trades = load_trades(TRADES_JSONL)
    summaries = load_summaries()
    
    files_read = []
    if os.path.exists(TRADES_JSONL):
        files_read.append(TRADES_JSONL)
    files_read.extend(list(summaries.keys()))
    
    # Metrics
    metrics = calculate_metrics(trades)
    if not metrics and summaries:
        # Fallback to summary values if trades don't exist
        for k, v in summaries.items():
            if isinstance(v, dict) and "total_trades" in v:
                metrics = {
                    "total_trades": v.get("total_trades", 0),
                    "recent_10_trades": 0,
                    "recent_30_trades": 0,
                    "recent_10_avg_net_pnl": v.get("net_pnl_pct", 0.0),
                    "recent_30_avg_net_pnl": v.get("net_pnl_pct", 0.0),
                    "recent_10_win_rate": v.get("win_rate", 0.0),
                    "recent_30_win_rate": v.get("win_rate", 0.0),
                    "sl_count": 0,
                    "tp_count": 0,
                    "timeout_count": 0,
                    "sl_ratio": 0.0,
                    "timeout_ratio": 0.0
                }
                break
                
    if not metrics:
        metrics = {"total_trades": 0}
        
    # Evaluate
    judgement, reason = evaluate_degradation(metrics)
    action = determine_action(judgement)
    
    # Output
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "files_read": files_read,
        "metrics": metrics,
        "judgement": judgement,
        "reason": reason,
        "action": action
    }
    
    json_path = os.path.join(REPORTS_DIR, "strategy_degradation_tracking_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "strategy_degradation_tracking_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  Strategy Degradation Tracking Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[읽은 파일 목록]"
    ]
    
    if not files_read:
        txt_lines.append(" - 없음 (데이터 부족)")
    else:
        for fr in files_read:
            txt_lines.append(f" - {fr}")
            
    txt_lines.extend([
        "",
        "[성과 Metrics]"
    ])
    
    if metrics.get("total_trades", 0) > 0:
        txt_lines.extend([
            f" - 총 거래 수         : {metrics['total_trades']}",
            f" - 최근 10건 성과     : PnL {metrics.get('recent_10_avg_net_pnl', 0):+.4f}%, 승률 {metrics.get('recent_10_win_rate', 0):.2f}%",
            f" - 최근 30건 성과     : PnL {metrics.get('recent_30_avg_net_pnl', 0):+.4f}%, 승률 {metrics.get('recent_30_win_rate', 0):.2f}%",
            f" - SL / TP / Timeout  : {metrics.get('sl_count', 0)} / {metrics.get('tp_count', 0)} / {metrics.get('timeout_count', 0)}",
            f" - SL 발생 비율       : {metrics.get('sl_ratio', 0)*100:.1f}%",
            f" - Timeout 발생 비율  : {metrics.get('timeout_ratio', 0)*100:.1f}%"
        ])
    else:
        txt_lines.append(" - 데이터 없음 (Trades 0)")
        
    txt_lines.extend([
        "",
        "[최종 상태 및 제안]",
        f" 🎯 최종 상태      : {judgement} ({reason})",
        f" 💡 다음 행동 제안 : {action}",
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
        
    print(f"\n[Done] Judgement: {judgement}")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
