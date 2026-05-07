from __future__ import annotations

class LiveTradingDisabled(RuntimeError):
    pass

class LiveTradingAdapter:
    """Safety placeholder. Real orders are intentionally disabled in v3.0 baseline."""
    def __init__(self, *_, **__):
        raise LiveTradingDisabled(
            "Live trading is disabled in coinB PRO v3.0 baseline. "
            "Run paper/backtest/tuner first, then add a reviewed live adapter separately."
        )
