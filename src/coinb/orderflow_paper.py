from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .config_loader import load_config
from .execution_model import simulate_virtual_buy_fill, simulate_virtual_sell_fill
from .jsonl import append_jsonl, read_json, write_json
from .market_rules import is_min_order_ok


@dataclass
class PaperDecision:
    timestamp: float
    market: str
    action: str
    reason: str
    score: float
    price: float
    expected_edge: float
    slippage_estimate: float
    virtual_fill_result: Dict[str, Any]
    diagnostic: Dict[str, Any]
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperTrade:
    timestamp: float
    market: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl_krw: float
    pnl_pct: float
    fee_krw: float
    reason_entry: str
    reason_exit: str
    max_profit_pct: float
    max_drawdown_pct: float
    holding_seconds: float
    expected_edge: float
    slippage_estimate: float
    virtual_fill_result: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_orderflow_paper_step(
    config_path: str = "config/config.json",
    microstructure_path: str = "reports/microstructure_snapshot.json",
    state_path: str = "runtime/orderflow_paper_state.json",
    decisions_path: str = "logs/orderflow_paper_decisions.jsonl",
    trades_path: str = "logs/orderflow_paper_trades.jsonl",
) -> Dict[str, Any]:
    config = load_config(config_path)
    report = read_json(microstructure_path, default={})

    if not report:
        raise FileNotFoundError(
            f"microstructure report not found or empty: {microstructure_path}"
        )

    features_by_market = report.get("features", {})

    if not isinstance(features_by_market, dict) or not features_by_market:
        raise ValueError("microstructure report has no market features")

    state = load_or_create_state(config, state_path)
    now = time.time()

    decisions: List[PaperDecision] = []
    trades: List[PaperTrade] = []

    for market, features in features_by_market.items():
        if not isinstance(features, dict):
            continue

        price = get_reference_price(features)

        if price <= 0:
            decision = make_decision(
                market=market,
                action="SKIP",
                reason="invalid_price",
                score=0.0,
                price=0.0,
                features=features,
                extra={},
            )
            decisions.append(decision)
            append_jsonl(decisions_path, decision.to_dict())
            continue

        update_position_stats(state, market, price)

        exit_reason = check_exit_condition(config, state, market, features, now)

        if exit_reason:
            trade = virtual_sell(
                config=config,
                state=state,
                market=market,
                features=features,
                reason_exit=exit_reason,
                now=now,
            )

            if trade is not None:
                trades.append(trade)
                append_jsonl(trades_path, trade.to_dict())

                decision = make_decision(
                    market=market,
                    action="VIRTUAL_SELL",
                    reason=exit_reason,
                    score=float(features.get("continuation_score", 0.0)),
                    price=trade.exit_price,
                    features=features,
                    extra={"trade": trade.to_dict()},
                )
                decisions.append(decision)
                append_jsonl(decisions_path, decision.to_dict())

            continue

        if has_position(state, market):
            decision = make_decision(
                market=market,
                action="HOLD_POSITION",
                reason="position_already_open",
                score=float(features.get("continuation_score", 0.0)),
                price=price,
                features=features,
                extra={},
            )
            decisions.append(decision)
            append_jsonl(decisions_path, decision.to_dict())
            continue

        entry_decision = check_entry_condition(config, state, market, features, price)
        decisions.append(entry_decision)
        append_jsonl(decisions_path, entry_decision.to_dict())

        if entry_decision.action == "VIRTUAL_BUY":
            virtual_buy(
                config=config,
                state=state,
                market=market,
                reason_entry=entry_decision.reason,
                features=features,
                now=now,
            )

    state["last_updated"] = now
    write_json(state_path, state)

    return {
        "ok": True,
        "command": "orderflow-paper",
        "exchange": "upbit",
        "market_type": "KRW",
        "mode": "paper",
        "execution_model": config.get("execution", {}).get("paper_fill_model", "orderbook_depth_v1"),
        "microstructure_path": microstructure_path,
        "state_path": state_path,
        "decisions_path": decisions_path,
        "trades_path": trades_path,
        "decision_count": len(decisions),
        "trade_count": len(trades),
        "cash_krw": round(float(state.get("cash_krw", 0.0)), 2),
        "open_positions": list(state.get("positions", {}).keys()),
    }


