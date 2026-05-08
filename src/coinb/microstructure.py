from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .jsonl import read_jsonl, write_json


@dataclass
class MicrostructureFeatures:
    market: str
    timestamp: float

    last_trade_price: float
    best_bid: float
    best_ask: float
    spread_pct: float

    buy_trade_value_1s: float
    sell_trade_value_1s: float
    buy_trade_value_3s: float
    sell_trade_value_3s: float
    buy_trade_value_10s: float
    sell_trade_value_10s: float

    buy_sell_imbalance_1s: float
    buy_sell_imbalance_3s: float
    buy_sell_imbalance_10s: float

    trade_count_1s: int
    trade_count_3s: int
    trade_count_10s: int
    large_trade_count_3s: int

    bid_depth_1_krw: float
    ask_depth_1_krw: float
    bid_depth_5_krw: float
    ask_depth_5_krw: float
    bid_ask_depth_ratio_5: float

    ask_wall_change_pct: float
    bid_wall_change_pct: float

    price_change_1s_pct: float
    price_change_3s_pct: float
    price_change_10s_pct: float

    ofi_score: float
    sweep_score: float
    absorption_score: float
    continuation_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_microstructure_report(
    input_path: str = "logs/upbit_ws_events.jsonl",
    output_path: str = "reports/microstructure_snapshot.json",
) -> Dict[str, Any]:
    events = read_jsonl(input_path)
    features_by_market = build_latest_features_by_market(events)

    report = {
        "ok": True,
        "command": "microstructure",
        "exchange": "upbit",
        "market_type": "KRW",
        "source": input_path,
        "output_path": output_path,
        "market_count": len(features_by_market),
        "features": {
            market: features.to_dict()
            for market, features in features_by_market.items()
        },
    }

    write_json(output_path, report)
    return report


def build_latest_features_by_market(
    events: List[Dict[str, Any]],
) -> Dict[str, MicrostructureFeatures]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for event in events:
        market = str(event.get("market", ""))

        if not market.startswith("KRW-"):
            continue

        grouped.setdefault(market, []).append(event)

    result: Dict[str, MicrostructureFeatures] = {}

    for market, market_events in grouped.items():
        features = build_features_for_market(market, market_events)

        if features is not None:
            result[market] = features

    return result


def build_features_for_market(
    market: str,
    events: List[Dict[str, Any]],
) -> Optional[MicrostructureFeatures]:
    if not events:
        return None

    events = sorted(events, key=lambda row: _to_float(row.get("received_at", 0.0)))
    latest_ts = _to_float(events[-1].get("received_at", 0.0))

    trades = [
        event for event in events
        if _event_type(event) == "trade"
    ]

    orderbooks = [
        event for event in events
        if _event_type(event) == "orderbook"
    ]

    latest_trade = _latest_trade(trades)
    latest_orderbook = _latest_orderbook(orderbooks)

    if latest_trade is None or latest_orderbook is None:
        return None

    last_trade_price = _trade_price(latest_trade)
    best_bid, best_ask = _best_bid_ask(latest_orderbook)
    spread_pct = _spread_pct(best_bid, best_ask)

    buy_1s, sell_1s, count_1s, large_1s = _trade_values_in_window(trades, latest_ts, 1.0)
    buy_3s, sell_3s, count_3s, large_3s = _trade_values_in_window(trades, latest_ts, 3.0)
    buy_10s, sell_10s, count_10s, large_10s = _trade_values_in_window(trades, latest_ts, 10.0)

    bid_depth_1, ask_depth_1 = _depth_krw(latest_orderbook, levels=1)
    bid_depth_5, ask_depth_5 = _depth_krw(latest_orderbook, levels=5)

    bid_ask_ratio_5 = _safe_divide(bid_depth_5, ask_depth_5)

    first_orderbook = _first_orderbook_in_window(orderbooks, latest_ts, 10.0)
    ask_wall_change_pct, bid_wall_change_pct = _wall_change_pct(
        first_orderbook=first_orderbook,
        latest_orderbook=latest_orderbook,
        levels=5,
    )

    price_change_1s = _price_change_pct(trades, latest_ts, 1.0)
    price_change_3s = _price_change_pct(trades, latest_ts, 3.0)
    price_change_10s = _price_change_pct(trades, latest_ts, 10.0)

    imbalance_1s = _imbalance(buy_1s, sell_1s)
    imbalance_3s = _imbalance(buy_3s, sell_3s)
    imbalance_10s = _imbalance(buy_10s, sell_10s)

    ofi_score = calc_ofi_score(
        imbalance_3s=imbalance_3s,
        buy_value_3s=buy_3s,
        sell_value_3s=sell_3s,
        bid_ask_depth_ratio_5=bid_ask_ratio_5,
    )

    sweep_score = calc_sweep_score(
        price_change_1s_pct=price_change_1s,
        price_change_3s_pct=price_change_3s,
        buy_trade_value_1s=buy_1s,
        buy_trade_value_3s=buy_3s,
        ask_wall_change_pct=ask_wall_change_pct,
        spread_pct=spread_pct,
    )

    absorption_score = calc_absorption_score(
        sell_trade_value_3s=sell_3s,
        price_change_3s_pct=price_change_3s,
        bid_wall_change_pct=bid_wall_change_pct,
        bid_ask_depth_ratio_5=bid_ask_ratio_5,
    )

    continuation_score = calc_continuation_score(
        ofi_score=ofi_score,
        sweep_score=sweep_score,
        absorption_score=absorption_score,
        price_change_3s_pct=price_change_3s,
        spread_pct=spread_pct,
    )

    return MicrostructureFeatures(
        market=market,
        timestamp=latest_ts,
        last_trade_price=round(last_trade_price, 8),
        best_bid=round(best_bid, 8),
        best_ask=round(best_ask, 8),
        spread_pct=round(spread_pct, 6),

        buy_trade_value_1s=round(buy_1s, 2),
        sell_trade_value_1s=round(sell_1s, 2),
        buy_trade_value_3s=round(buy_3s, 2),
        sell_trade_value_3s=round(sell_3s, 2),
        buy_trade_value_10s=round(buy_10s, 2),
        sell_trade_value_10s=round(sell_10s, 2),

        buy_sell_imbalance_1s=round(imbalance_1s, 4),
        buy_sell_imbalance_3s=round(imbalance_3s, 4),
        buy_sell_imbalance_10s=round(imbalance_10s, 4),

        trade_count_1s=count_1s,
        trade_count_3s=count_3s,
        trade_count_10s=count_10s,
        large_trade_count_3s=large_3s,

        bid_depth_1_krw=round(bid_depth_1, 2),
        ask_depth_1_krw=round(ask_depth_1, 2),
        bid_depth_5_krw=round(bid_depth_5, 2),
        ask_depth_5_krw=round(ask_depth_5, 2),
        bid_ask_depth_ratio_5=round(bid_ask_ratio_5, 4),

        ask_wall_change_pct=round(ask_wall_change_pct, 4),
        bid_wall_change_pct=round(bid_wall_change_pct, 4),

        price_change_1s_pct=round(price_change_1s, 4),
        price_change_3s_pct=round(price_change_3s, 4),
        price_change_10s_pct=round(price_change_10s, 4),

        ofi_score=round(ofi_score, 2),
        sweep_score=round(sweep_score, 2),
        absorption_score=round(absorption_score, 2),
        continuation_score=round(continuation_score, 2),
    )


