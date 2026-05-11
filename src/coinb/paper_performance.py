import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List
from . import report_io

def run_paper_performance(
    trades_path: str,
    decisions_path: str,
    output_json_path: str,
    equity_output_path: str,
    summary_output_path: str,
    starting_cash_krw: float = 1000000.0
) -> Dict[str, Any]:
    """
    Paper trading 성과를 분석하여 PnL, Equity Curve, MDD 등을 계산한다.
    """
    trades = []
    if os.path.exists(trades_path):
        try:
            with open(trades_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip(): trades.append(json.loads(line))
        except: pass

    decision_count = 0
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip(): decision_count += 1
        except: pass

    trade_count = len(trades)
    realized_pnl = sum(t.get("pnl_krw", 0.0) for t in trades)
    total_pnl = realized_pnl
    final_equity = starting_cash_krw + total_pnl
    
    win_trades = [t for t in trades if t.get("pnl_krw", 0.0) > 0]
    win_rate = (len(win_trades) / trade_count * 100.0) if trade_count > 0 else 0.0
    avg_pnl_pct = sum(t.get("pnl_pct", 0.0) for t in trades) / trade_count if trade_count > 0 else 0.0
    
    equity_curve = []
    current_equity = starting_cash_krw
    peak_equity = starting_cash_krw
    max_drawdown = 0.0
    sorted_trades = sorted(trades, key=lambda x: x.get("timestamp", 0.0))
    
    for t in sorted_trades:
        current_equity += t.get("pnl_krw", 0.0)
        peak_equity = max(peak_equity, current_equity)
        dd = (peak_equity - current_equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0
        max_drawdown = max(max_drawdown, dd)
        equity_curve.append({"timestamp": t.get("timestamp"), "equity": round(current_equity, 2), "pnl_krw": round(t.get("pnl_krw", 0.0), 2)})
    
    market_summary = {}
    for t in trades:
        m = t.get("market", "UNKNOWN")
        if m not in market_summary: market_summary[m] = {"trade_count": 0, "pnl_krw": 0.0, "win_count": 0}
        market_summary[m]["trade_count"] += 1
        market_summary[m]["pnl_krw"] += t.get("pnl_krw", 0.0)
        if t.get("pnl_krw", 0.0) > 0: market_summary[m]["win_count"] += 1
            
    for m in market_summary:
        market_summary[m]["win_rate"] = round((market_summary[m]["win_count"] / market_summary[m]["trade_count"] * 100.0) if market_summary[m]["trade_count"] > 0 else 0.0, 2)

    result = {
        "ok": True, "generated_at": time.time(), "decision_count": decision_count, "trade_count": trade_count,
        "starting_cash_krw": starting_cash_krw, "final_equity_krw": round(final_equity, 2),
        "total_pnl_krw": round(total_pnl, 2), "total_pnl_pct": round((total_pnl / starting_cash_krw * 100.0) if starting_cash_krw > 0 else 0.0, 4),
        "win_rate": round(win_rate, 2), "avg_pnl_pct": round(avg_pnl_pct, 4), "max_drawdown_pct": round(max_drawdown, 4),
        "market_summary": market_summary
    }

    report_io.write_json_report(output_json_path, result)
    
    # Equity curve is JSONL (special case, but let's keep it simple)
    os.makedirs(os.path.dirname(equity_output_path), exist_ok=True)
    with open(equity_output_path, "w", encoding="utf-8") as f:
        for point in equity_curve: f.write(json.dumps(point, ensure_ascii=False) + "\n")
            
    build_summary_txt(result, summary_output_path)
    return result

def build_summary_txt(res: Dict[str, Any], path: str):
    dt_str = datetime.fromtimestamp(res["generated_at"]).strftime('%Y-%m-%d %H:%M:%S')
    lines = [
        "[페이퍼 트레이딩 성과 요약]",
        f"- 생성 시간: {dt_str}",
        f"- 총 거래 횟수: {res['trade_count']:,}",
        f"- 시작 자산: {res['starting_cash_krw']:,} KRW",
        f"- 최종 자산: {res['final_equity_krw']:,} KRW",
        f"- 누적 수익: {res['total_pnl_krw']:,} KRW ({res['total_pnl_pct']:.4f}%)",
        f"- 승률: {res['win_rate']:.2f}%",
        f"- 최대 낙폭(MDD): {res['max_drawdown_pct']:.4f}%",
        "",
        "[마켓별 요약]"
    ]
    for m, s in res["market_summary"].items():
        lines.append(f"- {m}: {s['trade_count']}회, 수익 {s['pnl_krw']:,} KRW, 승률 {s['win_rate']}%")
        
    report_io.write_text_report(path, "\n".join(lines))
