from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class RiskDecision:
    ok: bool
    reason: str
    amount_krw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskManager:
    def __init__(
        self,
        starting_cash_krw: float,
        max_position_krw: float,
        position_size_pct: float,
        max_open_positions: int,
        min_order_krw: float,
        daily_loss_limit_pct: float,
        total_loss_limit_pct: float,
        max_consecutive_losses: int,
    ) -> None:
        if starting_cash_krw <= 0:
            raise ValueError("starting_cash_krw must be positive")

        self.starting_cash_krw = starting_cash_krw
        self.max_position_krw = max_position_krw
        self.position_size_pct = position_size_pct
        self.max_open_positions = max_open_positions
        self.min_order_krw = min_order_krw
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.total_loss_limit_pct = total_loss_limit_pct
        self.max_consecutive_losses = max_consecutive_losses

        self.realized_pnl_krw = 0.0
        self.consecutive_losses = 0
        self.trade_count = 0
        self.loss_trade_count = 0
        self.win_trade_count = 0
        self.is_stopped = False
        self.stop_reason = ""

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RiskManager":
        portfolio = config.get("portfolio", {})
        risk = config.get("risk", {})

        return cls(
            starting_cash_krw=float(portfolio.get("starting_cash_krw", 1_000_000)),
            max_position_krw=float(portfolio.get("max_position_krw", 100_000)),
            position_size_pct=float(portfolio.get("position_size_pct", 10.0)),
            max_open_positions=int(portfolio.get("max_open_positions", 3)),
            min_order_krw=float(risk.get("min_order_krw", 5_000)),
            daily_loss_limit_pct=float(risk.get("daily_loss_limit_pct", 3.0)),
            total_loss_limit_pct=float(risk.get("total_loss_limit_pct", 10.0)),
            max_consecutive_losses=int(risk.get("max_consecutive_losses", 4)),
        )

    def calc_order_amount_krw(self, equity_krw: float) -> float:
        if equity_krw <= 0:
            return 0.0

        pct_amount = equity_krw * (self.position_size_pct / 100.0)
        amount = min(self.max_position_krw, pct_amount)

        return max(0.0, amount)

    def check_entry(
        self,
        market: str,
        cash_krw: float,
        equity_krw: float,
        open_position_count: int,
        already_has_position: bool,
    ) -> RiskDecision:
        if self.is_stopped:
            return RiskDecision(False, f"risk_stopped:{self.stop_reason}")

        if already_has_position:
            return RiskDecision(False, "already_has_position")

        if open_position_count >= self.max_open_positions:
            return RiskDecision(False, "max_open_positions_reached")

        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_stopped = True
            self.stop_reason = "max_consecutive_losses"
            return RiskDecision(False, "max_consecutive_losses")

        if self._total_loss_limit_reached(equity_krw):
            self.is_stopped = True
            self.stop_reason = "total_loss_limit_reached"
            return RiskDecision(False, "total_loss_limit_reached")

        if self._daily_loss_limit_reached():
            self.is_stopped = True
            self.stop_reason = "daily_loss_limit_reached"
            return RiskDecision(False, "daily_loss_limit_reached")

        amount_krw = self.calc_order_amount_krw(equity_krw)

        if amount_krw < self.min_order_krw:
            return RiskDecision(False, "amount_below_min_order", amount_krw)

        if cash_krw < amount_krw:
            return RiskDecision(False, "insufficient_cash", amount_krw)

        return RiskDecision(True, "entry_allowed", amount_krw)

    def record_trade_result(self, pnl_krw: float) -> None:
        self.trade_count += 1
        self.realized_pnl_krw += pnl_krw

        if pnl_krw < 0:
            self.loss_trade_count += 1
            self.consecutive_losses += 1
        else:
            self.win_trade_count += 1
            self.consecutive_losses = 0

        if self._daily_loss_limit_reached():
            self.is_stopped = True
            self.stop_reason = "daily_loss_limit_reached"

    def _daily_loss_limit_reached(self) -> bool:
        if self.daily_loss_limit_pct <= 0:
            return False

        loss_limit_krw = self.starting_cash_krw * (self.daily_loss_limit_pct / 100.0)
        return self.realized_pnl_krw <= -loss_limit_krw

    def _total_loss_limit_reached(self, equity_krw: float) -> bool:
        if self.total_loss_limit_pct <= 0:
            return False

        min_equity_krw = self.starting_cash_krw * (1.0 - (self.total_loss_limit_pct / 100.0))
        return equity_krw <= min_equity_krw

    def to_dict(self) -> Dict[str, Any]:
        return {
            "starting_cash_krw": self.starting_cash_krw,
            "max_position_krw": self.max_position_krw,
            "position_size_pct": self.position_size_pct,
            "max_open_positions": self.max_open_positions,
            "min_order_krw": self.min_order_krw,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "total_loss_limit_pct": self.total_loss_limit_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "realized_pnl_krw": self.realized_pnl_krw,
            "consecutive_losses": self.consecutive_losses,
            "trade_count": self.trade_count,
            "loss_trade_count": self.loss_trade_count,
            "win_trade_count": self.win_trade_count,
            "is_stopped": self.is_stopped,
            "stop_reason": self.stop_reason,
        }