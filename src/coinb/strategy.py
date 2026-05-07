from __future__ import annotations

from typing import Any, Dict, List, Optional

from .indicators import atr, ema, rolling_high, rsi, volume_ratio
from .models import Candle, Signal


def generate_signal(
    candles: List[Candle],
    index: int,
    config: Dict[str, Any],
) -> Signal:
    if not candles:
        raise ValueError("candles is empty")

    if index < 0 or index >= len(candles):
        raise IndexError(f"index out of range: {index}")

    candle = candles[index]
    strategy_config = config.get("strategy", {})

    ema_fast_period = int(strategy_config.get("ema_fast_period", 9))
    ema_slow_period = int(strategy_config.get("ema_slow_period", 21))
    rsi_period = int(strategy_config.get("rsi_period", 14))
    atr_period = int(strategy_config.get("atr_period", 14))
    volume_period = int(strategy_config.get("volume_period", 20))
    breakout_period = int(strategy_config.get("breakout_period", 20))

    rsi_max = float(strategy_config.get("rsi_max", 72.0))
    atr_min_pct = float(strategy_config.get("atr_min_pct", 0.15))
    volume_ratio_min = float(strategy_config.get("volume_ratio_min", 1.2))
    min_score = float(strategy_config.get("min_score", 3.0))

    stop_loss_pct = float(strategy_config.get("stop_loss_pct", 0.8))
    take_profit_pct = float(strategy_config.get("take_profit_pct", 1.4))
    trailing_stop_pct = float(strategy_config.get("trailing_stop_pct", 0.7))

    closes = [c.close for c in candles]

    ema_fast_values = ema(closes, ema_fast_period)
    ema_slow_values = ema(closes, ema_slow_period)
    rsi_values = rsi(closes, rsi_period)
    atr_values = atr(candles, atr_period)
    volume_ratio_values = volume_ratio(candles, volume_period)
    breakout_high_values = rolling_high(closes, breakout_period)

    ema_fast = ema_fast_values[index]
    ema_slow = ema_slow_values[index]
    rsi_value = rsi_values[index]
    atr_value = atr_values[index]
    volume_ratio_value = volume_ratio_values[index]
    breakout_high = breakout_high_values[index]

    indicators = {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi": rsi_value,
        "atr": atr_value,
        "volume_ratio": volume_ratio_value,
        "breakout_high": breakout_high,
    }

    if _has_missing_values(
        [
            ema_fast,
            ema_slow,
            rsi_value,
            atr_value,
            volume_ratio_value,
            breakout_high,
        ]
    ):
        return Signal(
            market=candle.market,
            action="HOLD",
            score=0.0,
            reason="insufficient_indicator_data",
            entry_price=candle.close,
            indicators=indicators,
        )

    score = 0.0
    reasons: List[str] = []

    if ema_fast is not None and ema_slow is not None and ema_fast > ema_slow:
        score += 1.0
        reasons.append("ema_uptrend")
    else:
        reasons.append("ema_not_uptrend")

    if rsi_value is not None and rsi_value < rsi_max:
        score += 1.0
        reasons.append("rsi_not_overheated")
    else:
        reasons.append("rsi_overheated")

    if atr_value is not None and candle.close > 0:
        atr_pct = (atr_value / candle.close) * 100.0
        indicators["atr_pct"] = atr_pct

        if atr_pct >= atr_min_pct:
            score += 1.0
            reasons.append("atr_enough")
        else:
            reasons.append("atr_too_low")
    else:
        reasons.append("atr_missing")

    if volume_ratio_value is not None and volume_ratio_value >= volume_ratio_min:
        score += 1.0
        reasons.append("volume_participation")
    else:
        reasons.append("volume_weak")

    if breakout_high is not None and candle.close > breakout_high:
        score += 1.0
        reasons.append("breakout")
    else:
        reasons.append("no_breakout")

    action = "BUY" if score >= min_score else "HOLD"

    return Signal(
        market=candle.market,
        action=action,
        score=score,
        reason=",".join(reasons),
        entry_price=candle.close,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        trailing_stop_pct=trailing_stop_pct,
        indicators=indicators,
    )


def generate_signals(
    candles: List[Candle],
    config: Dict[str, Any],
) -> List[Signal]:
    return [
        generate_signal(candles=candles, index=index, config=config)
        for index in range(len(candles))
    ]


def _has_missing_values(values: List[Optional[float]]) -> bool:
    return any(value is None for value in values)