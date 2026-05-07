from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coinb.config_loader import load_config
from coinb.jsonl import append_jsonl, read_jsonl, write_json, read_json
from coinb.market_rules import (
    calc_fee_krw,
    calc_qty_from_krw,
    get_krw_tick_size,
    is_min_order_ok,
    round_price_to_tick,
)
from coinb.report import build_performance_summary


class TestConfigLoader(unittest.TestCase):
    def test_load_config(self) -> None:
        config = load_config("config/config.json")

        self.assertIn("app", config)
        self.assertIn("markets", config)
        self.assertIn("risk", config)
        self.assertIn("strategy", config)
        self.assertFalse(config.get("live", {}).get("enabled", False))


class TestMarketRules(unittest.TestCase):
    def test_tick_size(self) -> None:
        self.assertEqual(get_krw_tick_size(2_100_000), 1000.0)
        self.assertEqual(get_krw_tick_size(1_100_000), 500.0)
        self.assertEqual(get_krw_tick_size(600_000), 100.0)
        self.assertEqual(get_krw_tick_size(150_000), 50.0)
        self.assertEqual(get_krw_tick_size(15_000), 10.0)
        self.assertEqual(get_krw_tick_size(1_500), 1.0)

    def test_round_price_to_tick(self) -> None:
        self.assertEqual(round_price_to_tick(15_234, "nearest"), 15_230.0)
        self.assertEqual(round_price_to_tick(15_234, "floor"), 15_230.0)
        self.assertEqual(round_price_to_tick(15_234, "ceil"), 15_240.0)

    def test_fee_and_qty(self) -> None:
        self.assertEqual(calc_fee_krw(10_000, 0.0005), 5.0)
        self.assertTrue(is_min_order_ok(5_000))
        self.assertFalse(is_min_order_ok(4_999))
        self.assertEqual(calc_qty_from_krw(10_000, 100), 100.0)


class TestJsonl(unittest.TestCase):
    def test_json_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            json_path = base / "state.json"
            jsonl_path = base / "events.jsonl"

            write_json(json_path, {"ok": True})
            self.assertEqual(read_json(json_path), {"ok": True})

            append_jsonl(jsonl_path, {"a": 1})
            append_jsonl(jsonl_path, {"b": 2})

            rows = read_jsonl(jsonl_path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["a"], 1)
            self.assertEqual(rows[1]["b"], 2)


class TestReport(unittest.TestCase):
    def test_performance_summary(self) -> None:
        trades = [
            {
                "market": "KRW-BTC",
                "pnl_krw": 1000,
                "pnl_pct": 1.0,
            },
            {
                "market": "KRW-BTC",
                "pnl_krw": -500,
                "pnl_pct": -0.5,
            },
            {
                "market": "KRW-XRP",
                "pnl_krw": 1500,
                "pnl_pct": 1.5,
            },
        ]

        summary = build_performance_summary(trades)

        self.assertEqual(summary["total_trades"], 3)
        self.assertEqual(summary["win_rate"], 0.6667)
        self.assertEqual(summary["total_pnl_krw"], 2000.0)
        self.assertEqual(summary["best_market"], "KRW-XRP")
        self.assertEqual(summary["worst_market"], "KRW-BTC")


if __name__ == "__main__":
    unittest.main()