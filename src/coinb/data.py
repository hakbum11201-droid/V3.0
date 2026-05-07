from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .models import Candle


def load_candles_from_csv(path: str, default_market: str = "KRW-BTC") -> List[Candle]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    candles: List[Candle] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")

        for row in reader:
            normalized = _normalize_row(row, default_market)
            candles.append(
                Candle(
                    market=normalized["market"],
                    timestamp=normalized["timestamp"],
                    open=float(normalized["open"]),
                    high=float(normalized["high"]),
                    low=float(normalized["low"]),
                    close=float(normalized["close"]),
                    volume=float(normalized["volume"]),
                )
            )

    if not candles:
        raise ValueError(f"CSV has no candle rows: {csv_path}")

    return candles


def _normalize_row(row: Dict[str, str], default_market: str) -> Dict[str, str]:
    return {
        "market": _get_value(row, ["market", "symbol"], default_market),
        "timestamp": _get_value(row, ["timestamp", "time", "date", "datetime"], ""),
        "open": _get_value(row, ["open", "opening_price"], "0"),
        "high": _get_value(row, ["high", "high_price"], "0"),
        "low": _get_value(row, ["low", "low_price"], "0"),
        "close": _get_value(row, ["close", "trade_price", "price"], "0"),
        "volume": _get_value(row, ["volume", "candle_acc_trade_volume"], "0"),
    }


def _get_value(row: Dict[str, str], keys: List[str], default: str) -> str:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return str(row[key]).strip()

    return default


def split_candles_by_market(candles: List[Candle]) -> Dict[str, List[Candle]]:
    grouped: Dict[str, List[Candle]] = {}

    for candle in candles:
        grouped.setdefault(candle.market, []).append(candle)

    return grouped


def last_close(candles: List[Candle]) -> float:
    if not candles:
        raise ValueError("candles is empty")

    return candles[-1].close