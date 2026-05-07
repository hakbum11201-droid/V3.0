from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .config_loader import load_config
from .jsonl import read_jsonl, write_json


def run_report(config_path: str = "config/config.json") -> Dict[str, Any]:
    config = load_config(config_path)
    paths_config = config.get("paths", {})

    trades_path = paths_config.get("trades_log", "logs/trades.jsonl")
    report_path = paths_config.get("performance_report", "reports/performance_summary.json")

    trades = read_jsonl(trades_path)
    summary = build_performance_summary(trades)

    report = {
        "ok": True,
        "command": "report",
        "exchange": "upbit",
        "market_type": "KRW",
        "source": trades_path,
        "report_path": report_path,
        "summary": summary,
    }

    write_json(report_path, report)

    return report


def build_performance_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_pct": 0.0,
            "max_drawdown_krw": 0.0,
            "total_pnl_krw": 0.0,
            "best_market": "",
            "worst_market": "",
            "consecutive_losses": 0,
        }

    pnl_values = [_to_float(trade.get("pnl_krw", 0.0)) for trade in trades]
    pnl_pct_values = [_to_float(trade.get("pnl_pct", 0.0)) for trade in trades]

    wins = [value for value in pnl_pct_values if value > 0]
    losses = [value for value in pnl_pct_values if value < 0]

    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))

    total_trades = len(trades)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

    avg_win_pct = sum(wins) / len(wins) if wins else 0.0
    avg_loss_pct = sum(losses) / len(losses) if losses else 0.0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
    expectancy_pct = sum(pnl_pct_values) / total_trades if total_trades > 0 else 0.0

    total_pnl_krw = sum(pnl_values)
    max_drawdown_krw = calc_max_drawdown_krw(pnl_values)

    market_pnl = calc_market_pnl(trades)
    best_market = max(market_pnl, key=market_pnl.get) if market_pnl else ""
    worst_market = min(market_pnl, key=market_pnl.get) if market_pnl else ""

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "avg_win_pct": round(avg_win_pct, 4),
        "avg_loss_pct": round(avg_loss_pct, 4),
        "profit_factor": round(profit_factor, 4),
        "expectancy_pct": round(expectancy_pct, 4),
        "max_drawdown_krw": round(max_drawdown_krw, 2),
        "total_pnl_krw": round(total_pnl_krw, 2),
        "best_market": best_market,
        "worst_market": worst_market,
        "market_pnl_krw": {
            market: round(value, 2)
            for market, value in market_pnl.items()
        },
        "consecutive_losses": calc_max_consecutive_losses(trades),
    }


def calc_market_pnl(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    result: Dict[str, float] = defaultdict(float)

    for trade in trades:
        market = str(trade.get("market", "UNKNOWN"))
        result[market] += _to_float(trade.get("pnl_krw", 0.0))

    return dict(result)


def calc_max_consecutive_losses(trades: List[Dict[str, Any]]) -> int:
    max_losses = 0
    current_losses = 0

    for trade in trades:
        pnl_krw = _to_float(trade.get("pnl_krw", 0.0))

        if pnl_krw < 0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0

    return max_losses


def calc_max_drawdown_krw(pnl_values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for pnl in pnl_values:
        equity += pnl
        peak = max(peak, equity)
        drawdown = peak - equity
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0