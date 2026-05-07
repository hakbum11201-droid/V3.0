from __future__ import annotations

from typing import List, Optional

from .models import Candle, Signal, Position
from .indicators import ema, rsi, atr, volume_ratio, closes


class MultiFactorStrategy:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.s = cfg["strategy"]

    def signal(
        self,
        market: str,
        history: List[Candle],
        position: Optional[Position],
        regime: str,
    ) -> Signal:
        min_len = max(
            int(self.s["slow_ema"]) + 3,
            int(self.s["breakout_lookback"]) + 2,
            int(self.s["rsi_period"]) + 2,
            int(self.s["atr_period"]) + 2,
        )
        if len(history) < min_len:
            return Signal(market, "HOLD", 0, "warmup")

        values = closes(history)
        candle = history[-1]
        fast = ema(values[-int(self.s["fast_ema"]):], int(self.s["fast_ema"]))
        slow = ema(values[-int(self.s["slow_ema"]):], int(self.s["slow_ema"]))
        r = rsi(history, int(self.s["rsi_period"]))
        a = atr(history, int(self.s["atr_period"]))
        atr_pct = a / candle.close if candle.close else 0
        vr = volume_ratio(history, int(self.s["volume_lookback"]))
        lookback = int(self.s["breakout_lookback"])
        prev_high = max(c.high for c in history[-lookback-1:-1])

        indicators = {
            "fast_ema": fast,
            "slow_ema": slow,
            "rsi": r,
            "atr_pct": atr_pct,
            "volume_ratio": vr,
            "regime": regime,
            "prev_high": prev_high,
        }

        if position is not None:
            if r >= float(self.s["rsi_exit"]):
                return Signal(market, "EXIT_LONG", 4, "rsi_overheat_exit", candle.close, indicators=indicators)
            if fast < slow:
                return Signal(market, "EXIT_LONG", 3, "ema_bear_exit", candle.close, indicators=indicators)
            return Signal(market, "HOLD", 0, "position_hold", candle.close, indicators=indicators)

        if self.cfg["regime"].get("bear_block", True) and regime == "BEAR":
            return Signal(market, "HOLD", 0, "btc_bear_block", candle.close, indicators=indicators)

        score = 0
        reasons = []

        if fast > slow:
            score += 1
            reasons.append("ema_up")
        if candle.close > prev_high:
            score += 1
            reasons.append("breakout")
        if vr >= float(self.s["volume_ratio_min"]):
            score += 1
            reasons.append("volume_participation")
        if r <= float(self.s["rsi_max_entry"]):
            score += 1
            reasons.append("rsi_ok")
        if atr_pct >= float(self.s["atr_min_pct"]):
            score += 1
            reasons.append("atr_ok")
        if regime in ("BULL", "SIDE"):
            score += 1
            reasons.append(f"regime_{regime.lower()}")

        if score >= int(self.s["score_min"]):
            return Signal(
                market=market,
                action="ENTER_LONG",
                score=score,
                reason="+".join(reasons),
                entry_price=candle.close,
                stop_loss_pct=float(self.s["stop_loss_pct"]),
                take_profit_pct=float(self.s["take_profit_pct"]),
                trailing_stop_pct=float(self.s["trailing_stop_pct"]),
                indicators=indicators,
            )

        return Signal(market, "HOLD", score, "score_too_low:" + "+".join(reasons), candle.close, indicators=indicators)
