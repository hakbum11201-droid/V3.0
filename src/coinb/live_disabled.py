from __future__ import annotations


class LiveTradingDisabled(RuntimeError):
    pass


def assert_live_disabled() -> None:
    raise LiveTradingDisabled(
        "실거래 주문은 v3.0.1에서 차단되어 있습니다. v4 tiny_live 단계에서 별도 구현해야 합니다."
    )
