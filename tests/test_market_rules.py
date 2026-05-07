import unittest
from coinb.market_rules import krw_tick_size, round_price_down, is_min_order

class TestMarketRules(unittest.TestCase):
    def test_tick(self):
        self.assertEqual(krw_tick_size(2000000), 1000)
        self.assertEqual(krw_tick_size(15000), 10)
        self.assertEqual(krw_tick_size(500), 0.1)
    def test_round(self):
        self.assertEqual(round_price_down(12345), 12340)
    def test_min_order(self):
        self.assertFalse(is_min_order(4999))
        self.assertTrue(is_min_order(5000))

if __name__ == '__main__':
    unittest.main()
