from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

DEFAULT_STATE = {
    "consecutive_losses": 0,
    "daily_pnl_krw": 0.0,
    "total_pnl_krw": 0.0,
    "market_stats": {},
    "last_trade_ts": None,
}

class StateStore:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            merged=dict(DEFAULT_STATE)
            merged.update(data)
            return merged
        except Exception:
            return dict(DEFAULT_STATE)

    def save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def update_after_trade(state: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
        pnl=float(trade.get("pnl_krw",0))
        pnl_pct=float(trade.get("pnl_pct",0))
        market=trade.get("market","UNKNOWN")
        state["total_pnl_krw"] = float(state.get("total_pnl_krw",0)) + pnl
        state["daily_pnl_krw"] = float(state.get("daily_pnl_krw",0)) + pnl
        state["consecutive_losses"] = int(state.get("consecutive_losses",0)) + 1 if pnl < 0 else 0
        ms=state.setdefault("market_stats",{}).setdefault(market,{"consecutive_losses":0,"recent_pnl_pct":[]})
        ms["consecutive_losses"] = int(ms.get("consecutive_losses",0)) + 1 if pnl < 0 else 0
        recent=list(ms.get("recent_pnl_pct",[]))
        recent.append(pnl_pct)
        ms["recent_pnl_pct"] = recent[-20:]
        state["last_trade_ts"] = trade.get("timestamp")
        return state