def calc_ofi_score(
    imbalance_3s: float,
    buy_value_3s: float,
    sell_value_3s: float,
    bid_ask_depth_ratio_5: float,
) -> float:
    score = 0.0

    score += _clamp((imbalance_3s - 1.0) * 30.0, 0.0, 45.0)
    score += _clamp(buy_value_3s / 10_000_000.0 * 10.0, 0.0, 30.0)
    score += _clamp((bid_ask_depth_ratio_5 - 1.0) * 20.0, 0.0, 25.0)

    if sell_value_3s > buy_value_3s:
        score *= 0.65

    return _clamp(score, 0.0, 100.0)


def calc_sweep_score(
    price_change_1s_pct: float,
    price_change_3s_pct: float,
    buy_trade_value_1s: float,
    buy_trade_value_3s: float,
    ask_wall_change_pct: float,
    spread_pct: float,
) -> float:
    score = 0.0

    score += _clamp(price_change_1s_pct * 25.0, 0.0, 25.0)
    score += _clamp(price_change_3s_pct * 15.0, 0.0, 25.0)
    score += _clamp(buy_trade_value_1s / 5_000_000.0 * 15.0, 0.0, 20.0)
    score += _clamp(buy_trade_value_3s / 20_000_000.0 * 15.0, 0.0, 20.0)

    if ask_wall_change_pct < 0:
        score += _clamp(abs(ask_wall_change_pct) * 0.5, 0.0, 15.0)

    if spread_pct > 0.25:
        score *= 0.7

    return _clamp(score, 0.0, 100.0)


def calc_absorption_score(
    sell_trade_value_3s: float,
    price_change_3s_pct: float,
    bid_wall_change_pct: float,
    bid_ask_depth_ratio_5: float,
) -> float:
    score = 0.0

    score += _clamp(sell_trade_value_3s / 10_000_000.0 * 20.0, 0.0, 40.0)

    if price_change_3s_pct >= -0.15:
        score += 25.0

    if bid_wall_change_pct >= 0:
        score += _clamp(bid_wall_change_pct * 0.5, 0.0, 20.0)

    score += _clamp((bid_ask_depth_ratio_5 - 1.0) * 15.0, 0.0, 15.0)

    return _clamp(score, 0.0, 100.0)


def calc_continuation_score(
    ofi_score: float,
    sweep_score: float,
    absorption_score: float,
    price_change_3s_pct: float,
    spread_pct: float,
) -> float:
    score = 0.0

    score += ofi_score * 0.35
    score += sweep_score * 0.35
    score += absorption_score * 0.15

    if price_change_3s_pct > 0:
        score += 10.0

    if spread_pct <= 0.15:
        score += 5.0
    elif spread_pct > 0.30:
        score -= 10.0

    return _clamp(score, 0.0, 100.0)


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get("event_type", "")).lower()


