from __future__ import annotations

import unittest

from coinb.report import (
    build_performance_summary,
    calc_max_consecutive_losses,
    calc_max_drawdown_krw,
    calc_market_pnl,
)


class TestReport(unittest.TestCase):
    def test_empty_trades(self) -> None:
        summary = build_performance_summary([])

        self.assertEqual(summary["total_trades"], 0)
        self.assertEqual(summary["win_rate"], 0.0)
        self.assertEqual(summary["total_pnl_krw"], 0.0)
        self.assertEqual(summary["best_market"], "")
        self.assertEqual(summary["worst_market"], "")

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
            {
                "market": "KRW-DOGE",
                "pnl_krw": -1000,
                "pnl_pct": -1.0,
            },
        ]

        summary = build_performance_summary(trades)

        self.assertEqual(summary["total_trades"], 4)
        self.assertEqual(summary["win_rate"], 0.5)
        self.assertEqual(summary["avg_win_pct"], 1.25)
        self.assertEqual(summary["avg_loss_pct"], -0.75)
        self.assertEqual(summary["profit_factor"], 1.6667)
        self.assertEqual(summary["expectancy_pct"], 0.25)
        self.assertEqual(summary["total_pnl_krw"], 1000.0)
        self.assertEqual(summary["max_drawdown_krw"], 1000.0)
        self.assertEqual(summary["best_market"], "KRW-XRP")
        self.assertEqual(summary["worst_market"], "KRW-DOGE")
        self.assertEqual(summary["consecutive_losses"], 1)

    def test_calc_market_pnl(self) -> None:
        trades = [
            {"market": "KRW-BTC", "pnl_krw": 1000},
            {"market": "KRW-BTC", "pnl_krw": -300},
            {"market": "KRW-XRP", "pnl_krw": 500},
        ]

        result = calc_market_pnl(trades)

        self.assertEqual(result["KRW-BTC"], 700.0)
        self.assertEqual(result["KRW-XRP"], 500.0)

    def test_calc_max_consecutive_losses(self) -> None:
        trades = [
            {"pnl_krw": 100},
            {"pnl_krw": -100},
            {"pnl_krw": -200},
            {"pnl_krw": 300},
            {"pnl_krw": -50},
        ]

        result = calc_max_consecutive_losses(trades)

        self.assertEqual(result, 2)

    def test_calc_max_drawdown_krw(self) -> None:
        pnl_values = [1000, -300, -500, 700, -100]

        result = calc_max_drawdown_krw(pnl_values)

        self.assertEqual(result, 800.0)


if __name__ == "__main__":
    unittest.main()