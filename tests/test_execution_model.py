from __future__ import annotations

import unittest

from coinb.execution_model import simulate_virtual_buy_fill, simulate_virtual_sell_fill


def make_features() -> dict:
    return {
        "market": "KRW-XRP",
        "last_trade_price": 1000.0,
        "best_bid": 999.0,
        "best_ask": 1000.0,
        "ask_depth_5_krw": 5_000_000.0,
        "bid_depth_5_krw": 5_000_000.0,
    }


class TestExecutionModel(unittest.TestCase):
    def test_virtual_buy_fill_ok(self) -> None:
        fill = simulate_virtual_buy_fill(
            market="KRW-XRP",
            features=make_features(),
            requested_krw=100_000,
            fee_rate=0.0005,
            min_order_krw=5_000,
            max_depth_take_ratio=0.10,
            min_liquidity_multiple=3.0,
            extra_slippage_pct=0.03,
        )

        self.assertTrue(fill.ok)
        self.assertEqual(fill.side, "VIRTUAL_BUY")
        self.assertGreater(fill.qty, 0)
        self.assertGreater(fill.fee_krw, 0)

    def test_virtual_buy_blocked_by_thin_depth(self) -> None:
        features = make_features()
        features["ask_depth_5_krw"] = 100_000.0

        fill = simulate_virtual_buy_fill(
            market="KRW-XRP",
            features=features,
            requested_krw=100_000,
            fee_rate=0.0005,
            min_order_krw=5_000,
            max_depth_take_ratio=0.10,
            min_liquidity_multiple=3.0,
            extra_slippage_pct=0.03,
        )

        self.assertFalse(fill.ok)
        self.assertEqual(fill.reason, "ask_depth_too_thin")

    def test_virtual_sell_fill_ok(self) -> None:
        fill = simulate_virtual_sell_fill(
            market="KRW-XRP",
            features=make_features(),
            qty=100.0,
            entry_price=1000.0,
            fee_rate=0.0005,
            max_depth_take_ratio=0.10,
            min_liquidity_multiple=3.0,
            extra_slippage_pct=0.03,
            allow_forced_exit_on_low_liquidity=True,
        )

        self.assertTrue(fill.ok)
        self.assertEqual(fill.side, "VIRTUAL_SELL")
        self.assertGreater(fill.filled_krw, 0)
        self.assertGreater(fill.fee_krw, 0)

    def test_virtual_sell_forced_low_liquidity(self) -> None:
        features = make_features()
        features["bid_depth_5_krw"] = 10_000.0

        fill = simulate_virtual_sell_fill(
            market="KRW-XRP",
            features=features,
            qty=100.0,
            entry_price=1000.0,
            fee_rate=0.0005,
            max_depth_take_ratio=0.10,
            min_liquidity_multiple=3.0,
            extra_slippage_pct=0.03,
            allow_forced_exit_on_low_liquidity=True,
        )

        self.assertTrue(fill.ok)
        self.assertEqual(fill.reason, "forced_exit_low_liquidity")


if __name__ == "__main__":
    unittest.main()