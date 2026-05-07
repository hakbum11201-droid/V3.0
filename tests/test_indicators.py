import unittest
from coinb.indicators import ema, rsi, atr

class TestIndicators(unittest.TestCase):
    def test_ema_length(self):
        vals=list(range(1,50))
        self.assertEqual(len(ema(vals, 10)), len(vals))
        self.assertIsNotNone(ema(vals, 10)[-1])
    def test_rsi(self):
        vals=[1,2,3,4,5,6,5,4,5,6,7,8,9,10,11,12,13]
        self.assertEqual(len(rsi(vals,14)), len(vals))
    def test_atr(self):
        h=[3,4,5,6,7,8,9,10,11,12,13,14,15,16,17]
        l=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]
        c=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
        self.assertIsNotNone(atr(h,l,c,5)[-1])

if __name__ == '__main__':
    unittest.main()
