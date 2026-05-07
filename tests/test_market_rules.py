import unittest

from coinb.market_rules import is_min_order, round_price_to_tick


class TestMarketRules(unittest.TestCase):
    def test_min_order(self):
        self.assertTrue(is_min_order(5000))
        self.assertFalse(is_min_order(4999))

    def test_round_tick(self):
        self.assertEqual(round_price_to_tick(1234.56), 1235)


if __name__ == "__main__":
    unittest.main()
