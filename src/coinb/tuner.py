from __future__ import annotations
import itertools, json, copy
from pathlib import Path
from typing import Dict, Any, List
from .config_loader import load_config
from .backtest import BacktestEngine
from .report import analyze_trades
from .jsonl import read_jsonl

class ParameterTuner:
    def __init__(self, cfg: Dict[str, Any], csv_path: str = "data/sample_ohlcv.csv"):
        self.base=cfg
        self.csv_path=csv_path

    def run(self) -> Dict[str, Any]:
        grid=self.base.get("tuner", {})
        keys=list(grid.keys())
        combos=list(itertools.product(*(grid[k] for k in keys)))
        results=[]
        for idx, combo in enumerate(combos, start=1):
            cfg=copy.deepcopy(self.base)
            cfg["paths"]={**cfg["paths"], "logs_dir":f"logs/tuner/{idx}", "runtime_dir":f"runtime/tuner/{idx}"}
            for k,v in zip(keys, combo):
                cfg["strategy"][k]=v
            # reset logs
            Path(cfg["paths"]["logs_dir"]).mkdir(parents=True, exist_ok=True)
            (Path(cfg["paths"]["logs_dir"])/"trades.jsonl").write_text("", encoding="utf-8")
            (Path(cfg["paths"]["logs_dir"])/"decisions.jsonl").write_text("", encoding="utf-8")
            engine=BacktestEngine(cfg)
            engine.run(self.csv_path)
            trades=list(read_jsonl(Path(cfg["paths"]["logs_dir"])/"trades.jsonl"))
            rep=analyze_trades(trades, cfg["portfolio"]["initial_cash_krw"])
            penalty=abs(min(rep["max_drawdown"],0))*100000
            score=rep["expectancy_krw"]*rep["total_trades"] + rep["profit_factor"]*100 - penalty
            results.append({"params":dict(zip(keys, combo)), "score":score, "report":rep})
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"best":results[0] if results else None, "top5":results[:5], "tested":len(results)}

def run_tuner(config_path: str = "config/config.json", csv_path: str = "data/sample_ohlcv.csv") -> Dict[str, Any]:
    cfg=load_config(config_path)
    summary=ParameterTuner(cfg,csv_path).run()
    out=Path(cfg["paths"]["reports_dir"])/"tuner_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
