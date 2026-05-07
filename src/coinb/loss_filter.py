from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .jsonl import read_jsonl


@dataclass
class LossFilterDecision:
    ok: bool
    reason: str
    market: str
    recent_trade_count: int = 0
    recent_win_rate: float = 0.0
    recent_expectancy_pct: float = 0.0
    consecutive_losses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LossPatternFilter:
    def __init__(
        self,
        trades_path: str = "logs/trades.jsonl",
        enabled: bool = True,
        lookback_trades: int = 20,
        min_recent_trades: int = 5,
        max_consecutive_losses: int = 3,
        min_recent_win_rate: float = 0.25,
        min_expectancy_pct: float = -0.20,
    ) -> None:
        self.trades_path = trades_path
        self.enabled = enabled
        self.lookback_trades = lookback_trades
        self.min_recent_trades = min_recent_trades
        self.max_consecutive_losses = max_consecutive_losses
        self.min_recent_win_rate = min_recent_win_rate
        self.min_expectancy_pct = min_expectancy_pct

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "LossPatternFilter":
        paths = config.get("paths", {})
        loss_filter = config.get("loss_filter", {})

        return cls(
            trades_path=paths.get("trades_log", "logs/trades.jsonl"),
            enabled=bool(loss_filter.get("enabled", True)),
            lookback_trades=int(loss_filter.get("lookback_trades", 20)),
            min_recent_trades=int(loss_filter.get("min_recent_trades", 5)),
            max_consecutive_losses=int(loss_filter.get("max_consecutive_losses", 3)),
            min_recent_win_rate=float(loss_filter.get("min_recent_win_rate", 0.25)),
            min_expectancy_pct=float(loss_filter.get("min_expectancy_pct", -0.20)),
        )

    def check_market(self, market: str) -> LossFilterDecision:
        if not self.enabled:
            return LossFilterDecision(
                ok=True,
                reason="loss_filter_disabled",
                market=market,
            )

        trades = read_jsonl(self.trades_path)
        market_trades = [
            trade for trade in trades
            if str(trade.get("market", "")) == market
        ]

        recent_trades = market_trades[-self.lookback_trades :]

        if len(recent_trades) < self.min_recent_trades:
            return LossFilterDecision(
                ok=True,
                reason="insufficient_recent_trades",
                market=market,
                recent_trade_count=len(recent_trades),
            )

        consecutive_losses = calc_consecutive_losses(recent_trades)
        win_rate = calc_win_rate(recent_trades)
        expectancy_pct = calc_expectancy_pct(recent_trades)

        if consecutive_losses >= self.max_consecutive_losses:
            return LossFilterDecision(
                ok=False,
                reason="too_many_consecutive_losses",
                market=market,
                recent_trade_count=len(recent_trades),
                recent_win_rate=win_rate,
                recent_expectancy_pct=expectancy_pct,
                consecutive_losses=consecutive_losses,
            )

        if win_rate < self.min_recent_win_rate:
            return LossFilterDecision(
                ok=False,
                reason="recent_win_rate_too_low",
                market=market,
                recent_trade_count=len(recent_trades),
                recent_win_rate=win_rate,
                recent_expectancy_pct=expectancy_pct,
                consecutive_losses=consecutive_losses,
            )

        if expectancy_pct < self.min_expectancy_pct:
            return LossFilterDecision(
                ok=False,
                reason="recent_expectancy_negative",
                market=market,
                recent_trade_count=len(recent_trades),
                recent_win_rate=win_rate,
                recent_expectancy_pct=expectancy_pct,
                consecutive_losses=consecutive_losses,
            )

        return LossFilterDecision(
            ok=True,
            reason="loss_filter_ok",
            market=market,
            recent_trade_count=len(recent_trades),
            recent_win_rate=win_rate,
            recent_expectancy_pct=expectancy_pct,
            consecutive_losses=consecutive_losses,
        )


def calc_consecutive_losses(trades: List[Dict[str, Any]]) -> int:
    count = 0

    for trade in reversed(trades):
        pnl_krw = _to_float(trade.get("pnl_krw", 0.0))

        if pnl_krw < 0:
            count += 1
        else:
            break

    return count


def calc_win_rate(trades: List[Dict[str, Any]]) -> float:
    if not trades:
        return 0.0

    wins = [
        trade for trade in trades
        if _to_float(trade.get("pnl_krw", 0.0)) > 0
    ]

    return round(len(wins) / len(trades), 4)


def calc_expectancy_pct(trades: List[Dict[str, Any]]) -> float:
    if not trades:
        return 0.0

    pnl_pct_values = [
        _to_float(trade.get("pnl_pct", 0.0))
        for trade in trades
    ]

    return round(sum(pnl_pct_values) / len(pnl_pct_values), 4)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0