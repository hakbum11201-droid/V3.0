from __future__ import annotations

from typing import List, Optional

from .models import Candle


NumberList = List[Optional[float]]


def ema(values: List[float], period: int) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(values)

    if not values:
        return result

    multiplier = 2.0 / (period + 1.0)
    current_ema: Optional[float] = None

    for index, value in enumerate(values):
        if current_ema is None:
            current_ema = value
        else:
            current_ema = (value - current_ema) * multiplier + current_ema

        if index >= period - 1:
            result[index] = current_ema

    return result


def rsi(values: List[float], period: int = 14) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(values)

    if len(values) <= period:
        return result

    gains: List[float] = []
    losses: List[float] = []

    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    result[period] = _rsi_from_average(avg_gain, avg_loss)

    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = abs(min(change, 0.0))

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        result[index] = _rsi_from_average(avg_gain, avg_loss)

    return result


def _rsi_from_average(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(candles: List[Candle], period: int = 14) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(candles)

    if len(candles) <= period:
        return result

    true_ranges: List[float] = []

    for index, candle in enumerate(candles):
        if index == 0:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )

        true_ranges.append(true_range)

    current_atr = sum(true_ranges[1 : period + 1]) / period
    result[period] = current_atr

    for index in range(period + 1, len(candles)):
        current_atr = ((current_atr * (period - 1)) + true_ranges[index]) / period
        result[index] = current_atr

    return result


def volume_ratio(candles: List[Candle], period: int = 20) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(candles)

    for index in range(len(candles)):
        if index < period:
            continue

        previous_volumes = [c.volume for c in candles[index - period : index]]
        average_volume = sum(previous_volumes) / period

        if average_volume <= 0:
            result[index] = None
        else:
            result[index] = candles[index].volume / average_volume

    return result


def rolling_high(values: List[float], period: int) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(values)

    for index in range(len(values)):
        if index < period:
            continue

        result[index] = max(values[index - period : index])

    return result


def rolling_low(values: List[float], period: int) -> NumberList:
    if period <= 0:
        raise ValueError("period must be positive")

    result: NumberList = [None] * len(values)

    for index in range(len(values)):
        if index < period:
            continue

        result[index] = min(values[index - period : index])

    return result


def percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0

    return ((current - previous) / previous) * 100.0