from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .jsonl import read_jsonl, write_json


def build_orderflow_loss_analysis(
    decisions_path: str = "logs/orderflow_paper_decisions.jsonl",
    trades_path: str = "logs/orderflow_paper_trades.jsonl",
    output_path: str = "reports/orderflow_loss_analysis.json",
    min_trades_for_block: int = 5,
    min_win_rate: float = 0.30,
    min_expectancy_pct: float = -0.10,
) -> Dict[str, Any]:
    decisions = read_jsonl(decisions_path)
    trades = read_jsonl(trades_path)

    market_summary = build_market_summary(trades)
    reason_summary = build_reason_summary(decisions)
    loss_summary = build_loss_summary(trades)

    blocked_markets = find_blocked_markets(
        market_summary=market_summary,
        min_trades_for_block=min_trades_for_block,
        min_win_rate=min_win_rate,
        min_expectancy_pct=min_expectancy_pct,
    )

    blocked_reasons = find_blocked_reasons(
        reason_summary=reason_summary,
    )

    report = {
        "ok": True,
        "command": "orderflow-loss-analysis",
        "source_decisions": decisions_path,
        "source_trades": trades_path,
        "output_path": output_path,
        "thresholds": {
            "min_trades_for_block": min_trades_for_block,
            "min_win_rate": min_win_rate,
            "min_expectancy_pct": min_expectancy_pct,
        },
        "summary": {
            "decision_count": len(decisions),
            "trade_count": len(trades),
            "total_pnl_krw": round(sum(_to_float(t.get("pnl_krw", 0.0)) for t in trades), 2),
            "avg_pnl_pct": round(average([_to_float(t.get("pnl_pct", 0.0)) for t in trades]), 4),
            "win_rate": calc_win_rate(trades),
        },
        "market_summary": market_summary,
        "reason_summary": reason_summary,
        "loss_summary": loss_summary,
        "blocked_candidates": {
            "markets": blocked_markets,
            "reasons": blocked_reasons,
        },
    }

    write_json(output_path, report)
    return report


def build_market_summary(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for trade in trades:
        market = str(trade.get("market", "UNKNOWN"))
        grouped[market].append(trade)

    result: Dict[str, Dict[str, Any]] = {}

    for market, rows in grouped.items():
        pnl_values = [_to_float(row.get("pnl_krw", 0.0)) for row in rows]
        pnl_pct_values = [_to_float(row.get("pnl_pct", 0.0)) for row in rows]

        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]

        result[market] = {
            "trade_count": len(rows),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(rows), 4) if rows else 0.0,
            "total_pnl_krw": round(sum(pnl_values), 2),
            "avg_pnl_pct": round(average(pnl_pct_values), 4),
            "avg_win_pct": round(average([_to_float(row.get("pnl_pct", 0.0)) for row in rows if _to_float(row.get("pnl_krw", 0.0)) > 0]), 4),
            "avg_loss_pct": round(average([_to_float(row.get("pnl_pct", 0.0)) for row in rows if _to_float(row.get("pnl_krw", 0.0)) < 0]), 4),
            "max_loss_pct": round(min(pnl_pct_values), 4) if pnl_pct_values else 0.0,
            "max_profit_pct": round(max(pnl_pct_values), 4) if pnl_pct_values else 0.0,
        }

    return result


