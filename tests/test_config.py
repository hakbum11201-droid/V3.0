from __future__ import annotations

import unittest

from coinb.config_loader import load_config


class TestConfig(unittest.TestCase):
    def test_config_loads(self) -> None:
        config = load_config("config/config.json")

        self.assertIsInstance(config, dict)
        self.assertIn("app", config)
        self.assertIn("markets", config)
        self.assertIn("paths", config)
        self.assertIn("portfolio", config)
        self.assertIn("risk", config)
        self.assertIn("strategy", config)
        self.assertIn("regime", config)
        self.assertIn("live", config)

    def test_live_trading_is_disabled(self) -> None:
        config = load_config("config/config.json")

        live_config = config.get("live", {})
        self.assertFalse(live_config.get("enabled", False))

    def test_markets_are_krw_markets(self) -> None:
        config = load_config("config/config.json")
        markets = config.get("markets", [])

        self.assertGreater(len(markets), 0)

        for market in markets:
            self.assertTrue(
                str(market).startswith("KRW-"),
                msg=f"Only Upbit KRW markets are allowed: {market}",
            )


if __name__ == "__main__":
    unittest.main()