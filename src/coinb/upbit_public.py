from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List


UPBIT_QUOTATION_BASE = "https://api.upbit.com/v1"


def fetch_ticker(markets: List[str], timeout: float = 5.0) -> List[Dict[str, Any]]:
    query = ",".join(markets)
    url = f"{UPBIT_QUOTATION_BASE}/ticker?markets={query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
