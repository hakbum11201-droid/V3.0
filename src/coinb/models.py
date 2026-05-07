from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class Candle:
    market: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    market: str
    action: str
    score: float
    reason: str
    entry_price: float = 0.0
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    indicators: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    market: str
    entry_timestamp: str
    entry_price: float
    qty: float
    entry_fee_krw: float
    reason_entry: str
    bars_held: int = 0
    peak_price: float = 0.0
    trough_price: float = 0.0
    max_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    stop_price: float = 0.0
    take_profit_price: float = 0.0
    trailing_stop_pct: float = 0.0


@dataclass
class Trade:
    timestamp: str
    market: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl_krw: float
    pnl_pct: float
    fee_krw: float
    reason_entry: str
    reason_exit: str
    max_profit_pct: float
    max_drawdown_pct: float
    holding_bars: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)