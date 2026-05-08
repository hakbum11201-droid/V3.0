from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .indicators import ema, percent_change
from .models import Candle


@dataclass
class RegimeDecision:
    ok: bool
    regime: str
    reason: str
    btc_change_pct: float
    ema_fast: float
    ema_slow: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def check_market_regime(
    btc_candles: List[Candle],
    config: Dict[str, Any],
    index: int | None = None,
) -> RegimeDecision:
    regime_config = config.get("regime", {})

    enabled = bool(regime_config.get("enabled", True))
    if not enabled:
        return RegimeDecision(
            ok=True,
            regime="disabled",
            reason="regime_filter_disabled",
            btc_change_pct=0.0,
            ema_fast=0.0,
            ema_slow=0.0,
        )

    if not btc_candles:
        return RegimeDecision(
            ok=False,
            regime="unknown",
            reason="btc_candles_empty",
            btc_change_pct=0.0,
            ema_fast=0.0,
            ema_slow=0.0,
        )

    if index is None:
        index = len(btc_candles) - 1

    if index < 0 or index >= len(btc_candles):
        return RegimeDecision(
            ok=False,
            regime="unknown",
            reason="btc_index_out_of_range",
            btc_change_pct=0.0,
            ema_fast=0.0,
            ema_slow=0.0,
        )

    ema_fast_period = int(regime_config.get("btc_ema_fast_period", 12))
    ema_slow_period = int(regime_config.get("btc_ema_slow_period", 36))
    lookback = int(regime_config.get("btc_change_lookback", 12))
    min_change_pct = float(regime_config.get("btc_min_change_pct", -2.0))

    closes = [c.close for c in btc_candles]
    ema_fast_values = ema(closes, ema_fast_period)
    ema_slow_values = ema(closes, ema_slow_period)

    ema_fast_value = ema_fast_values[index]
    ema_slow_value = ema_slow_values[index]

    if ema_fast_value is None or ema_slow_value is None:
        return RegimeDecision(
            ok=False,
            regime="unknown",
            reason="insufficient_btc_ema_data",
            btc_change_pct=0.0,
            ema_fast=0.0,
            ema_slow=0.0,
        )

    base_index = max(0, index - lookback)
    btc_change_pct = percent_change(
        current=btc_candles[index].close,
        previous=btc_candles[base_index].close,
    )

    if btc_change_pct <= min_change_pct:
        return RegimeDecision(
            ok=False,
            regime="risk_off",
            reason="btc_change_too_weak",
            btc_change_pct=btc_change_pct,
            ema_fast=ema_fast_value,
            ema_slow=ema_slow_value,
        )

    if ema_fast_value < ema_slow_value:
        return RegimeDecision(
            ok=False,
            regime="risk_off",
            reason="btc_ema_downtrend",
            btc_change_pct=btc_change_pct,
            ema_fast=ema_fast_value,
            ema_slow=ema_slow_value,
        )

    return RegimeDecision(
        ok=True,
        regime="risk_on",
        reason="btc_regime_ok",
        btc_change_pct=btc_change_pct,
        ema_fast=ema_fast_value,
        ema_slow=ema_slow_value,
    )