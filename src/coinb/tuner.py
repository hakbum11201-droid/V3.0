from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, Any, List

from .config_loader import load_config
from .backtest import run_backtest
from .report import run_report


def run_tuner(config_path: str = "config/config.json", csv_path: str = "data/sample_ohlcv.csv") -> Dict[str, Any]:
    base_cfg = load_config(config_path)
    candidates: List[Dict[str, Any]] = []

    grids = [
        {"score_min": 3, "rsi_max_entry": 78, "take_profit_pct": 0.030, "stop_loss_pct": 0.018},
        {"score_min": 4, "rsi_max_entry": 74, "take_profit_pct": 0.035, "stop_loss_pct": 0.016},
        {"score_min": 5, "rsi_max_entry": 70, "take_profit_pct": 0.040, "stop_loss_pct": 0.015},
    ]

    temp_config = Path(base_cfg["paths"]["runtime_dir"]) / "_tuner_config.json"
    temp_config.parent.mkdir(parents=True, exist_ok=True)

    for i, params in enumerate(grids, start=1):
        cfg = copy.deepcopy(base_cfg)
        cfg["strategy"].update(params)
        temp_config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

        backtest_result = run_backtest(str(temp_config), csv_path)
        report = run_report(str(temp_config))

        score = (
            report.get("expectancy_krw", 0)
            + report.get("total_pnl_krw", 0) * 0.1
            - abs(report.get("max_drawdown", 0)) * 10000
            - report.get("consecutive_losses", 0) * 100
        )

        candidates.append({
            "rank_input": i,
            "params": params,
            "score": score,
            "backtest": backtest_result,
            "report": report,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    summary = {
        "best": candidates[0] if candidates else None,
        "candidates": candidates,
        "note": "자동으로 코드 수정하지 않음. candidate config는 사람이 확인 후 적용.",
    }

    out = Path(base_cfg["paths"]["reports_dir"]) / "tuner_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if candidates:
        candidate_cfg = copy.deepcopy(base_cfg)
        candidate_cfg["strategy"].update(candidates[0]["params"])
        candidate_out = Path(base_cfg["paths"]["reports_dir"]) / "config_candidate.json"
        candidate_out.write_text(json.dumps(candidate_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary
