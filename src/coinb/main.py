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
        description="coinB PRO paper/backtest/tuner/orderflow command runner",
    )

    parser.add_argument(
        "command",
        choices=[
            "validate-config",
            "backtest",
            "report",
            "tune",
            "paper-check",
            "collect-ws",
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

    parser.add_argument(
        "--seconds",
        type=int,
        default=30,
        help="WebSocket 수집 시간(초)",
    )

    parser.add_argument(
        "--output",
        default="logs/upbit_ws_events.jsonl",
        help="WebSocket 수집 로그 저장 경로",
    )

    args = parser.parse_args()

    if args.command == "validate-config":
        cfg = load_config(args.config)
        app_config = cfg.get("app", {})
        live_config = cfg.get("live", {})

        result = {
            "ok": True,
            "command": "validate-config",
            "app": app_config,
            "markets": cfg.get("markets"),
            "mode": app_config.get("default_mode", "paper"),
            "live": live_config,
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
            "exchange": "upbit",
            "market_type": "KRW",
            "mode": "paper_ready",
            "live_trading": "disabled",
            "markets": cfg.get("markets"),
            "message": "paper 모드 점검 완료. 실거래 주문은 차단되어 있습니다.",
        }

    elif args.command == "collect-ws":
        cfg = load_config(args.config)
        markets = cfg.get("markets", [])

        from .upbit_ws import collect_upbit_ws_events

        result = collect_upbit_ws_events(
            markets=markets,
            output_path=args.output,
            seconds=args.seconds,
            include_trade=True,
            include_orderbook=True,
        )

    else:
        raise ValueError(f"unknown command: {args.command}")

    _print_json(result)


if __name__ == "__main__":
    main()