def load_or_create_state(config: Dict[str, Any], state_path: str) -> Dict[str, Any]:
    state = read_json(state_path, default={})

    if state:
        state.setdefault("positions", {})
        state.setdefault("stats", {})
        return state

    portfolio = config.get("portfolio", {})
    starting_cash_krw = float(portfolio.get("starting_cash_krw", 1_000_000))

    return {
        "mode": "paper",
        "exchange": "upbit",
        "market_type": "KRW",
        "starting_cash_krw": starting_cash_krw,
        "cash_krw": starting_cash_krw,
        "positions": {},
        "stats": {
            "virtual_buy_count": 0,
            "virtual_sell_count": 0,
            "realized_pnl_krw": 0.0,
        },
        "last_updated": time.time(),
    }


def check_entry_condition(
    config: Dict[str, Any],
    state: Dict[str, Any],
    market: str,
    features: Dict[str, Any],
    price: float,
) -> PaperDecision:
    portfolio = config.get("portfolio", {})
    risk = config.get("risk", {})
    micro = config.get("microstructure", {})
    execution = config.get("execution", {})

    cash_krw = float(state.get("cash_krw", 0.0))
    positions = state.get("positions", {})

    max_open_positions = int(portfolio.get("max_open_positions", 2))
    max_position_krw = float(portfolio.get("max_position_krw", 100_000))
    position_size_pct = float(portfolio.get("position_size_pct", 10.0))
    min_order_krw = float(risk.get("min_order_krw", 5_000))
    fee_rate = float(risk.get("fee_rate", 0.0005))

    max_spread_pct = float(micro.get("max_spread_pct", 0.12))
    min_trade_value_3s = float(micro.get("min_trade_value_3s", 30_000_000))
    continuation_min = float(micro.get("continuation_score_min", 65))
    ofi_min = float(micro.get("ofi_score_min", 50))
    sweep_min = float(micro.get("sweep_score_min", 70))
    absorption_min = float(micro.get("absorption_score_min", 65))
    depth_ratio_min = float(micro.get("bid_ask_depth_ratio_min", 1.05))

    max_depth_take_ratio = float(execution.get("max_depth_take_ratio", 0.10))
    min_liquidity_multiple = float(execution.get("min_liquidity_multiple", 3.0))
    extra_slippage_pct = float(execution.get("extra_slippage_pct", 0.03))

    continuation_score = float(features.get("continuation_score", 0.0))
    ofi_score = float(features.get("ofi_score", 0.0))
    sweep_score = float(features.get("sweep_score", 0.0))
    absorption_score = float(features.get("absorption_score", 0.0))
    spread_pct = float(features.get("spread_pct", 999.0))
    buy_trade_value_3s = float(features.get("buy_trade_value_3s", 0.0))
    depth_ratio = float(features.get("bid_ask_depth_ratio_5", 0.0))

    score = calc_entry_score(features)

    # DDM Gate Check: 신규 진입 차단 상태 확인
    ddm = read_json("reports/ddm_status.json", default={})
    if ddm.get("should_block_new_entry") is True:
        diag = {
            "checked_field": "ddm.should_block_new_entry",
            "actual_value": True,
            "required_value": False,
            "ddm_status": ddm.get("status"),
            "risk_level": ddm.get("risk_level"),
            "summary": ddm.get("summary")
        }
        return make_decision(market, "NO_BUY", "DDM_BLOCK_NEW_ENTRY", score, price, features, {"diagnostic": diag})

    if len(positions) >= max_open_positions:
        return make_decision(market, "NO_BUY", "RISK_BLOCKED:MAX_POSITIONS", score, price, features, {})

    if cash_krw < min_order_krw:
        return make_decision(market, "NO_BUY", "RISK_BLOCKED:NO_CASH", score, price, features, {})

    if spread_pct > max_spread_pct:
        diag = {
            "checked_field": "spread_pct",
            "actual_value": round(spread_pct, 6),
            "required_value": round(max_spread_pct, 6),
            "gap": round(spread_pct - max_spread_pct, 6),
            "gap_pct": round((spread_pct - max_spread_pct) / max_spread_pct * 100.0, 2) if max_spread_pct > 0 else 0.0
        }
        return make_decision(market, "NO_BUY", "SPREAD_TOO_WIDE", score, price, features, {"diagnostic": diag})

    if buy_trade_value_3s < min_trade_value_3s:
        diag = {
            "checked_field": "buy_trade_value_3s",
            "actual_value": round(buy_trade_value_3s, 2),
            "required_value": round(min_trade_value_3s, 2),
            "gap": round(buy_trade_value_3s - min_trade_value_3s, 2),
            "gap_pct": round((buy_trade_value_3s - min_trade_value_3s) / min_trade_value_3s * 100.0, 2) if min_trade_value_3s > 0 else 0.0
        }
        return make_decision(market, "NO_BUY", "LOW_VOLUME", score, price, features, {"diagnostic": diag})

    if depth_ratio < depth_ratio_min:
        diag = {
            "checked_field": "bid_ask_depth_ratio_5",
            "actual_value": round(depth_ratio, 4),
            "required_value": round(depth_ratio_min, 4),
            "gap": round(depth_ratio - depth_ratio_min, 4),
            "gap_pct": round((depth_ratio - depth_ratio_min) / depth_ratio_min * 100.0, 2) if depth_ratio_min > 0 else 0.0
        }
        return make_decision(market, "NO_BUY", "LOW_IMBALANCE", score, price, features, {"diagnostic": diag})

    continuation_ok = continuation_score >= continuation_min
    sweep_ok = ofi_score >= ofi_min and sweep_score >= sweep_min
    absorption_ok = absorption_score >= absorption_min and ofi_score >= ofi_min

    if not (continuation_ok or sweep_ok or absorption_ok):
        return make_decision(market, "NO_BUY", "LOW_MOMENTUM", score, price, features, {})

    equity_krw = calc_equity_krw(state)
    requested_krw = min(
        max_position_krw,
        equity_krw * (position_size_pct / 100.0),
        cash_krw,
    )

    if not is_min_order_ok(requested_krw, min_order_krw):
        return make_decision(market, "NO_BUY", "RISK_BLOCKED:MIN_ORDER", score, price, features, {})

    fill = simulate_virtual_buy_fill(
        market=market,
        features=features,
        requested_krw=requested_krw,
        fee_rate=fee_rate,
        min_order_krw=min_order_krw,
        max_depth_take_ratio=max_depth_take_ratio,
        min_liquidity_multiple=min_liquidity_multiple,
        extra_slippage_pct=extra_slippage_pct,
    )

    if not fill.ok:
        return make_decision(
            market=market,
            action="NO_BUY",
            reason=f"FILL_FAILED:{fill.reason}",
            score=score,
            price=price,
            features=features,
            extra={"fill": fill.to_dict()},
        )

    return make_decision(
        market=market,
        action="VIRTUAL_BUY",
        reason="ENTRY_APPROVED",
        score=score,
        price=fill.price,
        features=features,
        extra={"fill": fill.to_dict()},
    )


