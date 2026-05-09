import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

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
    # 1. 데이터 로드
    trades = []
    if os.path.exists(trades_path):
        try:
            with open(trades_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except Exception:
            pass

    decision_count = 0
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        decision_count += 1
        except Exception:
            pass

    trade_count = len(trades)
    
    # 2. 성과 계산
    realized_pnl_krw = sum(t.get("pnl_krw", 0.0) for t in trades)
    unrealized_pnl_krw = 0.0 # 로그 분석 단계에서는 미실현 수익을 0으로 처리 (현재 포지션 정보 부재)
    total_pnl_krw = realized_pnl_krw + unrealized_pnl_krw
    final_equity_krw = starting_cash_krw + total_pnl_krw
    
    win_trades = [t for t in trades if t.get("pnl_krw", 0.0) > 0]
    loss_trades = [t for t in trades if t.get("pnl_krw", 0.0) <= 0]
    
    win_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = (win_count / trade_count * 100.0) if trade_count > 0 else 0.0
    
    avg_pnl_pct = sum(t.get("pnl_pct", 0.0) for t in trades) / trade_count if trade_count > 0 else 0.0
    
    # Equity curve 및 MDD 계산
    equity_curve = []
    current_equity = starting_cash_krw
    peak_equity = starting_cash_krw
    max_drawdown_pct = 0.0
    
    # 시간순 정렬
    sorted_trades = sorted(trades, key=lambda x: x.get("timestamp", 0.0))
    
    # 시작점 추가
    start_ts = sorted_trades[0].get("timestamp", time.time()) - 1 if sorted_trades else time.time()
    equity_curve.append({
        "timestamp": start_ts,
        "equity": starting_cash_krw,
        "pnl_krw": 0.0
    })
    
    max_consecutive_losses = 0
    current_consecutive_losses = 0
    
    for t in sorted_trades:
        pnl = t.get("pnl_krw", 0.0)
        current_equity += pnl
        
        if pnl <= 0:
            current_consecutive_losses += 1
        else:
            current_consecutive_losses = 0
        
        max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
        
        if current_equity > peak_equity:
            peak_equity = current_equity
        
        dd = (peak_equity - current_equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0
        max_drawdown_pct = max(max_drawdown_pct, dd)
        
        equity_curve.append({
            "timestamp": t.get("timestamp"),
            "equity": round(current_equity, 2),
            "pnl_krw": round(pnl, 2)
        })
    
    consecutive_losses = current_consecutive_losses
    
    # 마켓별 요약
    market_summary = {}
    for t in trades:
        m = t.get("market", "UNKNOWN")
        if m not in market_summary:
            market_summary[m] = {"trade_count": 0, "pnl_krw": 0.0, "win_count": 0}
        market_summary[m]["trade_count"] += 1
        market_summary[m]["pnl_krw"] += t.get("pnl_krw", 0.0)
        if t.get("pnl_krw", 0.0) > 0:
            market_summary[m]["win_count"] += 1
            
    for m in market_summary:
        ms = market_summary[m]
        ms["win_rate"] = round((ms["win_count"] / ms["trade_count"] * 100.0) if ms["trade_count"] > 0 else 0.0, 2)
        ms["pnl_krw"] = round(ms["pnl_krw"], 2)

    # 3. 결과 객체 생성
    result = {
        "ok": True,
        "generated_at": time.time(),
        "decision_count": decision_count,
        "trade_count": trade_count,
        "starting_cash_krw": starting_cash_krw,
        "final_equity_krw": round(final_equity_krw, 2),
        "realized_pnl_krw": round(realized_pnl_krw, 2),
        "unrealized_pnl_krw": round(unrealized_pnl_krw, 2),
        "total_pnl_krw": round(total_pnl_krw, 2),
        "total_pnl_pct": round((total_pnl_krw / starting_cash_krw * 100.0) if starting_cash_krw > 0 else 0.0, 4),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "consecutive_losses": consecutive_losses,
        "max_consecutive_losses": max_consecutive_losses,
        "market_summary": market_summary
    }

    # 4. 파일 저장
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    os.makedirs(os.path.dirname(equity_output_path), exist_ok=True)
    with open(equity_output_path, "w", encoding="utf-8") as f:
        for point in equity_curve:
            f.write(json.dumps(point, ensure_ascii=False) + "\n")
            
    os.makedirs(os.path.dirname(summary_output_path), exist_ok=True)
    build_summary_txt(result, summary_output_path)

    return result

def build_summary_txt(res: Dict[str, Any], path: str):
    dt_str = datetime.fromtimestamp(res["generated_at"]).strftime('%Y-%m-%d %H:%M:%S')
    
    lines = [
        "[페이퍼 트레이딩 성과 요약]",
        f"- 생성 시간: {dt_str}",
        f"- 총 판단 횟수: {res['decision_count']:,}",
        f"- 총 거래 횟수: {res['trade_count']:,}",
        f"- 시작 자산: {res['starting_cash_krw']:,} KRW",
        f"- 최종 자산: {res['final_equity_krw']:,} KRW",
        f"- 누적 수익: {res['total_pnl_krw']:,} KRW ({res['total_pnl_pct']:.4f}%)",
        f"- 실현 수익: {res['realized_pnl_krw']:,} KRW",
        f"- 미실현 수익: {res['unrealized_pnl_krw']:,} KRW",
        f"- 승리: {res['win_count']} / 패배: {res['loss_count']} (승률: {res['win_rate']:.2f}%)",
        f"- 평균 수익률: {res['avg_pnl_pct']:.4f}%",
        f"- 최대 낙폭(MDD): {res['max_drawdown_pct']:.4f}%",
        f"- 현재 연속 손실: {res['consecutive_losses']}",
        f"- 최대 연속 손실: {res['max_consecutive_losses']}",
        "",
        "[마켓별 요약]"
    ]
    
    for m, s in res["market_summary"].items():
        lines.append(f"- {m}: {s['trade_count']}회, 수익 {s['pnl_krw']:,} KRW, 승률 {s['win_rate']}%")
        
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
