from __future__ import annotations
import json, time, urllib.parse, urllib.request
from typing import List, Dict, Any

class SimpleRateLimiter:
    def __init__(self, per_sec: int = 8):
        self.interval=1.0/max(per_sec,1)
        self.last=0.0
    def wait(self):
        now=time.time()
        delta=now-self.last
        if delta < self.interval:
            time.sleep(self.interval-delta)
        self.last=time.time()

class UpbitPublicClient:
    """Public quotation client. No API key required. Do not use this as a live-order client."""
    BASE="https://api.upbit.com/v1"
    def __init__(self, rate_limit_per_sec: int = 8, timeout: float = 10):
        self.rl=SimpleRateLimiter(rate_limit_per_sec)
        self.timeout=timeout
    def _get(self, path: str, params: Dict[str, Any]) -> Any:
        self.rl.wait()
        q=urllib.parse.urlencode(params)
        req=urllib.request.Request(f"{self.BASE}{path}?{q}", headers={"Accept":"application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    def candles_minutes(self, market: str, unit: int = 1, count: int = 200) -> List[Dict[str, Any]]:
        return self._get(f"/candles/minutes/{unit}", {"market":market, "count":count})
    def ticker(self, markets: List[str]) -> List[Dict[str, Any]]:
        return self._get("/ticker", {"markets": ",".join(markets)})
    def orderbook(self, markets: List[str]) -> List[Dict[str, Any]]:
        return self._get("/orderbook", {"markets": ",".join(markets)})