def virtual_buy(
    config: Dict[str, Any],
    state: Dict[str, Any],
    market: str,
    reason_entry: str,
    features: Dict[str, Any],
    now: float,
) -> None:
    portfolio = config.get("portfolio", {})
    risk = config.get("risk", {})
    execution = config.get("execution", {})

    max_position_krw = float(portfolio.get("max_position_krw", 100_000))
    position_size_pct = float(portfolio.get("position_size_pct", 10.0))
    fee_rate = float(risk.get("fee_rate", 0.0005))
    min_order_krw = float(risk.get("min_order_krw", 5_000))

    max_depth_take_ratio = float(execution.get("max_depth_take_ratio", 0.10))
    min_liquidity_multiple = float(execution.get("min_liquidity_multiple", 3.0))
    extra_slippage_pct = float(execution.get("extra_slippage_pct", 0.03))

    cash_krw = float(state.get("cash_krw", 0.0))
    equity_krw = calc_equity_krw(state)
    requested_krw = min(
        max_position_krw,
        equity_krw * (position_size_pct / 100.0),
        cash_krw,
    )

    fill = simulate_virtual_buy_fill(
        market=market,
        features=features,
        requested_krw=requested_krw,
        fee_rate=fee_rate,
        min_order_krw=min_order_krw,
        max_depth_take_ratio=max_depth_take_ratio,
        min_liquidity_multiple=min_liquidity_multiple,
        extra_slippage_pct=extra_slippage_pct,
    )

    if not fill.ok:
        return

    state["cash_krw"] = cash_krw - fill.filled_krw
    state.setdefault("positions", {})

    state["positions"][market] = {
        "market": market,
        "entry_timestamp": now,
        "entry_price": fill.price,
        "qty": fill.qty,
        "amount_krw": fill.filled_krw,
        "entry_fee_krw": fill.fee_krw,
        "reason_entry": reason_entry,
        "peak_price": fill.price,
        "trough_price": fill.price,
        "max_profit_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "entry_features": features,
        "entry_fill": fill.to_dict(),
    }

    stats = state.setdefault("stats", {})
    stats["virtual_buy_count"] = int(stats.get("virtual_buy_count", 0)) + 1


