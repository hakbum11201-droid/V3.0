from __future__ import annotations
from typing import List, Dict, Any
from .models import Candle
from .indicators import ema

class RegimeFilter:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def classify(self, btc_history: List[Candle]) -> Dict[str, Any]:
        if len(btc_history) < max(self.cfg["ema_slow"], 80):
            return {"regime":"unknown", "allow_new_entry":False, "reason":"insufficient_btc_history"}
        close=[c.close for c in btc_history]
        ef=ema(close, self.cfg["ema_fast"])[-1]
        es=ema(close, self.cfg["ema_slow"])[-1]
        recent_return=(close[-1]/close[-24]-1) if len(close)>24 else 0.0
        slope=(close[-1]/close[-5]-1)/5 if len(close)>5 else 0.0
        if recent_return <= self.cfg["risk_off_drawdown_pct"] or (ef is not None and es is not None and ef < es and slope < 0):
            return {"regime":"risk_off", "allow_new_entry":False, "reason":"btc_downtrend_or_drawdown", "recent_return":recent_return, "slope":slope}
        if ef and es and ef > es and slope >= self.cfg["risk_on_slope_min"]:
            return {"regime":"risk_on", "allow_new_entry":True, "reason":"btc_trend_positive", "recent_return":recent_return, "slope":slope}
        return {"regime":"neutral", "allow_new_entry":True, "reason":"btc_neutral", "recent_return":recent_return, "slope":slope}
