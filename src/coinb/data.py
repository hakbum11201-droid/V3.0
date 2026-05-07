from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List
from .models import Candle

REQUIRED_COLUMNS = ["timestamp", "market", "open", "high", "low", "close", "volume"]

def load_candles_csv(path: str | Path) -> Dict[str, List[Candle]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    by_market: Dict[str, List[Candle]] = {}
    with p.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for col in REQUIRED_COLUMNS:
            if col not in reader.fieldnames:
                raise ValueError(f"missing csv column: {col}")
        for r in reader:
            c = Candle(
                timestamp=r["timestamp"], market=r["market"],
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]),
            )
            by_market.setdefault(c.market, []).append(c)
    for m in by_market:
        by_market[m].sort(key=lambda x: x.timestamp)
    return by_market

def save_candles_csv(path: str | Path, candles: List[Candle]) -> None:
    p=Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
        w.writeheader()
        for c in candles:
            w.writerow({k:getattr(c,k) for k in REQUIRED_COLUMNS})