def check_exit_condition(
    config: Dict[str, Any],
    state: Dict[str, Any],
    market: str,
    features: Dict[str, Any],
    now: float,
) -> Optional[str]:
    if not has_position(state, market):
        return None

    strategy = config.get("strategy", {})

    stop_loss_pct = float(strategy.get("stop_loss_pct", 0.8))
    take_profit_pct = float(strategy.get("take_profit_pct", 1.4))
    max_holding_seconds = float(strategy.get("max_holding_seconds", 300))
    weak_continuation_score = float(strategy.get("weak_continuation_score", 25.0))

    position = state["positions"][market]
    entry_price = float(position.get("entry_price", 0.0))
    current_price = get_exit_reference_price(features)

    if entry_price <= 0 or current_price <= 0:
        return None

    pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
    holding_seconds = now - float(position.get("entry_timestamp", now))
    continuation_score = float(features.get("continuation_score", 0.0))

    if pnl_pct <= -stop_loss_pct:
        return "stop_loss"

    if pnl_pct >= take_profit_pct:
        return "take_profit"

    if holding_seconds >= max_holding_seconds:
        return "max_holding_seconds"

    if pnl_pct > 0 and continuation_score <= weak_continuation_score:
        return "weak_continuation_profit_exit"

    return None


def virtual_sell(
    config: Dict[str, Any],
    state: Dict[str, Any],
    market: str,
    features: Dict[str, Any],
    reason_exit: str,
    now: float,
) -> Optional[PaperTrade]:
    if not has_position(state, market):
        return None

    risk = config.get("risk", {})
    execution = config.get("execution", {})

    fee_rate = float(risk.get("fee_rate", 0.0005))
    max_depth_take_ratio = float(execution.get("max_depth_take_ratio", 0.10))
    min_liquidity_multiple = float(execution.get("min_liquidity_multiple", 3.0))
    extra_slippage_pct = float(execution.get("extra_slippage_pct", 0.03))
    allow_forced_exit = bool(execution.get("allow_forced_exit_on_low_liquidity", True))

    position = state["positions"][market]

    entry_price = float(position.get("entry_price", 0.0))
    qty = float(position.get("qty", 0.0))
    entry_fee_krw = float(position.get("entry_fee_krw", 0.0))
    entry_timestamp = float(position.get("entry_timestamp", now))

    fill = simulate_virtual_sell_fill(
        market=market,
        features=features,
        qty=qty,
        entry_price=entry_price,
        fee_rate=fee_rate,
        max_depth_take_ratio=max_depth_take_ratio,
        min_liquidity_multiple=min_liquidity_multiple,
        extra_slippage_pct=extra_slippage_pct,
        allow_forced_exit_on_low_liquidity=allow_forced_exit,
    )

    if not fill.ok:
        return None

    net_exit_krw = fill.filled_krw - fill.fee_krw
    entry_value_krw = entry_price * qty
    pnl_krw = net_exit_krw - entry_value_krw
    pnl_pct = (pnl_krw / entry_value_krw) * 100.0 if entry_value_krw > 0 else 0.0

    state["cash_krw"] = float(state.get("cash_krw", 0.0)) + net_exit_krw

    stats = state.setdefault("stats", {})
    stats["virtual_sell_count"] = int(stats.get("virtual_sell_count", 0)) + 1
    stats["realized_pnl_krw"] = float(stats.get("realized_pnl_krw", 0.0)) + pnl_krw

    trade = PaperTrade(
        timestamp=now,
        market=market,
        side="VIRTUAL_SELL",
        entry_price=entry_price,
        exit_price=fill.price,
        qty=qty,
        pnl_krw=pnl_krw,
        pnl_pct=pnl_pct,
        fee_krw=entry_fee_krw + fill.fee_krw,
        reason_entry=str(position.get("reason_entry", "")),
        reason_exit=f"{reason_exit}:{fill.reason}",
        max_profit_pct=float(position.get("max_profit_pct", 0.0)),
        max_drawdown_pct=float(position.get("max_drawdown_pct", 0.0)),
        holding_seconds=now - entry_timestamp,
        expected_edge=float(features.get("continuation_score", 0.0)),
        slippage_estimate=abs(fill.price - entry_price) / entry_price * 100 if entry_price else 0,
        virtual_fill_result=fill.to_dict(),
    )

    del state["positions"][market]

    return trade


