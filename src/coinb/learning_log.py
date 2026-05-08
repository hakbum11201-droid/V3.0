from __future__ import annotations

from typing import Any, Dict, List

from .jsonl import read_jsonl, write_json, write_jsonl


FEATURE_KEYS = [
    "ofi_score",
    "sweep_score",
    "absorption_score",
    "continuation_score",
    "spread_pct",
    "buy_trade_value_3s",
    "sell_trade_value_3s",
    "bid_ask_depth_ratio_5",
]


def build_learning_dataset(
    decisions_path: str = "logs/orderflow_paper_decisions.jsonl",
    trades_path: str = "logs/orderflow_paper_trades.jsonl",
    output_path: str = "logs/orderflow_learning_dataset.jsonl",
    summary_path: str = "reports/orderflow_learning_summary.json",
) -> Dict[str, Any]:
    decisions = read_jsonl(decisions_path)
    trades = read_jsonl(trades_path)

    rows: List[Dict[str, Any]] = []

    for decision in decisions:
        rows.append(build_decision_learning_row(decision))

    for trade in trades:
        rows.append(build_trade_learning_row(trade))

    write_jsonl(output_path, rows)

    summary = build_learning_summary(rows)

    report = {
        "ok": True,
        "command": "learning-log",
        "source_decisions": decisions_path,
        "source_trades": trades_path,
        "output_path": output_path,
        "summary_path": summary_path,
        "summary": summary,
    }

    write_json(summary_path, report)

    return report


def build_decision_learning_row(decision: Dict[str, Any]) -> Dict[str, Any]:
    details = decision.get("details", {})

    if not isinstance(details, dict):
        details = {}

    action = str(decision.get("action", "UNKNOWN"))
    reason = str(decision.get("reason", ""))

    row = {
        "row_type": "decision",
        "timestamp": _to_float(decision.get("timestamp", 0.0)),
        "market": str(decision.get("market", "")),
        "action": action,
        "reason": reason,
        "score": _to_float(decision.get("score", 0.0)),
        "price": _to_float(decision.get("price", 0.0)),
        "label": decision_label(action),
        "outcome_known": False,
        "pnl_krw": 0.0,
        "pnl_pct": 0.0,
    }

    for key in FEATURE_KEYS:
        row[key] = _to_float(details.get(key, 0.0))

    return row


def build_trade_learning_row(trade: Dict[str, Any]) -> Dict[str, Any]:
    pnl_krw = _to_float(trade.get("pnl_krw", 0.0))
    pnl_pct = _to_float(trade.get("pnl_pct", 0.0))

    row = {
        "row_type": "trade",
        "timestamp": _to_float(trade.get("timestamp", 0.0)),
        "market": str(trade.get("market", "")),
        "action": str(trade.get("side", "VIRTUAL_SELL")),
        "reason": str(trade.get("reason_exit", "")),
        "reason_entry": str(trade.get("reason_entry", "")),
        "score": 0.0,
        "price": _to_float(trade.get("exit_price", 0.0)),
        "entry_price": _to_float(trade.get("entry_price", 0.0)),
        "exit_price": _to_float(trade.get("exit_price", 0.0)),
        "qty": _to_float(trade.get("qty", 0.0)),
        "fee_krw": _to_float(trade.get("fee_krw", 0.0)),
        "max_profit_pct": _to_float(trade.get("max_profit_pct", 0.0)),
        "max_drawdown_pct": _to_float(trade.get("max_drawdown_pct", 0.0)),
        "holding_seconds": _to_float(trade.get("holding_seconds", 0.0)),
        "label": trade_label(pnl_krw),
        "outcome_known": True,
        "pnl_krw": pnl_krw,
        "pnl_pct": pnl_pct,
    }

    for key in FEATURE_KEYS:
        row[key] = 0.0

    return row


def build_learning_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    decision_rows = [row for row in rows if row.get("row_type") == "decision"]
    trade_rows = [row for row in rows if row.get("row_type") == "trade"]

    virtual_buy_rows = [
        row for row in decision_rows
        if row.get("action") == "VIRTUAL_BUY"
    ]

    no_buy_rows = [
        row for row in decision_rows
        if row.get("action") == "NO_BUY"
    ]

    hold_rows = [
        row for row in decision_rows
        if row.get("action") == "HOLD_POSITION"
    ]

    win_trades = [
        row for row in trade_rows
        if _to_float(row.get("pnl_krw", 0.0)) > 0
    ]

    loss_trades = [
        row for row in trade_rows
        if _to_float(row.get("pnl_krw", 0.0)) < 0
    ]

    total_pnl_krw = sum(_to_float(row.get("pnl_krw", 0.0)) for row in trade_rows)
    avg_pnl_pct = average([_to_float(row.get("pnl_pct", 0.0)) for row in trade_rows])

    return {
        "total_rows": len(rows),
        "decision_rows": len(decision_rows),
        "trade_rows": len(trade_rows),
        "virtual_buy_count": len(virtual_buy_rows),
        "no_buy_count": len(no_buy_rows),
        "hold_count": len(hold_rows),
        "win_trade_count": len(win_trades),
        "loss_trade_count": len(loss_trades),
        "win_rate": round(len(win_trades) / len(trade_rows), 4) if trade_rows else 0.0,
        "total_pnl_krw": round(total_pnl_krw, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 4),
        "markets": sorted({str(row.get("market", "")) for row in rows if row.get("market")}),
    }


def decision_label(action: str) -> str:
    if action == "VIRTUAL_BUY":
        return "entry_candidate"

    if action == "NO_BUY":
        return "rejected"

    if action == "HOLD_POSITION":
        return "hold"

    if action == "SKIP":
        return "skip"

    return "unknown"


def trade_label(pnl_krw: float) -> str:
    if pnl_krw > 0:
        return "win"

    if pnl_krw < 0:
        return "loss"

    return "flat"


def average(values: List[float]) -> float:
    if not values:
        return 0.0

    return sum(values) / len(values)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0