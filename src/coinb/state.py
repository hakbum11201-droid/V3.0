from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


DEFAULT_STATE = {
    "total_pnl_krw": 0.0,
    "consecutive_losses": 0,
    "trade_count": 0,
    "blocked_markets": {},
}


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            state = dict(DEFAULT_STATE)
            state.update(loaded)
            return state
        except json.JSONDecodeError:
            return dict(DEFAULT_STATE)

    def save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def update_after_trade(state: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
        pnl = float(trade.get("pnl_krw", 0))
        state["total_pnl_krw"] = float(state.get("total_pnl_krw", 0)) + pnl
        state["trade_count"] = int(state.get("trade_count", 0)) + 1
        if pnl < 0:
            state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
        else:
            state["consecutive_losses"] = 0
        return state
