from __future__ import annotations


class LiveTradingDisabled(RuntimeError):
    """Raised when live trading is requested in a blocked version."""


def assert_live_disabled() -> None:
    raise LiveTradingDisabled(
        "실거래 주문은 현재 버전에서 차단되어 있습니다. "
        "paper/backtest/가매매 검증을 먼저 완료한 뒤 tiny_live 단계에서 별도 구현해야 합니다."
    )


def is_live_trading_allowed() -> bool:
    return False


def live_trading_status() -> dict:
    return {
        "enabled": False,
        "mode": "blocked",
        "reason": "live trading is intentionally disabled in this version",
        "allowed_modes": ["paper", "backtest", "tune", "report"],
    }