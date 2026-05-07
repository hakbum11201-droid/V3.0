from __future__ import annotations
from typing import Dict, Any
from .market_rules import is_min_order

class RiskManager:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg=cfg
        self.port=cfg["portfolio"]
        self.risk=cfg["risk"]
        self.ex=cfg["exchange"]

    def approve_entry(self, market: str, signal, equity: float, cash: float, open_positions: int, state: Dict[str, Any]) -> Dict[str, Any]:
        if signal.action != "ENTER_LONG":
            return {"allow":False, "reason":"no_entry_signal", "size_krw":0}
        if open_positions >= self.port["max_open_positions"]:
            return {"allow":False, "reason":"max_open_positions", "size_krw":0}
        if cash <= equity * self.port["reserve_cash_pct"]:
            return {"allow":False, "reason":"reserve_cash", "size_krw":0}
        if float(state.get("daily_pnl_krw",0)) <= -equity * self.risk["daily_loss_limit_pct"]:
            return {"allow":False, "reason":"daily_loss_limit", "size_krw":0}
        if float(state.get("total_pnl_krw",0)) <= -equity * self.risk["total_loss_limit_pct"]:
            return {"allow":False, "reason":"total_loss_limit", "size_krw":0}
        atr=float(signal.meta.get("atr",0))
        price=float(signal.meta.get("close",0))
        if price <= 0 or atr <= 0:
            return {"allow":False, "reason":"invalid_price_or_atr", "size_krw":0}
        stop_distance_pct=max((atr * self.cfg["strategy"]["stop_loss_atr"]) / price, 0.003)
        risk_budget=equity * self.port["risk_per_trade_pct"]
        size_by_risk=risk_budget / stop_distance_pct
        size_krw=min(size_by_risk, self.port["max_position_krw"], cash * (1-self.port["reserve_cash_pct"]))
        if not is_min_order(size_krw, self.ex["min_order_krw"]):
            return {"allow":False, "reason":"below_min_order", "size_krw":0}
        if signal.meta.get("atr_pct",0) < self.risk["min_atr_pct"] or signal.meta.get("atr_pct",0) > self.risk["max_atr_pct"]:
            return {"allow":False, "reason":"atr_pct_out_of_range", "size_krw":0}
        return {"allow":True, "reason":"risk_ok", "size_krw":round(size_krw,2), "stop_distance_pct":stop_distance_pct}
