from __future__ import annotations

from typing import Dict, Optional

from .models import Candle, Signal, Position, Trade
from .market_rules import round_price_to_tick


class PaperBroker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.cash = float(cfg["portfolio"]["initial_cash_krw"])
        self.fee_rate = float(cfg["portfolio"]["fee_rate"])
        self.slippage_rate = float(cfg["portfolio"]["slippage_rate"])
        self.positions: Dict[str, Position] = {}
        self.trades = []

    def equity(self, last_prices: Dict[str, float]) -> float:
        value = self.cash
        for market, pos in self.positions.items():
            value += pos.qty * last_prices.get(market, pos.entry_price)
        return value

    def enter_long(self, candle: Candle, size_krw: float, signal: Signal) -> Optional[Position]:
        if candle.market in self.positions:
            return None

        buy_price = round_price_to_tick(candle.close * (1 + self.slippage_rate))
        fee = size_krw * self.fee_rate
        usable = size_krw - fee
        qty = usable / buy_price

        if size_krw > self.cash:
            return None

        self.cash -= size_krw
        pos = Position(
            market=candle.market,
            entry_timestamp=candle.timestamp,
            entry_price=buy_price,
            qty=qty,
            entry_fee_krw=fee,
            reason_entry=signal.reason,
            peak_price=buy_price,
            trough_price=buy_price,
            stop_price=buy_price * (1 - signal.stop_loss_pct),
            take_profit_price=buy_price * (1 + signal.take_profit_pct),
            trailing_stop_pct=signal.trailing_stop_pct,
        )
        self.positions[candle.market] = pos
        return pos

    def update_position(self, candle: Candle) -> Optional[Trade]:
        pos = self.positions.get(candle.market)
        if pos is None:
            return None

        pos.bars_held += 1
        pos.peak_price = max(pos.peak_price, candle.high)
        pos.trough_price = min(pos.trough_price, candle.low)
        pos.max_profit_pct = max(pos.max_profit_pct, (pos.peak_price / pos.entry_price) - 1)
        pos.max_drawdown_pct = min(pos.max_drawdown_pct, (pos.trough_price / pos.entry_price) - 1)

        trailing_stop = pos.peak_price * (1 - pos.trailing_stop_pct)
        if candle.low <= pos.stop_price:
            return self.exit_position(candle, "stop_loss", pos.stop_price)
        if candle.high >= pos.take_profit_price:
            return self.exit_position(candle, "take_profit", pos.take_profit_price)
        if candle.low <= trailing_stop and pos.peak_price > pos.entry_price:
            return self.exit_position(candle, "trailing_stop", trailing_stop)

        max_bars = int(self.cfg["strategy"].get("max_holding_bars", 48))
        if pos.bars_held >= max_bars:
            return self.exit_position(candle, "time_exit", candle.close)

        return None

    def exit_by_signal(self, candle: Candle, signal: Signal) -> Optional[Trade]:
        if signal.action == "EXIT_LONG":
            return self.exit_position(candle, signal.reason, candle.close)
        return None

    def exit_position(self, candle: Candle, reason: str, raw_price: float) -> Optional[Trade]:
        pos = self.positions.get(candle.market)
        if pos is None:
            return None

        sell_price = round_price_to_tick(raw_price * (1 - self.slippage_rate))
        gross = pos.qty * sell_price
        exit_fee = gross * self.fee_rate
        net = gross - exit_fee
        self.cash += net

        cost = pos.qty * pos.entry_price + pos.entry_fee_krw
        pnl = net - cost
        pnl_pct = pnl / cost if cost else 0.0

        trade = Trade(
            timestamp=candle.timestamp,
            market=candle.market,
            side="LONG",
            entry_price=pos.entry_price,
            exit_price=sell_price,
            qty=pos.qty,
            pnl_krw=round(pnl, 2),
            pnl_pct=round(pnl_pct, 6),
            fee_krw=round(pos.entry_fee_krw + exit_fee, 2),
            reason_entry=pos.reason_entry,
            reason_exit=reason,
            max_profit_pct=round(pos.max_profit_pct, 6),
            max_drawdown_pct=round(pos.max_drawdown_pct, 6),
            holding_bars=pos.bars_held,
        )

        self.positions.pop(candle.market, None)
        self.trades.append(trade)
        return trade
