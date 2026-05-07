from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_PATH = Path("config/config.json")

class ConfigError(RuntimeError):
    pass

def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    validate_config(data)
    ensure_dirs(data)
    return data

def validate_config(cfg: Dict[str, Any]) -> None:
    required = ["app", "markets", "paths", "exchange", "portfolio", "risk", "strategy", "regime"]
    for key in required:
        if key not in cfg:
            raise ConfigError(f"missing config section: {key}")
    if not cfg["markets"]:
        raise ConfigError("markets cannot be empty")
    if cfg["exchange"].get("min_order_krw", 0) < 5000:
        raise ConfigError("min_order_krw must be >= 5000")
    if cfg["portfolio"].get("initial_cash_krw", 0) <= 0:
        raise ConfigError("initial_cash_krw must be positive")

def ensure_dirs(cfg: Dict[str, Any]) -> None:
    for k in ["data_dir", "logs_dir", "reports_dir", "runtime_dir"]:
        Path(cfg["paths"][k]).mkdir(parents=True, exist_ok=True)
