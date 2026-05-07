import unittest
from coinb.report import analyze_trades

class TestReport(unittest.TestCase):
    def test_report(self):
        trades=[{"market":"KRW-BTC","pnl_krw":1000,"pnl_pct":0.01},{"market":"KRW-BTC","pnl_krw":-500,"pnl_pct":-0.005}]
        r=analyze_trades(trades, 1000000)
        self.assertEqual(r["total_trades"],2)
        self.assertAlmostEqual(r["win_rate"],0.5)
        self.assertGreater(r["profit_factor"],1)

if __name__ == '__main__':
    unittest.main()
