from __future__ import annotations
from typing import Dict, List, Any, Optional
from .models import Candle, Signal, Position
from .indicators import ema, rsi, atr, sma, rolling_high

class MultiFactorStrategy:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.s = cfg["strategy"]
        self.risk = cfg["risk"]

    def signal(self, market: str, history: List[Candle], position: Optional[Position], regime: Dict[str, Any]) -> Signal:
        if len(history) < max(self.s["ema_slow"], self.s["breakout_lookback"], self.s["volume_lookback"], 80):
            return Signal(market, "HOLD", 0, "insufficient_history")
        closes=[c.close for c in history]
        highs=[c.high for c in history]
        lows=[c.low for c in history]
        vols=[c.volume for c in history]
        close=closes[-1]
        efast=ema(closes, self.s["ema_fast"])[-1]
        eslow=ema(closes, self.s["ema_slow"])[-1]
        rv=rsi(closes, self.s["rsi_period"])[-1]
        av=atr(highs,lows,closes,self.s["atr_period"])[-1]
        rh=rolling_high(highs,self.s["breakout_lookback"])[-1]
        vavg=sma(vols,self.s["volume_lookback"])[-1]
        if any(x is None for x in [efast, eslow, rv, av, rh, vavg]):
            return Signal(market, "HOLD", 0, "indicator_not_ready")
        atr_pct = av / close if close else 0
        if position:
            # Exit signal is mainly managed by broker stops; this handles stale holding and trend failure.
            if position.bars_held >= self.s["max_holding_bars"]:
                return Signal(market, "EXIT", 100, "max_holding_bars", {"close":close})
            if efast < eslow and rv < 45:
                return Signal(market, "EXIT", 80, "trend_failed", {"close":close})
            return Signal(market, "HOLD", 50, "position_hold", {"close":close})
        if not regime.get("allow_new_entry", False):
            return Signal(market, "HOLD", 0, "regime_block:" + regime.get("reason", "unknown"))
        reasons=[]
        score=0.0
        if efast > eslow:
            score += 25; reasons.append("ema_trend_up")
        else:
            reasons.append("ema_trend_down")
        if close > rh:
            score += 25; reasons.append("breakout")
        else:
            reasons.append("no_breakout")
        if vols[-1] > vavg * self.s["volume_mult"]:
            score += 20; reasons.append("volume_participation")
        else:
            reasons.append("weak_volume")
        if self.s["rsi_min"] <= rv <= self.s["rsi_max"]:
            score += 15; reasons.append("rsi_ok")
        else:
            reasons.append("rsi_block")
        if self.risk["min_atr_pct"] <= atr_pct <= self.risk["max_atr_pct"]:
            score += 15; reasons.append("atr_ok")
        else:
            reasons.append("atr_block")
        if regime.get("regime") == "risk_on":
            score += 5; reasons.append("regime_bonus")
        action = "ENTER_LONG" if score >= self.s["entry_score_threshold"] else "HOLD"
        return Signal(market, action, min(score,100), ",".join(reasons), {"close":close, "atr":av, "atr_pct":atr_pct, "rsi":rv, "ema_fast":efast, "ema_slow":eslow})
