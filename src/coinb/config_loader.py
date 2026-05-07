from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REQUIRED_TOP_KEYS = [
    "app",
    "markets",
    "paths",
    "portfolio",
    "risk",
    "strategy",
    "regime",
    "live",
]


def load_config(path: str = "config/config.json") -> Dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    missing_keys = [key for key in REQUIRED_TOP_KEYS if key not in config]
    if missing_keys:
        raise ValueError(f"config missing required keys: {missing_keys}")

    live_config = config.get("live", {})
    if live_config.get("enabled") is True:
        raise RuntimeError(
            "live trading is blocked in this version. Use paper/backtest only."
        )

    return config