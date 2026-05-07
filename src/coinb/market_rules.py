from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Literal


RoundMode = Literal["nearest", "floor", "ceil"]


@dataclass(frozen=True)
class MarketRules:
    min_order_krw: float = 5000.0
    fee_rate: float = 0.0005


DEFAULT_RULES = MarketRules()


def get_krw_tick_size(price: float) -> float:
    if price >= 2_000_000:
        return 1000.0
    if price >= 1_000_000:
        return 500.0
    if price >= 500_000:
        return 100.0
    if price >= 100_000:
        return 50.0
    if price >= 10_000:
        return 10.0
    if price >= 1_000:
        return 1.0
    if price >= 100:
        return 0.1
    if price >= 10:
        return 0.01
    if price >= 1:
        return 0.001
    if price >= 0.1:
        return 0.0001
    if price >= 0.01:
        return 0.00001

    return 0.000001


def round_price_to_tick(price: float, mode: RoundMode = "nearest") -> float:
    if price <= 0:
        raise ValueError("price must be positive")

    tick = get_krw_tick_size(price)
    scaled = price / tick

    if mode == "nearest":
        rounded = round(scaled) * tick
    elif mode == "floor":
        rounded = floor(scaled) * tick
    elif mode == "ceil":
        rounded = floor(scaled + 0.999999999) * tick
    else:
        raise ValueError(f"unsupported round mode: {mode}")

    return round(rounded, 8)


def calc_fee_krw(amount_krw: float, fee_rate: float = DEFAULT_RULES.fee_rate) -> float:
    if amount_krw < 0:
        raise ValueError("amount_krw must be non-negative")

    return amount_krw * fee_rate


def is_min_order_ok(amount_krw: float, min_order_krw: float = DEFAULT_RULES.min_order_krw) -> bool:
    return amount_krw >= min_order_krw


def assert_min_order(amount_krw: float, min_order_krw: float = DEFAULT_RULES.min_order_krw) -> None:
    if not is_min_order_ok(amount_krw, min_order_krw):
        raise ValueError(
            f"order amount too small: {amount_krw:.0f} KRW < {min_order_krw:.0f} KRW"
        )


def calc_qty_from_krw(amount_krw: float, price: float) -> float:
    if amount_krw <= 0:
        raise ValueError("amount_krw must be positive")

    if price <= 0:
        raise ValueError("price must be positive")

    return amount_krw / price


def calc_order_value_krw(price: float, qty: float) -> float:
    if price <= 0:
        raise ValueError("price must be positive")

    if qty < 0:
        raise ValueError("qty must be non-negative")

    return price * qty


def apply_slippage(price: float, slippage_pct: float, side: str) -> float:
    if price <= 0:
        raise ValueError("price must be positive")

    if slippage_pct < 0:
        raise ValueError("slippage_pct must be non-negative")

    rate = slippage_pct / 100.0

    if side == "buy":
        slipped_price = price * (1.0 + rate)
    elif side == "sell":
        slipped_price = price * (1.0 - rate)
    else:
        raise ValueError(f"unsupported side: {side}")

    return round_price_to_tick(slipped_price, mode="nearest")