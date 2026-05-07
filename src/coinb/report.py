from __future__ import annotations
import json, math
from pathlib import Path
from typing import Dict, Any, List
from .jsonl import read_jsonl
from .config_loader import load_config

def max_drawdown_from_equity(equity_curve: List[float]) -> float:
    peak=-10**18
    max_dd=0.0
    for e in equity_curve:
        peak=max(peak,e)
        if peak > 0:
            max_dd=min(max_dd, (e/peak)-1)
    return max_dd

def analyze_trades(trades: List[Dict[str, Any]], initial_cash: float = 1_000_000) -> Dict[str, Any]:
    total=len(trades)
    wins=[t for t in trades if float(t.get("pnl_krw",0)) > 0]
    losses=[t for t in trades if float(t.get("pnl_krw",0)) < 0]
    pnl=[float(t.get("pnl_krw",0)) for t in trades]
    pnl_pct=[float(t.get("pnl_pct",0)) for t in trades]
    gross_win=sum(x for x in pnl if x>0)
    gross_loss=abs(sum(x for x in pnl if x<0))
    equity=initial_cash
    curve=[]
    consecutive_losses=0
    max_consecutive_losses=0
    by_market: Dict[str, Dict[str, float]]={}
    for t in trades:
        p=float(t.get("pnl_krw",0))
        equity += p
        curve.append(equity)
        if p < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0
        max_consecutive_losses=max(max_consecutive_losses, consecutive_losses)
        m=t.get("market","UNKNOWN")
        st=by_market.setdefault(m,{"trades":0,"pnl":0.0,"wins":0})
        st["trades"] += 1
        st["pnl"] += p
        if p > 0: st["wins"] += 1
    best_market=max(by_market.items(), key=lambda kv: kv[1]["pnl"])[0] if by_market else None
    worst_market=min(by_market.items(), key=lambda kv: kv[1]["pnl"])[0] if by_market else None
    return {
        "total_trades": total,
        "win_rate": len(wins)/total if total else 0.0,
        "avg_win_pct": sum(float(t.get("pnl_pct",0)) for t in wins)/len(wins) if wins else 0.0,
        "avg_loss_pct": sum(float(t.get("pnl_pct",0)) for t in losses)/len(losses) if losses else 0.0,
        "profit_factor": gross_win/gross_loss if gross_loss else (999.0 if gross_win else 0.0),
        "expectancy_krw": sum(pnl)/total if total else 0.0,
        "expectancy_pct": sum(pnl_pct)/total if total else 0.0,
        "max_drawdown": max_drawdown_from_equity(curve),
        "total_pnl_krw": sum(pnl),
        "roi_pct": (sum(pnl)/initial_cash) if initial_cash else 0.0,
        "best_market": best_market,
        "worst_market": worst_market,
        "consecutive_losses": max_consecutive_losses,
        "by_market": by_market,
    }

def run_report(config_path: str = "config/config.json") -> Dict[str, Any]:
    cfg=load_config(config_path)
    trades=list(read_jsonl(Path(cfg["paths"]["logs_dir"])/"trades.jsonl"))
    report=analyze_trades(trades, cfg["portfolio"]["initial_cash_krw"])
    out=Path(cfg["paths"]["reports_dir"])/"performance_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
