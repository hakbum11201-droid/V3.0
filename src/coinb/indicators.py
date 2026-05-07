from __future__ import annotations
from typing import List, Optional

def sma(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i-period]
        out.append(s / period if i >= period-1 else None)
    return out

def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    if not values:
        return out
    k = 2 / (period + 1)
    e = values[0]
    for i, v in enumerate(values):
        e = v if i == 0 else v * k + e * (1-k)
        out.append(e if i >= period-1 else None)
    return out

def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    if len(values) < 2:
        return [None] * len(values)
    out: List[Optional[float]] = [None]
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i-1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
        if i < period:
            out.append(None)
        elif i == period:
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            rs = avg_gain / avg_loss if avg_loss else 999999
            out.append(100 - (100 / (1 + rs)))
        else:
            prev = out[-1]
            # Reconstruct smoothed values approximately using recent window for simplicity/stability.
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            rs = avg_gain / avg_loss if avg_loss else 999999
            out.append(100 - (100 / (1 + rs)))
    return out

def atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> List[Optional[float]]:
    trs: List[float] = []
    for i in range(len(close)):
        if i == 0:
            tr = high[i] - low[i]
        else:
            tr = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        trs.append(tr)
    return ema(trs, period)

def rolling_high(values: List[float], period: int) -> List[Optional[float]]:
    out=[]
    for i in range(len(values)):
        if i < period:
            out.append(None)
        else:
            out.append(max(values[i-period:i]))
    return out

def rolling_low(values: List[float], period: int) -> List[Optional[float]]:
    out=[]
    for i in range(len(values)):
        if i < period:
            out.append(None)
        else:
            out.append(min(values[i-period:i]))
    return out
