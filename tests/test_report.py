import unittest

from coinb.report import analyze_trades


class TestReport(unittest.TestCase):
    def test_analyze_trades(self):
        trades = [
            {"market": "KRW-XRP", "pnl_krw": 1000, "pnl_pct": 0.01},
            {"market": "KRW-XRP", "pnl_krw": -500, "pnl_pct": -0.005},
        ]
        report = analyze_trades(trades, 1000000)
        self.assertEqual(report["total_trades"], 2)
        self.assertAlmostEqual(report["win_rate"], 0.5)
        self.assertEqual(report["total_pnl_krw"], 500)


if __name__ == "__main__":
    unittest.main()