def build_reason_summary(decisions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    for decision in decisions:
        reason = str(decision.get("reason", "UNKNOWN"))
        action = str(decision.get("action", "UNKNOWN"))

        key = f"{action}:{reason}"

        if key not in result:
            result[key] = {
                "action": action,
                "reason": reason,
                "count": 0,
                "markets": {},
                "diagnostics_sample": [],
            }

        result[key]["count"] += 1

        market = str(decision.get("market", "UNKNOWN"))
        markets = result[key]["markets"]
        markets[market] = int(markets.get(market, 0)) + 1

        diagnostic = decision.get("diagnostic")
        if diagnostic and len(result[key]["diagnostics_sample"]) < 5:
            result[key]["diagnostics_sample"].append(diagnostic)

    return dict(sorted(result.items(), key=lambda item: item[1]["count"], reverse=True))


def build_loss_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    losses = [
        trade for trade in trades
        if _to_float(trade.get("pnl_krw", 0.0)) < 0
    ]

    if not losses:
        return {
            "loss_trade_count": 0,
            "total_loss_krw": 0.0,
            "avg_loss_pct": 0.0,
            "worst_trade": {},
            "exit_reason_counts": {},
        }

    exit_reason_counts: Dict[str, int] = defaultdict(int)
    loss_classification: Dict[str, int] = defaultdict(int)

    for trade in losses:
        reason = str(trade.get("reason_exit", "UNKNOWN"))
        exit_reason_counts[reason] += 1
        
        if "stop_loss" in reason:
            loss_classification["STOP_LOSS_HIT"] += 1
        elif "max_holding" in reason:
            loss_classification["TIME_STOP"] += 1
        elif "weak_continuation" in reason:
            loss_classification["MOMENTUM_LOSS"] += 1
        else:
            loss_classification["OTHER"] += 1

    worst_trade = min(
        losses,
        key=lambda row: _to_float(row.get("pnl_krw", 0.0)),
    )

    return {
        "loss_trade_count": len(losses),
        "total_loss_krw": round(sum(_to_float(t.get("pnl_krw", 0.0)) for t in losses), 2),
        "avg_loss_pct": round(average([_to_float(t.get("pnl_pct", 0.0)) for t in losses]), 4),
        "worst_trade": worst_trade,
        "exit_reason_counts": dict(exit_reason_counts),
        "loss_classification": dict(loss_classification),
    }


def find_blocked_markets(
    market_summary: Dict[str, Dict[str, Any]],
    min_trades_for_block: int,
    min_win_rate: float,
    min_expectancy_pct: float,
) -> List[Dict[str, Any]]:
    blocked: List[Dict[str, Any]] = []

    for market, summary in market_summary.items():
        trade_count = int(summary.get("trade_count", 0))
        win_rate = _to_float(summary.get("win_rate", 0.0))
        avg_pnl_pct = _to_float(summary.get("avg_pnl_pct", 0.0))

        if trade_count < min_trades_for_block:
            continue

        reasons: List[str] = []

        if win_rate < min_win_rate:
            reasons.append("win_rate_too_low")

        if avg_pnl_pct < min_expectancy_pct:
            reasons.append("expectancy_too_low")

        if reasons:
            blocked.append(
                {
                    "market": market,
                    "reasons": reasons,
                    "trade_count": trade_count,
                    "win_rate": win_rate,
                    "avg_pnl_pct": avg_pnl_pct,
                    "total_pnl_krw": summary.get("total_pnl_krw", 0.0),
                }
            )

    return blocked


def find_blocked_reasons(
    reason_summary: Dict[str, Dict[str, Any]],
    min_count: int = 20,
) -> List[Dict[str, Any]]:
    blocked: List[Dict[str, Any]] = []

    for key, summary in reason_summary.items():
        action = str(summary.get("action", ""))
        reason = str(summary.get("reason", ""))
        count = int(summary.get("count", 0))

        if action != "NO_BUY":
            continue

        if count >= min_count:
            blocked.append(
                {
                    "key": key,
                    "reason": reason,
                    "count": count,
                    "note": "frequent_rejection_reason",
                }
            )

    return blocked


def calc_win_rate(trades: List[Dict[str, Any]]) -> float:
    if not trades:
        return 0.0

    wins = [
        trade for trade in trades
        if _to_float(trade.get("pnl_krw", 0.0)) > 0
    ]

    return round(len(wins) / len(trades), 4)


def average(values: List[float]) -> float:
    if not values:
        return 0.0

    return sum(values) / len(values)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0