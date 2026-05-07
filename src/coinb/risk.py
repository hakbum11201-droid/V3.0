from __future__ import annotations

from typing import Dict, Any

from .models import Signal
from .market_rules import is_min_order


class RiskManager:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.p = cfg["portfolio"]
        self.r = cfg["risk"]

    def approve_entry(
        self,
        market: str,
        signal: Signal,
        equity: float,
        cash: float,
        open_positions: int,
        state: dict,
    ) -> Dict[str, Any]:
        if signal.action != "ENTER_LONG":
            return {"allow": False, "reason": "no_entry_signal", "size_krw": 0}

        if open_positions >= int(self.p["max_positions"]):
            return {"allow": False, "reason": "max_positions", "size_krw": 0}

        if int(state.get("consecutive_losses", 0)) >= int(self.r["max_consecutive_losses"]):
            return {"allow": False, "reason": "consecutive_loss_cut", "size_krw": 0}

        initial = float(self.p["initial_cash_krw"])
        total_pnl = float(state.get("total_pnl_krw", 0))
        if total_pnl <= -initial * float(self.r["total_loss_limit_pct"]):
            return {"allow": False, "reason": "total_loss_limit", "size_krw": 0}

        size_krw = min(
            cash,
            equity * float(self.p["position_size_pct"]),
        )

        if not is_min_order(size_krw, float(self.p["min_order_krw"])):
            return {"allow": False, "reason": "below_min_order", "size_krw": size_krw}

        if cash < size_krw:
            return {"allow": False, "reason": "not_enough_cash", "size_krw": size_krw}

        return {"allow": True, "reason": "approved", "size_krw": round(size_krw, 2)}
