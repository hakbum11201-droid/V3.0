from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

@dataclass
class Candle:
    timestamp: str
    market: str
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Signal:
    market: str
    action: str  # ENTER_LONG, EXIT, HOLD
    score: float
    reason: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Position:
    market: str
    entry_time: str
    entry_price: float
    qty: float
    stop_price: float
    take_profit_price: float
    trailing_stop_price: float
    highest_price: float
    bars_held: int = 0
    reason_entry: str = ""
    max_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0

@dataclass
class Trade:
    timestamp: str
    market: str
    side: str
    entry_time: str
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
    holding_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
