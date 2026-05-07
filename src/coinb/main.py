from __future__ import annotations

import argparse
import json

from .config_loader import load_config
from .backtest import run_backtest
from .report import run_report
from .tuner import run_tuner


def main() -> None:
    parser = argparse.ArgumentParser(prog="coinB PRO v3.0.1")
    parser.add_argument(
        "command",
        choices=["validate-config", "backtest", "report", "tune", "paper-check"],
    )
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--csv", default="data/sample_ohlcv.csv")
    args = parser.parse_args()

    if args.command == "validate-config":
        cfg = load_config(args.config)
        result = {"ok": True, "app": cfg["app"], "markets": cfg["markets"]}
    elif args.command == "backtest":
        result = run_backtest(args.config, args.csv)
    elif args.command == "report":
        result = run_report(args.config)
    elif args.command == "tune":
        result = run_tuner(args.config, args.csv)
    elif args.command == "paper-check":
        cfg = load_config(args.config)
        result = {
            "ok": True,
            "mode": "paper_ready",
            "live_trading": "disabled",
            "markets": cfg["markets"],
        }
    else:
        raise ValueError(f"unknown command: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
