from __future__ import annotations

__app_name__ = "coinB PRO"
__version__ = "3.0.1"
__exchange__ = "upbit"
__market_type__ = "KRW"
__default_mode__ = "paper"


def get_version_info() -> dict:
    return {
        "app_name": __app_name__,
        "version": __version__,
        "exchange": __exchange__,
        "market_type": __market_type__,
        "default_mode": __default_mode__,
        "live_trading": "disabled",
    }