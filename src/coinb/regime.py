from __future__ import annotations

from typing import List

from .models import Candle
from .indicators import ema, closes


class RegimeFilter:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def classify(self, btc_history: List[Candle]) -> str:
        period = int(self.cfg.get("ema_period", 21))
        if len(btc_history) < period + 3:
            return "WARMUP"

        values = closes(btc_history)
        now_ema = ema(values[-period:], period)
        prev_ema = ema(values[-period-3:-3], period)
        close = values[-1]

        if close > now_ema and now_ema >= prev_ema:
            return "BULL"
        if close < now_ema and now_ema < prev_ema:
            return "BEAR"
        return "SIDE"
