import unittest

from coinb.config_loader import load_config


class TestConfig(unittest.TestCase):
    def test_load_config(self):
        cfg = load_config("config/config.json")
        self.assertEqual(cfg["app"]["name"], "coinB PRO")
        self.assertFalse(cfg["live"]["enabled"])


if __name__ == "__main__":
    unittest.main()
