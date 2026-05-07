from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

from .backtest import run_backtest
from .config_loader import load_config
from .jsonl import read_jsonl, write_json
from .report import build_performance_summary


def run_tuner(
    config_path: str = "config/config.json",
    csv_path: str = "data/sample_ohlcv.csv",
) -> Dict[str, Any]:
    base_config = load_config(config_path)
    paths_config = base_config.get("paths", {})

    trades_path = paths_config.get("trades_log", "logs/trades.jsonl")
    tuner_report_path = paths_config.get("tuner_report", "reports/tuner_summary.json")
    candidate_config_path = paths_config.get("candidate_config", "reports/config_candidate.json")
    temp_config_path = "runtime/_tuner_config.json"

    candidates = build_candidates(base_config)

    results: List[Dict[str, Any]] = []

    for candidate in candidates:
        candidate_config = candidate["config"]

        write_json(temp_config_path, candidate_config)

        backtest_result = run_backtest(
            config_path=temp_config_path,
            csv_path=csv_path,
        )

        trades = read_jsonl(trades_path)
        performance = build_performance_summary(trades)

        result = {
            "name": candidate["name"],
            "description": candidate["description"],
            "params": candidate["params"],
            "backtest": backtest_result,
            "performance": performance,
            "score": calc_candidate_score(performance),
        }

        results.append(result)

    best_result = select_best_result(results)

    report = {
        "ok": True,
        "command": "tune",
        "exchange": "upbit",
        "market_type": "KRW",
        "auto_apply": False,
        "message": "튜너는 config 후보만 생성합니다. 자동 적용은 하지 않습니다.",
        "csv_path": csv_path,
        "candidate_count": len(results),
        "best": best_result,
        "results": results,
        "tuner_report_path": tuner_report_path,
        "candidate_config_path": candidate_config_path,
    }

    write_json(tuner_report_path, report)

    if best_result:
        best_config = find_candidate_config(candidates, best_result["name"])
        write_json(candidate_config_path, best_config)

    return {
        "ok": True,
        "command": "tune",
        "auto_apply": False,
        "candidate_count": len(results),
        "best_name": best_result["name"] if best_result else "",
        "best_score": best_result["score"] if best_result else 0.0,
        "tuner_report_path": tuner_report_path,
        "candidate_config_path": candidate_config_path,
    }


def build_candidates(base_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    base_strategy = base_config.get("strategy", {})

    candidate_specs = [
        {
            "name": "base",
            "description": "기존 설정 유지",
            "updates": {},
        },
        {
            "name": "conservative_filter",
            "description": "진입 기준 강화",
            "updates": {
                "min_score": _float(base_strategy.get("min_score", 3.0)) + 1.0,
                "volume_ratio_min": _float(base_strategy.get("volume_ratio_min", 1.2)) + 0.3,
                "rsi_max": max(60.0, _float(base_strategy.get("rsi_max", 72.0)) - 5.0),
            },
        },
        {
            "name": "faster_take_profit",
            "description": "익절을 빠르게 가져가는 후보",
            "updates": {
                "take_profit_pct": max(0.4, _float(base_strategy.get("take_profit_pct", 1.4)) - 0.3),
                "stop_loss_pct": _float(base_strategy.get("stop_loss_pct", 0.8),
                ),
            },
        },
        {
            "name": "tighter_stop",
            "description": "손절폭 축소 후보",
            "updates": {
                "stop_loss_pct": max(0.3, _float(base_strategy.get("stop_loss_pct", 0.8)) - 0.2),
                "trailing_stop_pct": max(0.3, _float(base_strategy.get("trailing_stop_pct", 0.7)) - 0.1),
            },
        },
        {
            "name": "volume_first",
            "description": "거래량 참여도 우선 후보",
            "updates": {
                "volume_ratio_min": _float(base_strategy.get("volume_ratio_min", 1.2)) + 0.6,
                "min_score": _float(base_strategy.get("min_score", 3.0)),
            },
        },
    ]

    for spec in candidate_specs:
        candidate_config = copy.deepcopy(base_config)
        candidate_config.setdefault("strategy", {})

        for key, value in spec["updates"].items():
            candidate_config["strategy"][key] = value

        block_live_trading(candidate_config)

        candidates.append(
            {
                "name": spec["name"],
                "description": spec["description"],
                "params": spec["updates"],
                "config": candidate_config,
            }
        )

    return candidates


def block_live_trading(config: Dict[str, Any]) -> None:
    config.setdefault("live", {})
    config["live"]["enabled"] = False


def calc_candidate_score(performance: Dict[str, Any]) -> float:
    total_trades = _float(performance.get("total_trades", 0))
    win_rate = _float(performance.get("win_rate", 0.0))
    profit_factor = _float(performance.get("profit_factor", 0.0))
    expectancy_pct = _float(performance.get("expectancy_pct", 0.0))
    max_drawdown_krw = _float(performance.get("max_drawdown_krw", 0.0))

    if total_trades <= 0:
        return -9999.0

    score = 0.0
    score += expectancy_pct * 10.0
    score += win_rate * 5.0
    score += min(profit_factor, 5.0) * 2.0
    score -= max_drawdown_krw / 100_000.0

    if total_trades < 3:
        score -= 3.0

    return round(score, 6)


def select_best_result(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}

    return max(results, key=lambda item: item.get("score", -9999.0))


def find_candidate_config(
    candidates: List[Dict[str, Any]],
    name: str,
) -> Dict[str, Any]:
    for candidate in candidates:
        if candidate["name"] == name:
            return candidate["config"]

    return {}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0