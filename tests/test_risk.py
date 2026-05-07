import unittest
from coinb.config_loader import load_config
from coinb.risk import RiskManager
from coinb.models import Signal

class TestRisk(unittest.TestCase):
    def test_approve_entry(self):
        cfg=load_config('config/config.json')
        rm=RiskManager(cfg)
        sig=Signal('KRW-BTC','ENTER_LONG',90,'test',{'close':10000,'atr':100,'atr_pct':0.01})
        d=rm.approve_entry('KRW-BTC',sig,1000000,900000,0,{})
        self.assertTrue(d['allow'])
        self.assertGreaterEqual(d['size_krw'],5000)

if __name__ == '__main__':
    unittest.main()
