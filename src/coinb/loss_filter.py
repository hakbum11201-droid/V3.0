from __future__ import annotations

from typing import Dict, Any


class LossPatternFilter:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def allow_market(self, market: str, timestamp: str, state: dict) -> Dict[str, Any]:
        blocked = state.get("blocked_markets", {})
        if market in blocked:
            return {"allow": False, "reason": "market_blocked_by_loss_filter"}

        return {"allow": True, "reason": "ok"}
