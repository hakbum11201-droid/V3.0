from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from .backtest import run_backtest
from .config_loader import load_config
from .report import run_report
from .tuner import run_tuner


def _print_json(result: Dict[str, Any]) -> None:
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
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
            "microstructure",
            "orderflow-paper",
            "learning-log",
            "loss-analysis",
            "paper-review",
            "paper-config-candidates",
            "ddm-status",
            "paper-performance",
            "rejection-diagnostics",
            "build-config-experiments",
            "volume-threshold-diagnostics",
            "opportunity-diagnostics",
            "orderflow-score-diagnostics",
            "score-component-diagnostics",
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

    parser.add_argument(
        "--micro-input",
        default="logs/upbit_ws_events.jsonl",
        help="Microstructure 계산용 입력 로그 경로",
    )

    parser.add_argument(
        "--micro-output",
        default="reports/microstructure_snapshot.json",
        help="Microstructure 계산 결과 저장 경로",
    )

    parser.add_argument(
        "--paper-state",
        default="runtime/orderflow_paper_state.json",
        help="Orderflow paper 상태 저장 경로",
    )

    parser.add_argument(
        "--paper-decisions",
        default="logs/orderflow_paper_decisions.jsonl",
        help="Orderflow paper 판단 로그 경로",
    )

    parser.add_argument(
        "--paper-trades",
        default="logs/orderflow_paper_trades.jsonl",
        help="Orderflow paper 거래 로그 경로",
    )

    parser.add_argument(
        "--learning-output",
        default="logs/orderflow_learning_dataset.jsonl",
        help="학습 데이터셋 저장 경로",
    )

    parser.add_argument(
        "--learning-summary",
        default="reports/orderflow_learning_summary.json",
        help="학습 데이터 요약 리포트 저장 경로",
    )

    parser.add_argument(
        "--loss-output",
        default="reports/orderflow_loss_analysis.json",
        help="손실 패턴 분석 리포트 저장 경로",
    )

    parser.add_argument(
        "--review-output",
        default="reports/paper_review_latest.txt",
        help="Paper 리뷰 자동 요약 저장 경로",
    )

    parser.add_argument(
        "--decisions",
        default="logs/orderflow_paper_decisions.jsonl",
        help="paper_config_candidates 용 decisions 파일 경로",
    )

    parser.add_argument(
        "--loss-analysis",
        default="reports/orderflow_loss_analysis.json",
        help="paper_config_candidates 용 loss analysis 파일 경로",
    )

    parser.add_argument(
        "--output-json",
        default="reports/orderflow_config_candidates.json",
        help="json 출력 경로 (paper-config-candidates 또는 paper-performance)",
    )

    parser.add_argument(
        "--output-txt",
        default="reports/orderflow_config_candidates.txt",
        help="paper_config_candidates txt 출력 경로",
    )

    parser.add_argument(
        "--ddm-output",
        default="reports/ddm_status.json",
        help="DDM 상태 저장 경로",
    )

    parser.add_argument(
        "--trades",
        default="logs/orderflow_paper_trades.jsonl",
        help="paper-performance 용 trades 파일 경로",
    )

    parser.add_argument(
        "--equity-output",
        default="logs/paper_equity_curve.jsonl",
        help="paper-performance equity curve 저장 경로",
    )

    parser.add_argument(
        "--summary-output",
        default="reports/paper_performance_summary.txt",
        help="paper-performance summary txt 저장 경로",
    )

    parser.add_argument(
        "--base-config",
        default="config/config.json",
        help="build-config-experiments 용 원본 설정 파일",
    )

    parser.add_argument(
        "--diagnostics",
        default="reports/rejection_diagnostics.json",
        help="build-config-experiments 용 진단 데이터",
    )

    parser.add_argument(
        "--output-dir",
        default="configs/experiments",
        help="build-config-experiments 용 출력 디렉토리",
    )
    
    parser.add_argument(
        "--ws",
        default="logs/upbit_ws_events.jsonl",
        help="volume-threshold-diagnostics 용 WebSocket 로그 경로",
    )
    
    parser.add_argument(
        "--snapshot",
        default="reports/microstructure_snapshot.json",
        help="orderflow-score-diagnostics 용 microstructure snapshot 경로",
    )
    
    parser.add_argument(
        "--opportunity",
        default="reports/opportunity_diagnostics.json",
        help="orderflow-score-diagnostics 용 opportunity diagnostics 경로",
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

    elif args.command == "microstructure":
        from .microstructure import build_microstructure_report

        result = build_microstructure_report(
            input_path=args.micro_input,
            output_path=args.micro_output,
        )

    elif args.command == "orderflow-paper":
        from .orderflow_paper import run_orderflow_paper_step

        result = run_orderflow_paper_step(
            config_path=args.config,
            microstructure_path=args.micro_output,
            state_path=args.paper_state,
            decisions_path=args.paper_decisions,
            trades_path=args.paper_trades,
        )

    elif args.command == "learning-log":
        from .learning_log import build_learning_dataset

        result = build_learning_dataset(
            decisions_path=args.paper_decisions,
            trades_path=args.paper_trades,
            output_path=args.learning_output,
            summary_path=args.learning_summary,
        )

    elif args.command == "loss-analysis":
        from .orderflow_loss_analyzer import build_orderflow_loss_analysis

        result = build_orderflow_loss_analysis(
            decisions_path=args.paper_decisions,
            trades_path=args.paper_trades,
            output_path=args.loss_output,
        )

    elif args.command == "paper-review":
        from .paper_review import build_paper_review

        result = build_paper_review(
            loss_analysis_path=args.loss_output,
            output_path=args.review_output,
        )

    elif args.command == "paper-config-candidates":
        from .paper_config_candidates import build_paper_config_candidates

        result = build_paper_config_candidates(
            decisions_path=args.decisions,
            loss_analysis_path=args.loss_analysis,
            output_json_path=args.output_json,
            output_txt_path=args.output_txt,
        )

    elif args.command == "ddm-status":
        from .ddm import run_ddm_status

        result = run_ddm_status(
            config_path=args.config,
            output_path=args.ddm_output,
        )

    elif args.command == "paper-performance":
        cfg = load_config(args.config)
        portfolio = cfg.get("portfolio", {})
        starting_cash = float(portfolio.get("starting_cash_krw", 1000000.0))

        from .paper_performance import run_paper_performance

        result = run_paper_performance(
            trades_path=args.trades,
            decisions_path=args.decisions,
            output_json_path=args.output_json,
            equity_output_path=args.equity_output,
            summary_output_path=args.summary_output,
            starting_cash_krw=starting_cash,
        )

    elif args.command == "rejection-diagnostics":
        from .rejection_diagnostics import run_rejection_diagnostics

        result = run_rejection_diagnostics(
            decisions_path=args.decisions,
            output_json_path=args.output_json,
            output_txt_path=args.output_txt,
        )

    elif args.command == "build-config-experiments":
        from .config_experiment_builder import run_config_experiment_builder

        result = run_config_experiment_builder(
            base_config=args.base_config,
            diagnostics=args.diagnostics,
            output_dir=args.output_dir,
        )

    elif args.command == "volume-threshold-diagnostics":
        from .volume_threshold_diagnostics import run_diagnostics
        
        result = run_diagnostics(
            ws_path=args.ws,
            output_json=args.output_json,
            output_txt=args.output_txt,
        )

    elif args.command == "opportunity-diagnostics":
        from .opportunity_diagnostics import run_opportunity_diagnostics
        
        result = run_opportunity_diagnostics(
            ws_path=args.ws,
            config_path=args.config,
            output_json=args.output_json,
            output_txt=args.output_txt,
        )

    elif args.command == "orderflow-score-diagnostics":
        from .orderflow_score_diagnostics import run_orderflow_score_diagnostics
        
        result = run_orderflow_score_diagnostics(
            snapshot_path=args.snapshot,
            opportunity_path=args.opportunity,
            config_path=args.config,
            output_json=args.output_json,
            output_txt=args.output_txt,
        )

    elif args.command == "score-component-diagnostics":
        from .score_component_diagnostics import run_score_component_diagnostics
        
        result = run_score_component_diagnostics(
            opportunity_path=args.opportunity,
            ws_path=args.ws,
            config_path=args.config,
            output_json=args.output_json,
            output_txt=args.output_txt,
        )

    else:
        raise ValueError(f"unknown command: {args.command}")

    _print_json(result)


if __name__ == "__main__":
    main()