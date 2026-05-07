from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REQUIRED_TOP_KEYS = ["app", "markets", "paths", "portfolio", "risk", "strategy", "regime", "live"]


def load_config(path: str = "config/config.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")

    cfg = json.loads(p.read_text(encoding="utf-8"))

    missing = [k for k in REQUIRED_TOP_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"config missing required keys: {missing}")

    if cfg["live"].get("enabled") is True:
        raise RuntimeError("live trading is blocked in v3.0.1. Use paper/backtest only.")

    return cfg
