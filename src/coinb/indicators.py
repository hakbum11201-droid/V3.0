from __future__ import annotations

from typing import List

from .models import Candle


def closes(candles: List[Candle]) -> List[float]:
    return [c.close for c in candles]


def ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    period = max(1, period)
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def sma(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    chunk = values[-period:] if len(values) >= period else values
    return sum(chunk) / len(chunk)


def rsi(candles: List[Candle], period: int = 14) -> float:
    values = closes(candles)
    if len(values) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles: List[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0

    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        tr = max(
            c.high - c.low,
            abs(c.high - prev.close),
            abs(c.low - prev.close),
        )
        trs.append(tr)

    chunk = trs[-period:] if len(trs) >= period else trs
    return sum(chunk) / len(chunk) if chunk else 0.0


def volume_ratio(candles: List[Candle], period: int = 12) -> float:
    if len(candles) < period + 1:
        return 1.0
    prev = [c.volume for c in candles[-period-1:-1]]
    avg = sum(prev) / len(prev)
    if avg <= 0:
        return 1.0
    return candles[-1].volume / avg
