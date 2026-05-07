from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Any
import json
from .config_loader import load_config
from .data import load_candles_csv
from .models import Candle
from .regime import RegimeFilter
from .strategy import MultiFactorStrategy
from .risk import RiskManager
from .loss_filter import LossPatternFilter
from .broker import PaperBroker
from .state import StateStore
from .jsonl import JsonlLogger

class BacktestEngine:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg=cfg
        self.strategy=MultiFactorStrategy(cfg)
        self.regime=RegimeFilter(cfg["regime"])
        self.risk=RiskManager(cfg)
        self.loss_filter=LossPatternFilter(cfg)
        self.broker=PaperBroker(cfg)
        paths=cfg["paths"]
        self.trades_log=JsonlLogger(Path(paths["logs_dir"])/"trades.jsonl")
        self.decisions_log=JsonlLogger(Path(paths["logs_dir"])/"decisions.jsonl")
        self.state_store=StateStore(Path(paths["runtime_dir"])/"state.json")
        self.state=self.state_store.load()

    def run(self, csv_path: str = "data/sample_ohlcv.csv") -> Dict[str, Any]:
        by_market=load_candles_csv(csv_path)
        btc_market=self.cfg["regime"].get("btc_market","KRW-BTC")
        # Use synchronized index length by smallest available market.
        min_len=min(len(v) for v in by_market.values())
        histories={m:[] for m in by_market}
        last_prices={m:0.0 for m in by_market}
        for i in range(min_len):
            for m, series in by_market.items():
                candle=series[i]
                histories[m].append(candle)
                last_prices[m]=candle.close
            btc_hist=histories.get(btc_market) or next(iter(histories.values()))
            regime=self.regime.classify(btc_hist)
            for market in self.cfg["markets"]:
                if market not in histories or not histories[market]:
                    continue
                candle=histories[market][-1]
                # Broker stop/TP update first.
                trade=self.broker.update_position(candle)
                if trade:
                    self.trades_log.write(trade.to_dict())
                    self.state=StateStore.update_after_trade(self.state, trade.to_dict())
                    self.state_store.save(self.state)
                    continue
                pos=self.broker.positions.get(market)
                sig=self.strategy.signal(market, histories[market], pos, regime)
                if pos:
                    trade=self.broker.exit_by_signal(candle, sig)
                    if trade:
                        self.trades_log.write(trade.to_dict())
                        self.state=StateStore.update_after_trade(self.state, trade.to_dict())
                        self.state_store.save(self.state)
                    continue
                loss_decision=self.loss_filter.allow_market(market, candle.timestamp, self.state)
                risk_decision={"allow":False,"reason":"not_checked","size_krw":0}
                if sig.action == "ENTER_LONG" and loss_decision["allow"]:
                    risk_decision=self.risk.approve_entry(market, sig, self.broker.equity(last_prices), self.broker.cash, len(self.broker.positions), self.state)
                    if risk_decision["allow"]:
                        self.broker.enter_long(candle, risk_decision["size_krw"], sig)
                self.decisions_log.write({
                    "timestamp":candle.timestamp,"market":market,"signal":sig.action,"score":sig.score,
                    "reason":sig.reason,"regime":regime,"loss_filter":loss_decision,"risk":risk_decision,
                    "cash":round(self.broker.cash,2),"open_positions":len(self.broker.positions)
                })
        # Liquidate remaining positions at last price.
        for market, pos in list(self.broker.positions.items()):
            candle=histories[market][-1]
            trade=self.broker.exit_position(candle, "end_of_backtest", candle.close)
            if trade:
                self.trades_log.write(trade.to_dict())
                self.state=StateStore.update_after_trade(self.state, trade.to_dict())
        self.state_store.save(self.state)
        return {"cash":self.broker.cash, "trades":len(self.broker.trades), "equity":self.broker.equity(last_prices)}

def run_backtest(config_path: str = "config/config.json", csv_path: str = "data/sample_ohlcv.csv") -> Dict[str, Any]:
    cfg=load_config(config_path)
    # reset logs for deterministic local run
    for f in [Path(cfg["paths"]["logs_dir"])/"trades.jsonl", Path(cfg["paths"]["logs_dir"])/"decisions.jsonl"]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("", encoding="utf-8")
    engine=BacktestEngine(cfg)
    result=engine.run(csv_path)
    out=Path(cfg["paths"]["reports_dir"])/"backtest_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
