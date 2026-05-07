from __future__ import annotations
from typing import Dict, List, Any, Optional
from datetime import datetime
from .models import Position, Trade, Signal, Candle
from .market_rules import round_price_down

class PaperBroker:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg=cfg
        self.cash=float(cfg["portfolio"]["initial_cash_krw"])
        self.initial_cash=self.cash
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.fee=cfg["exchange"]["fee_rate"]
        self.slip=cfg["exchange"]["slippage_rate"]
        self.s=cfg["strategy"]

    def equity(self, last_prices: Dict[str, float]) -> float:
        value=self.cash
        for m,p in self.positions.items():
            value += p.qty * last_prices.get(m, p.entry_price)
        return value

    def enter_long(self, candle: Candle, size_krw: float, signal: Signal) -> Optional[Position]:
        if candle.market in self.positions:
            return None
        price=round_price_down(candle.close * (1 + self.slip))
        total_cost=size_krw
        fee_krw=total_cost*self.fee
        if self.cash < total_cost + fee_krw:
            return None
        qty=(total_cost-fee_krw)/price
        atr=float(signal.meta.get("atr", candle.close*0.01))
        stop=price - atr*self.s["stop_loss_atr"]
        tp=price + atr*self.s["take_profit_atr"]
        tr=price - atr*self.s["trailing_atr"]
        pos=Position(candle.market, candle.timestamp, price, qty, stop, tp, tr, price, reason_entry=signal.reason)
        self.cash -= total_cost
        self.positions[candle.market]=pos
        return pos

    def update_position(self, candle: Candle) -> Optional[Trade]:
        pos=self.positions.get(candle.market)
        if not pos:
            return None
        pos.bars_held += 1
        pos.highest_price=max(pos.highest_price, candle.high)
        pnl_pct_now=(candle.close/pos.entry_price)-1
        pos.max_profit_pct=max(pos.max_profit_pct, pnl_pct_now)
        pos.max_drawdown_pct=min(pos.max_drawdown_pct, pnl_pct_now)
        # trailing stop only ratchets upward
        atr_proxy=(candle.high-candle.low) if candle.high>candle.low else pos.entry_price*0.005
        new_trail=pos.highest_price - atr_proxy*self.s["trailing_atr"]
        pos.trailing_stop_price=max(pos.trailing_stop_price, new_trail)
        reason=None
        exit_price=None
        if candle.low <= pos.stop_price:
            reason="stop_loss"; exit_price=pos.stop_price
        elif candle.low <= pos.trailing_stop_price and pos.max_profit_pct > 0.002:
            reason="trailing_stop"; exit_price=pos.trailing_stop_price
        elif candle.high >= pos.take_profit_price:
            reason="take_profit"; exit_price=pos.take_profit_price
        if reason:
            return self.exit_position(candle, reason, exit_price)
        return None

    def exit_by_signal(self, candle: Candle, signal: Signal) -> Optional[Trade]:
        if signal.action == "EXIT" and candle.market in self.positions:
            return self.exit_position(candle, signal.reason, candle.close)
        return None

    def exit_position(self, candle: Candle, reason: str, price: float) -> Optional[Trade]:
        pos=self.positions.pop(candle.market, None)
        if not pos:
            return None
        exit_price=round_price_down(price * (1 - self.slip))
        gross=exit_price*pos.qty
        fee_krw=gross*self.fee
        self.cash += gross-fee_krw
        entry_value=pos.entry_price*pos.qty
        pnl_krw=(gross-fee_krw)-entry_value
        pnl_pct=pnl_krw/entry_value if entry_value else 0.0
        trade=Trade(
            timestamp=candle.timestamp, market=candle.market, side="SELL", entry_time=pos.entry_time,
            entry_price=pos.entry_price, exit_price=exit_price, qty=pos.qty, pnl_krw=pnl_krw,
            pnl_pct=pnl_pct, fee_krw=fee_krw, reason_entry=pos.reason_entry, reason_exit=reason,
            max_profit_pct=pos.max_profit_pct, max_drawdown_pct=pos.max_drawdown_pct,
            holding_bars=pos.bars_held, holding_seconds=pos.bars_held*60,
        )
        self.trades.append(trade)
        return trade