def _raw(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("raw", {})
    return raw if isinstance(raw, dict) else {}


def _latest_trade(trades: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return trades[-1] if trades else None


def _latest_orderbook(orderbooks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return orderbooks[-1] if orderbooks else None


def _first_orderbook_in_window(
    orderbooks: List[Dict[str, Any]],
    latest_ts: float,
    seconds: float,
) -> Optional[Dict[str, Any]]:
    window_start = latest_ts - seconds

    for event in orderbooks:
        if _to_float(event.get("received_at", 0.0)) >= window_start:
            return event

    return orderbooks[0] if orderbooks else None


def _trade_price(event: Dict[str, Any]) -> float:
    raw = _raw(event)
    return _to_float(raw.get("trade_price", raw.get("tp", 0.0)))


def _trade_volume(event: Dict[str, Any]) -> float:
    raw = _raw(event)
    return _to_float(raw.get("trade_volume", raw.get("tv", 0.0)))


def _trade_side(event: Dict[str, Any]) -> str:
    raw = _raw(event)
    return str(raw.get("ask_bid", raw.get("ab", ""))).upper()


def _trade_value_krw(event: Dict[str, Any]) -> float:
    return _trade_price(event) * _trade_volume(event)


def _trade_values_in_window(
    trades: List[Dict[str, Any]],
    latest_ts: float,
    seconds: float,
    large_trade_krw: float = 5_000_000.0,
) -> tuple[float, float, int, int]:
    window_start = latest_ts - seconds

    buy_value = 0.0
    sell_value = 0.0
    count = 0
    large_count = 0

    for event in trades:
        received_at = _to_float(event.get("received_at", 0.0))

        if received_at < window_start:
            continue

        value = _trade_value_krw(event)
        side = _trade_side(event)

        if side == "BID":
            buy_value += value
        elif side == "ASK":
            sell_value += value

        count += 1

        if value >= large_trade_krw:
            large_count += 1

    return buy_value, sell_value, count, large_count


def _orderbook_units(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = _raw(event)
    units = raw.get("orderbook_units", raw.get("obu", []))

    if not isinstance(units, list):
        return []

    return [
        unit for unit in units
        if isinstance(unit, dict)
    ]


def _best_bid_ask(event: Dict[str, Any]) -> tuple[float, float]:
    units = _orderbook_units(event)

    if not units:
        return 0.0, 0.0

    first = units[0]

    best_bid = _to_float(first.get("bid_price", first.get("bp", 0.0)))
    best_ask = _to_float(first.get("ask_price", first.get("ap", 0.0)))

    return best_bid, best_ask


def _depth_krw(event: Dict[str, Any], levels: int = 5) -> tuple[float, float]:
    units = _orderbook_units(event)[:levels]

    bid_depth = 0.0
    ask_depth = 0.0

    for unit in units:
        bid_price = _to_float(unit.get("bid_price", unit.get("bp", 0.0)))
        bid_size = _to_float(unit.get("bid_size", unit.get("bs", 0.0)))
        ask_price = _to_float(unit.get("ask_price", unit.get("ap", 0.0)))
        ask_size = _to_float(unit.get("ask_size", unit.get("as", 0.0)))

        bid_depth += bid_price * bid_size
        ask_depth += ask_price * ask_size

    return bid_depth, ask_depth


def _wall_change_pct(
    first_orderbook: Optional[Dict[str, Any]],
    latest_orderbook: Dict[str, Any],
    levels: int = 5,
) -> tuple[float, float]:
    if first_orderbook is None:
        return 0.0, 0.0

    first_bid, first_ask = _depth_krw(first_orderbook, levels=levels)
    latest_bid, latest_ask = _depth_krw(latest_orderbook, levels=levels)

    ask_change = _pct_change(latest_ask, first_ask)
    bid_change = _pct_change(latest_bid, first_bid)

    return ask_change, bid_change


def _price_change_pct(
    trades: List[Dict[str, Any]],
    latest_ts: float,
    seconds: float,
) -> float:
    if not trades:
        return 0.0

    window_start = latest_ts - seconds
    base_trade = None

    for event in trades:
        if _to_float(event.get("received_at", 0.0)) >= window_start:
            base_trade = event
            break

    if base_trade is None:
        base_trade = trades[0]

    latest_trade = trades[-1]

    return _pct_change(_trade_price(latest_trade), _trade_price(base_trade))


def _spread_pct(best_bid: float, best_ask: float) -> float:
    if best_bid <= 0 or best_ask <= 0:
        return 0.0

    mid = (best_bid + best_ask) / 2.0

    if mid <= 0:
        return 0.0

    return ((best_ask - best_bid) / mid) * 100.0


def _imbalance(buy_value: float, sell_value: float) -> float:
    if sell_value <= 0:
        return buy_value if buy_value > 0 else 0.0

    return buy_value / sell_value


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return numerator if numerator > 0 else 0.0

    return numerator / denominator


def _pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0

    return ((current - previous) / previous) * 100.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0