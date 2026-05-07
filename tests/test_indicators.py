from __future__ import annotations

import unittest

from coinb.indicators import atr, ema, percent_change, rolling_high, rolling_low, rsi, volume_ratio
from coinb.models import Candle


def make_candles() -> list[Candle]:
    candles: list[Candle] = []

    prices = [
        100, 101, 102, 103, 104,
        105, 106, 107, 108, 109,
        110, 111, 112, 113, 114,
        115, 116, 117, 118, 119,
        120, 121, 122, 123, 124,
    ]

    for index, price in enumerate(prices):
        candles.append(
            Candle(
                market="KRW-BTC",
                timestamp=f"2026-01-01 00:{index:02d}:00",
                open=float(price - 1),
                high=float(price + 1),
                low=float(price - 2),
                close=float(price),
                volume=float(100 + index),
            )
        )

    return candles


class TestIndicators(unittest.TestCase):
    def test_ema(self) -> None:
        values = [float(i) for i in range(1, 30)]
        result = ema(values, period=5)

        self.assertEqual(len(result), len(values))
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[4])
        self.assertIsNotNone(result[-1])

    def test_rsi(self) -> None:
        values = [float(i) for i in range(1, 30)]
        result = rsi(values, period=14)

        self.assertEqual(len(result), len(values))
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[14])
        self.assertGreaterEqual(result[-1] or 0.0, 0.0)
        self.assertLessEqual(result[-1] or 100.0, 100.0)

    def test_atr(self) -> None:
        candles = make_candles()
        result = atr(candles, period=14)

        self.assertEqual(len(result), len(candles))
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[14])
        self.assertGreater(result[-1] or 0.0, 0.0)

    def test_volume_ratio(self) -> None:
        candles = make_candles()
        result = volume_ratio(candles, period=5)

        self.assertEqual(len(result), len(candles))
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[5])
        self.assertGreater(result[-1] or 0.0, 0.0)

    def test_rolling_high_low(self) -> None:
        values = [1, 2, 3, 2, 5, 4, 6]

        highs = rolling_high(values, period=3)
        lows = rolling_low(values, period=3)

        self.assertIsNone(highs[0])
        self.assertEqual(highs[3], 3)
        self.assertEqual(highs[6], 5)

        self.assertIsNone(lows[0])
        self.assertEqual(lows[3], 1)
        self.assertEqual(lows[6], 2)

    def test_percent_change(self) -> None:
        self.assertEqual(percent_change(110, 100), 10.0)
        self.assertEqual(percent_change(90, 100), -10.0)
        self.assertEqual(percent_change(100, 0), 0.0)


if __name__ == "__main__":
    unittest.main()