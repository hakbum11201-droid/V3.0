from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


UPBIT_API_BASE_URL = "https://api.upbit.com/v1"
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_SLEEP_SECONDS = 0.12


class UpbitPublicApiError(RuntimeError):
    """Raised when Upbit public API request fails."""


def get_json(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    url = build_url(path, params)

    request = urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": "coinB-paper-research/3.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    except Exception as exc:
        raise UpbitPublicApiError(f"Upbit public API request failed: {url}") from exc


def build_url(path: str, params: Optional[Dict[str, Any]] = None) -> str:
    clean_path = path if path.startswith("/") else f"/{path}"
    url = f"{UPBIT_API_BASE_URL}{clean_path}"

    if not params:
        return url

    query = urllib.parse.urlencode(params)
    return f"{url}?{query}"


def get_ticker(markets: List[str]) -> List[Dict[str, Any]]:
    if not markets:
        raise ValueError("markets must not be empty")

    params = {
        "markets": ",".join(markets),
    }

    data = get_json("/ticker", params=params)

    if not isinstance(data, list):
        raise UpbitPublicApiError("unexpected ticker response format")

    time.sleep(DEFAULT_SLEEP_SECONDS)

    return data


def get_market_ticker(market: str) -> Dict[str, Any]:
    tickers = get_ticker([market])

    if not tickers:
        raise UpbitPublicApiError(f"ticker not found: {market}")

    return tickers[0]


def get_minute_candles(
    market: str,
    unit: int = 1,
    count: int = 200,
    to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if unit not in [1, 3, 5, 10, 15, 30, 60, 240]:
        raise ValueError(f"unsupported minute unit: {unit}")

    if count <= 0 or count > 200:
        raise ValueError("count must be between 1 and 200")

    params: Dict[str, Any] = {
        "market": market,
        "count": count,
    }

    if to:
        params["to"] = to

    data = get_json(f"/candles/minutes/{unit}", params=params)

    if not isinstance(data, list):
        raise UpbitPublicApiError("unexpected candle response format")

    time.sleep(DEFAULT_SLEEP_SECONDS)

    return data


def normalize_upbit_candles(
    raw_candles: List[Dict[str, Any]],
    market: str,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for row in raw_candles:
        normalized.append(
            {
                "market": str(row.get("market", market)),
                "timestamp": str(row.get("candle_date_time_kst", "")),
                "open": float(row.get("opening_price", 0.0)),
                "high": float(row.get("high_price", 0.0)),
                "low": float(row.get("low_price", 0.0)),
                "close": float(row.get("trade_price", 0.0)),
                "volume": float(row.get("candle_acc_trade_volume", 0.0)),
                "trade_value_krw": float(row.get("candle_acc_trade_price", 0.0)),
            }
        )

    normalized.reverse()
    return normalized


def fetch_normalized_minute_candles(
    market: str,
    unit: int = 1,
    count: int = 200,
) -> List[Dict[str, Any]]:
    raw_candles = get_minute_candles(
        market=market,
        unit=unit,
        count=count,
    )

    return normalize_upbit_candles(raw_candles, market)


def is_krw_market(market: str) -> bool:
    return market.startswith("KRW-")


def validate_krw_market(market: str) -> None:
    if not is_krw_market(market):
        raise ValueError(f"only KRW market is allowed: {market}")