from __future__ import annotations
import math

# Upbit KRW tick approximation. Always verify current exchange policy before live trading.
def krw_tick_size(price: float) -> float:
    if price >= 2_000_000: return 1000
    if price >= 1_000_000: return 500
    if price >= 500_000: return 100
    if price >= 100_000: return 50
    if price >= 10_000: return 10
    if price >= 1_000: return 1
    if price >= 100: return 0.1
    if price >= 10: return 0.01
    if price >= 1: return 0.001
    if price >= 0.1: return 0.0001
    if price >= 0.01: return 0.00001
    return 0.000001

def round_price_down(price: float) -> float:
    tick = krw_tick_size(price)
    return math.floor(price / tick) * tick

def round_price_up(price: float) -> float:
    tick = krw_tick_size(price)
    return math.ceil(price / tick) * tick

def is_min_order(amount_krw: float, min_order_krw: float = 5000) -> bool:
    return amount_krw >= min_order_krw
