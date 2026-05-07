from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from .broker import PaperBroker
from .config_loader import load_config
from .data import load_candles_from_csv, split_candles_by_market
from .jsonl import write_json, write_jsonl
from .models import Candle, Trade
from .risk import RiskManager
from .strategy import generate_signal


def run_backtest(
    config_path: str = "config/config.json",
    csv_path: str = "data/sample_ohlcv.csv",
) -> Dict[str, Any]:
    config = load_config(config_path)

    candles = load_candles_from_csv(csv_path)
    candles_by_market = split_candles_by_market(candles)

    portfolio_config = config.get("portfolio", {})
    risk_config = config.get("risk", {})
    strategy_config = config.get("strategy", {})
    paths_config = config.get("paths", {})

    starting_cash_krw = float(portfolio_config.get("starting_cash_krw", 1_000_000))
    fee_rate = float(risk_config.get("fee_rate", 0.0005))
    slippage_pct = float(risk_config.get("slippage_pct", 0.05))
    min_order_krw = float(risk_config.get("min_order_krw", 5_000))
    max_holding_bars = int(strategy_config.get("max_holding_bars", 48))

    trades_path = paths_config.get("trades_log", "logs/trades.jsonl")
    decisions_path = paths_config.get("decisions_log", "logs/decisions.jsonl")
    state_path = paths_config.get("state", "runtime/state.json")

    broker = PaperBroker(
        starting_cash_krw=starting_cash_krw,
        fee_rate=fee_rate,
        slippage_pct=slippage_pct,
        min_order_krw=min_order_krw,
    )

    risk_manager = RiskManager.from_config(config)

    last_prices: Dict[str, float] = {}

    for market, market_candles in candles_by_market.items():
        _run_market_backtest(
            market=market,
            candles=market_candles,
            config=config,
            broker=broker,
            risk_manager=risk_manager,
            max_holding_bars=max_holding_bars,
            last_prices=last_prices,
        )

    if candles:
        last_timestamp = candles[-1].timestamp
    else:
        last_timestamp = "unknown"

    force_closed_trades = broker.force_close_all(
        timestamp=last_timestamp,
        last_prices=last_prices,
        reason_exit="force_close_end_of_backtest",
    )

    for trade in force_closed_trades:
        risk_manager.record_trade_result(trade.pnl_krw)

    trade_rows = [trade.to_dict() for trade in broker.trades]
    decision_rows = broker.decision_logs

    write_jsonl(trades_path, trade_rows)
    write_jsonl(decisions_path, decision_rows)

    final_equity_krw = broker.equity_krw(last_prices)
    total_pnl_krw = final_equity_krw - starting_cash_krw
    total_pnl_pct = (total_pnl_krw / starting_cash_krw) * 100.0

    state = {
        "mode": "backtest",
        "exchange": "upbit",
        "market_type": "KRW",
        "starting_cash_krw": starting_cash_krw,
        "final_cash_krw": broker.cash_krw,
        "final_equity_krw": final_equity_krw,
        "total_pnl_krw": total_pnl_krw,
        "total_pnl_pct": total_pnl_pct,
        "open_positions": {
            market: asdict(position)
            for market, position in broker.positions.items()
        },
        "risk": risk_manager.to_dict(),
        "last_prices": last_prices,
        "trades_path": trades_path,
        "decisions_path": decisions_path,
    }

    write_json(state_path, state)

    return {
        "ok": True,
        "command": "backtest",
        "exchange": "upbit",
        "market_type": "KRW",
        "csv_path": csv_path,
        "markets": list(candles_by_market.keys()),
        "total_candles": len(candles),
        "total_trades": len(broker.trades),
        "starting_cash_krw": round(starting_cash_krw, 2),
        "final_equity_krw": round(final_equity_krw, 2),
        "total_pnl_krw": round(total_pnl_krw, 2),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "trades_path": trades_path,
        "decisions_path": decisions_path,
        "state_path": state_path,
    }


def _run_market_backtest(
    market: str,
    candles: List[Candle],
    config: Dict[str, Any],
    broker: PaperBroker,
    risk_manager: RiskManager,
    max_holding_bars: int,
    last_prices: Dict[str, float],
) -> None:
    for index, candle in enumerate(candles):
        last_prices[market] = candle.close

        broker.update_position_price(
            market=market,
            price=candle.close,
        )

        exit_reason = broker.check_exit_reason(
            market=market,
            price=candle.close,
            max_holding_bars=max_holding_bars,
        )

        if exit_reason is not None:
            trade = broker.sell(
                timestamp=candle.timestamp,
                market=market,
                price=candle.close,
                reason_exit=exit_reason,
            )

            if trade is not None:
                risk_manager.record_trade_result(trade.pnl_krw)

        signal = generate_signal(
            candles=candles,
            index=index,
            config=config,
        )

        if signal.action != "BUY":
            broker.decision_logs.append(
                {
                    "timestamp": candle.timestamp,
                    "market": market,
                    "action": "NO_BUY",
                    "reason": signal.reason,
                    "score": signal.score,
                    "close": candle.close,
                    "signal": signal.to_dict(),
                }
            )
            continue

        equity_krw = broker.equity_krw(last_prices)

        risk_decision = risk_manager.check_entry(
            market=market,
            cash_krw=broker.cash_krw,
            equity_krw=equity_krw,
            open_position_count=broker.open_position_count(),
            already_has_position=broker.has_position(market),
        )

        if not risk_decision.ok:
            broker.decision_logs.append(
                {
                    "timestamp": candle.timestamp,
                    "market": market,
                    "action": "BUY_BLOCKED_BY_RISK",
                    "reason": risk_decision.reason,
                    "amount_krw": risk_decision.amount_krw,
                    "score": signal.score,
                    "signal": signal.to_dict(),
                    "risk": risk_decision.to_dict(),
                }
            )
            continue

        broker.buy(
            timestamp=candle.timestamp,
            signal=signal,
            amount_krw=risk_decision.amount_krw,
        )


def summarize_trades(trades: List[Trade]) -> Dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl_krw": 0.0,
            "avg_pnl_pct": 0.0,
        }

    wins = [trade for trade in trades if trade.pnl_krw > 0]
    total_pnl_krw = sum(trade.pnl_krw for trade in trades)
    avg_pnl_pct = sum(trade.pnl_pct for trade in trades) / len(trades)

    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "total_pnl_krw": total_pnl_krw,
        "avg_pnl_pct": avg_pnl_pct,
    }