from __future__ import annotations

import unittest

from coinb.market_rules import (
    apply_slippage,
    assert_min_order,
    calc_fee_krw,
    calc_order_value_krw,
    calc_qty_from_krw,
    get_krw_tick_size,
    is_min_order_ok,
    round_price_to_tick,
)


class TestMarketRules(unittest.TestCase):
    def test_get_krw_tick_size(self) -> None:
        self.assertEqual(get_krw_tick_size(2_000_000), 1000.0)
        self.assertEqual(get_krw_tick_size(1_000_000), 500.0)
        self.assertEqual(get_krw_tick_size(500_000), 100.0)
        self.assertEqual(get_krw_tick_size(100_000), 50.0)
        self.assertEqual(get_krw_tick_size(10_000), 10.0)
        self.assertEqual(get_krw_tick_size(1_000), 1.0)
        self.assertEqual(get_krw_tick_size(100), 0.1)
        self.assertEqual(get_krw_tick_size(10), 0.01)
        self.assertEqual(get_krw_tick_size(1), 0.001)

    def test_round_price_to_tick(self) -> None:
        self.assertEqual(round_price_to_tick(15_234, "nearest"), 15_230.0)
        self.assertEqual(round_price_to_tick(15_234, "floor"), 15_230.0)
        self.assertEqual(round_price_to_tick(15_234, "ceil"), 15_240.0)

    def test_calc_fee_krw(self) -> None:
        self.assertEqual(calc_fee_krw(10_000, 0.0005), 5.0)
        self.assertEqual(calc_fee_krw(100_000, 0.0005), 50.0)

    def test_min_order(self) -> None:
        self.assertTrue(is_min_order_ok(5_000))
        self.assertTrue(is_min_order_ok(10_000))
        self.assertFalse(is_min_order_ok(4_999))

        with self.assertRaises(ValueError):
            assert_min_order(4_999)

    def test_calc_qty_from_krw(self) -> None:
        self.assertEqual(calc_qty_from_krw(10_000, 100), 100.0)
        self.assertEqual(calc_qty_from_krw(5_000, 500), 10.0)

    def test_calc_order_value_krw(self) -> None:
        self.assertEqual(calc_order_value_krw(100, 10), 1_000)
        self.assertEqual(calc_order_value_krw(500, 2), 1_000)

    def test_apply_slippage(self) -> None:
        buy_price = apply_slippage(
            price=10_000,
            slippage_pct=0.1,
            side="buy",
        )

        sell_price = apply_slippage(
            price=10_000,
            slippage_pct=0.1,
            side="sell",
        )

        self.assertEqual(buy_price, 10_010.0)
        self.assertEqual(sell_price, 9_990.0)

    def test_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            round_price_to_tick(0)

        with self.assertRaises(ValueError):
            calc_qty_from_krw(0, 100)

        with self.assertRaises(ValueError):
            calc_qty_from_krw(10_000, 0)

        with self.assertRaises(ValueError):
            apply_slippage(10_000, 0.1, "hold")


if __name__ == "__main__":
    unittest.main()