from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from .models import Candle


def load_candles_csv(path: str) -> Dict[str, List[Candle]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"csv not found: {p}")

    by_market: Dict[str, List[Candle]] = defaultdict(list)
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"market", "timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"csv required columns: {sorted(required)}")

        for row in reader:
            candle = Candle(
                market=row["market"],
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            by_market[candle.market].append(candle)

    if not by_market:
        raise ValueError("csv has no candles")

    return dict(by_market)
