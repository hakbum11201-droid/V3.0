from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional

from .market_rules import (
    apply_slippage,
    assert_min_order,
    calc_fee_krw,
    calc_order_value_krw,
    calc_qty_from_krw,
)
from .models import Position, Signal, Trade


class PaperBroker:
    def __init__(
        self,
        starting_cash_krw: float,
        fee_rate: float,
        slippage_pct: float,
        min_order_krw: float,
    ) -> None:
        if starting_cash_krw <= 0:
            raise ValueError("starting_cash_krw must be positive")

        self.starting_cash_krw = starting_cash_krw
        self.cash_krw = starting_cash_krw
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.min_order_krw = min_order_krw

        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.decision_logs: List[dict] = []

    def has_position(self, market: str) -> bool:
        return market in self.positions

    def open_position_count(self) -> int:
        return len(self.positions)

    def can_buy(self, market: str, amount_krw: float) -> bool:
        if self.has_position(market):
            return False

        if amount_krw < self.min_order_krw:
            return False

        return self.cash_krw >= amount_krw

    def buy(
        self,
        timestamp: str,
        signal: Signal,
        amount_krw: float,
    ) -> Optional[Position]:
        market = signal.market

        if not self.can_buy(market, amount_krw):
            self.decision_logs.append(
                {
                    "timestamp": timestamp,
                    "market": market,
                    "action": "BUY_BLOCKED",
                    "reason": "insufficient_cash_or_existing_position_or_min_order",
                    "amount_krw": amount_krw,
                    "cash_krw": self.cash_krw,
                    "signal": signal.to_dict(),
                }
            )
            return None

        assert_min_order(amount_krw, self.min_order_krw)

        entry_price = apply_slippage(
            price=signal.entry_price,
            slippage_pct=self.slippage_pct,
            side="buy",
        )

        entry_fee_krw = calc_fee_krw(amount_krw, self.fee_rate)
        spend_krw = amount_krw - entry_fee_krw
        qty = calc_qty_from_krw(spend_krw, entry_price)

        stop_price = entry_price * (1.0 - (signal.stop_loss_pct / 100.0))
        take_profit_price = entry_price * (1.0 + (signal.take_profit_pct / 100.0))

        position = Position(
            market=market,
            entry_timestamp=timestamp,
            entry_price=entry_price,
            qty=qty,
            entry_fee_krw=entry_fee_krw,
            reason_entry=signal.reason,
            bars_held=0,
            peak_price=entry_price,
            trough_price=entry_price,
            max_profit_pct=0.0,
            max_drawdown_pct=0.0,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=signal.trailing_stop_pct,
        )

        self.cash_krw -= amount_krw
        self.positions[market] = position

        self.decision_logs.append(
            {
                "timestamp": timestamp,
                "market": market,
                "action": "VIRTUAL_BUY",
                "amount_krw": amount_krw,
                "entry_price": entry_price,
                "qty": qty,
                "fee_krw": entry_fee_krw,
                "signal": signal.to_dict(),
            }
        )

        return position

    def update_position_price(self, market: str, price: float) -> None:
        position = self.positions.get(market)

        if position is None:
            return

        position.bars_held += 1
        position.peak_price = max(position.peak_price, price)
        position.trough_price = min(position.trough_price, price)

        profit_pct = ((position.peak_price - position.entry_price) / position.entry_price) * 100.0
        drawdown_pct = ((position.trough_price - position.entry_price) / position.entry_price) * 100.0

        position.max_profit_pct = max(position.max_profit_pct, profit_pct)
        position.max_drawdown_pct = min(position.max_drawdown_pct, drawdown_pct)

    def check_exit_reason(self, market: str, price: float, max_holding_bars: int) -> Optional[str]:
        position = self.positions.get(market)

        if position is None:
            return None

        if price <= position.stop_price:
            return "stop_loss"

        if price >= position.take_profit_price:
            return "take_profit"

        if position.trailing_stop_pct > 0 and position.peak_price > position.entry_price:
            trailing_stop_price = position.peak_price * (1.0 - (position.trailing_stop_pct / 100.0))

            if price <= trailing_stop_price:
                return "trailing_stop"

        if max_holding_bars > 0 and position.bars_held >= max_holding_bars:
            return "max_holding_bars"

        return None

    def sell(
        self,
        timestamp: str,
        market: str,
        price: float,
        reason_exit: str,
    ) -> Optional[Trade]:
        position = self.positions.get(market)

        if position is None:
            return None

        exit_price = apply_slippage(
            price=price,
            slippage_pct=self.slippage_pct,
            side="sell",
        )

        gross_exit_krw = calc_order_value_krw(exit_price, position.qty)
        exit_fee_krw = calc_fee_krw(gross_exit_krw, self.fee_rate)
        net_exit_krw = gross_exit_krw - exit_fee_krw

        entry_value_krw = position.entry_price * position.qty
        total_fee_krw = position.entry_fee_krw + exit_fee_krw
        pnl_krw = net_exit_krw - entry_value_krw
        pnl_pct = (pnl_krw / entry_value_krw) * 100.0 if entry_value_krw > 0 else 0.0

        self.cash_krw += net_exit_krw

        trade = Trade(
            timestamp=timestamp,
            market=market,
            side="SELL",
            entry_price=position.entry_price,
            exit_price=exit_price,
            qty=position.qty,
            pnl_krw=pnl_krw,
            pnl_pct=pnl_pct,
            fee_krw=total_fee_krw,
            reason_entry=position.reason_entry,
            reason_exit=reason_exit,
            max_profit_pct=position.max_profit_pct,
            max_drawdown_pct=position.max_drawdown_pct,
            holding_bars=position.bars_held,
        )

        self.trades.append(trade)
        del self.positions[market]

        self.decision_logs.append(
            {
                "timestamp": timestamp,
                "market": market,
                "action": "VIRTUAL_SELL",
                "reason_exit": reason_exit,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "qty": position.qty,
                "pnl_krw": pnl_krw,
                "pnl_pct": pnl_pct,
                "fee_krw": total_fee_krw,
                "position": asdict(position),
            }
        )

        return trade

    def equity_krw(self, last_prices: Dict[str, float]) -> float:
        equity = self.cash_krw

        for market, position in self.positions.items():
            last_price = last_prices.get(market, position.entry_price)
            equity += position.qty * last_price

        return equity

    def force_close_all(
        self,
        timestamp: str,
        last_prices: Dict[str, float],
        reason_exit: str = "force_close_end_of_backtest",
    ) -> List[Trade]:
        closed_trades: List[Trade] = []

        for market in list(self.positions.keys()):
            position = self.positions[market]
            price = last_prices.get(market, position.entry_price)
            trade = self.sell(timestamp, market, price, reason_exit)

            if trade is not None:
                closed_trades.append(trade)

        return closed_trades