def update_position_stats(state: Dict[str, Any], market: str, price: float) -> None:
    if not has_position(state, market):
        return

    position = state["positions"][market]
    entry_price = float(position.get("entry_price", 0.0))

    if entry_price <= 0 or price <= 0:
        return

    peak_price = max(float(position.get("peak_price", entry_price)), price)
    trough_price = min(float(position.get("trough_price", entry_price)), price)

    max_profit_pct = ((peak_price - entry_price) / entry_price) * 100.0
    max_drawdown_pct = ((trough_price - entry_price) / entry_price) * 100.0

    position["peak_price"] = peak_price
    position["trough_price"] = trough_price
    position["max_profit_pct"] = max(float(position.get("max_profit_pct", 0.0)), max_profit_pct)
    position["max_drawdown_pct"] = min(float(position.get("max_drawdown_pct", 0.0)), max_drawdown_pct)


def get_reference_price(features: Dict[str, Any]) -> float:
    best_ask = float(features.get("best_ask", 0.0))
    last_trade_price = float(features.get("last_trade_price", 0.0))

    if best_ask > 0:
        return best_ask

    return last_trade_price


def get_exit_reference_price(features: Dict[str, Any]) -> float:
    best_bid = float(features.get("best_bid", 0.0))
    last_trade_price = float(features.get("last_trade_price", 0.0))

    if best_bid > 0:
        return best_bid

    return last_trade_price


def calc_entry_score(features: Dict[str, Any]) -> float:
    ofi_score = float(features.get("ofi_score", 0.0))
    sweep_score = float(features.get("sweep_score", 0.0))
    absorption_score = float(features.get("absorption_score", 0.0))
    continuation_score = float(features.get("continuation_score", 0.0))

    return round(
        (ofi_score * 0.30)
        + (sweep_score * 0.25)
        + (absorption_score * 0.20)
        + (continuation_score * 0.25),
        4,
    )


def calc_equity_krw(state: Dict[str, Any]) -> float:
    cash_krw = float(state.get("cash_krw", 0.0))
    positions = state.get("positions", {})

    equity = cash_krw

    for position in positions.values():
        amount_krw = float(position.get("amount_krw", 0.0))
        equity += amount_krw

    return equity


def has_position(state: Dict[str, Any], market: str) -> bool:
    positions = state.get("positions", {})
    return market in positions


def make_decision(
    market: str,
    action: str,
    reason: str,
    score: float,
    price: float,
    features: Dict[str, Any],
    extra: Dict[str, Any],
) -> PaperDecision:
    details = {
        "ofi_score": features.get("ofi_score"),
        "sweep_score": features.get("sweep_score"),
        "absorption_score": features.get("absorption_score"),
        "continuation_score": features.get("continuation_score"),
        "spread_pct": features.get("spread_pct"),
        "buy_trade_value_3s": features.get("buy_trade_value_3s"),
        "sell_trade_value_3s": features.get("sell_trade_value_3s"),
        "bid_ask_depth_ratio_5": features.get("bid_ask_depth_ratio_5"),
        "bid_depth_5_krw": features.get("bid_depth_5_krw"),
        "ask_depth_5_krw": features.get("ask_depth_5_krw"),
    }

    details.update(extra)

    fill_result = extra.pop("fill", {})
    diagnostic = extra.pop("diagnostic", {})

    return PaperDecision(
        timestamp=time.time(),
        market=market,
        action=action,
        reason=reason,
        score=score,
        price=price,
        expected_edge=float(features.get("continuation_score", 0.0)),
        slippage_estimate=abs(price - float(features.get("best_ask", price))) / price * 100 if price > 0 else 0.0,
        virtual_fill_result=fill_result,
        diagnostic=diagnostic,
        details=details,
    )