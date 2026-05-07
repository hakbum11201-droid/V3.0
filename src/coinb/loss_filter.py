from __future__ import annotations
from typing import Dict, Any, List

class LossPatternFilter:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def allow_market(self, market: str, now_ts: str, state: Dict[str, Any]) -> Dict[str, Any]:
        risk = self.cfg["risk"]
        global_losses = int(state.get("consecutive_losses", 0))
        if global_losses >= risk["max_consecutive_losses"]:
            return {"allow": False, "reason": "global_consecutive_losses_limit"}
        market_stats = state.get("market_stats", {}).get(market, {})
        if int(market_stats.get("consecutive_losses", 0)) >= 2:
            return {"allow": False, "reason": "market_consecutive_losses_cooldown"}
        recent = market_stats.get("recent_pnl_pct", [])[-5:]
        if len(recent) >= 4 and sum(1 for x in recent if x < 0) >= 3:
            return {"allow": False, "reason": "recent_market_loss_cluster"}
        return {"allow": True, "reason": "loss_filter_ok"}
