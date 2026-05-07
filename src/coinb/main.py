from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from .backtest import run_backtest
from .config_loader import load_config
from .report import run_report
from .tuner import run_tuner


def _print_json(result: Dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="coinB PRO v3.0.1",
        description="coinB PRO paper/backtest/tuner command runner",
    )

    parser.add_argument(
        "command",
        choices=[
            "validate-config",
            "backtest",
            "report",
            "tune",
            "paper-check",
        ],
        help="실행할 명령",
    )

    parser.add_argument(
        "--config",
        default="config/config.json",
        help="설정 파일 경로",
    )

    parser.add_argument(
        "--csv",
        default="data/sample_ohlcv.csv",
        help="백테스트용 OHLCV CSV 파일 경로",
    )

    args = parser.parse_args()

    if args.command == "validate-config":
        cfg = load_config(args.config)
        result = {
            "ok": True,
            "command": "validate-config",
            "app": cfg.get("app"),
            "markets": cfg.get("markets"),
            "mode": cfg.get("mode"),
        }

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
            "command": "paper-check",
            "mode": "paper_ready",
            "live_trading": "disabled",
            "markets": cfg.get("markets"),
            "message": "paper 모드 점검 완료. 실거래 주문은 차단되어 있습니다.",
        }

    else:
        raise ValueError(f"unknown command: {args.command}")

    _print_json(result)


if __name__ == "__main__":
    main()