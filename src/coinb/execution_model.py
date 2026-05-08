from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .market_rules import calc_fee_krw


@dataclass
class FillResult:
    ok: bool
    side: str
    market: str
    reason: str
    requested_krw: float
    filled_krw: float
    price: float
    qty: float
    fee_krw: float
    depth_krw: float
    liquidity_multiple: float
    extra_slippage_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def simulate_virtual_buy_fill(
    market: str,
    features: Dict[str, Any],
    requested_krw: float,
    fee_rate: float,
    min_order_krw: float,
    max_depth_take_ratio: float,
    min_liquidity_multiple: float,
    extra_slippage_pct: float,
) -> FillResult:
    best_ask = _to_float(features.get("best_ask", 0.0))
    last_trade_price = _to_float(features.get("last_trade_price", 0.0))
    ask_depth_5_krw = _to_float(features.get("ask_depth_5_krw", 0.0))

    base_price = best_ask if best_ask > 0 else last_trade_price
    price = base_price * (1.0 + (extra_slippage_pct / 100.0)) if base_price > 0 else 0.0

    if requested_krw < min_order_krw:
        return _failed_fill(
            side="VIRTUAL_BUY",
            market=market,
            reason="requested_amount_below_min_order",
            requested_krw=requested_krw,
            price=price,
            depth_krw=ask_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    if price <= 0:
        return _failed_fill(
            side="VIRTUAL_BUY",
            market=market,
            reason="invalid_buy_price",
            requested_krw=requested_krw,
            price=price,
            depth_krw=ask_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    if ask_depth_5_krw <= 0:
        return _failed_fill(
            side="VIRTUAL_BUY",
            market=market,
            reason="ask_depth_missing",
            requested_krw=requested_krw,
            price=price,
            depth_krw=ask_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    required_depth = requested_krw * min_liquidity_multiple

    if ask_depth_5_krw < required_depth:
        return _failed_fill(
            side="VIRTUAL_BUY",
            market=market,
            reason="ask_depth_too_thin",
            requested_krw=requested_krw,
            price=price,
            depth_krw=ask_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    max_fill_krw = ask_depth_5_krw * max_depth_take_ratio
    filled_krw = min(requested_krw, max_fill_krw)

    if filled_krw < min_order_krw:
        return _failed_fill(
            side="VIRTUAL_BUY",
            market=market,
            reason="fillable_amount_below_min_order",
            requested_krw=requested_krw,
            price=price,
            depth_krw=ask_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    fee_krw = calc_fee_krw(filled_krw, fee_rate)
    net_krw = max(0.0, filled_krw - fee_krw)
    qty = net_krw / price if price > 0 else 0.0

    return FillResult(
        ok=True,
        side="VIRTUAL_BUY",
        market=market,
        reason="filled_by_ask_depth",
        requested_krw=requested_krw,
        filled_krw=filled_krw,
        price=price,
        qty=qty,
        fee_krw=fee_krw,
        depth_krw=ask_depth_5_krw,
        liquidity_multiple=_safe_divide(ask_depth_5_krw, requested_krw),
        extra_slippage_pct=extra_slippage_pct,
    )


def simulate_virtual_sell_fill(
    market: str,
    features: Dict[str, Any],
    qty: float,
    entry_price: float,
    fee_rate: float,
    max_depth_take_ratio: float,
    min_liquidity_multiple: float,
    extra_slippage_pct: float,
    allow_forced_exit_on_low_liquidity: bool,
) -> FillResult:
    best_bid = _to_float(features.get("best_bid", 0.0))
    last_trade_price = _to_float(features.get("last_trade_price", 0.0))
    bid_depth_5_krw = _to_float(features.get("bid_depth_5_krw", 0.0))

    base_price = best_bid if best_bid > 0 else last_trade_price
    price = base_price * (1.0 - (extra_slippage_pct / 100.0)) if base_price > 0 else 0.0
    requested_krw = qty * price if price > 0 else qty * entry_price

    if qty <= 0:
        return _failed_fill(
            side="VIRTUAL_SELL",
            market=market,
            reason="invalid_qty",
            requested_krw=requested_krw,
            price=price,
            depth_krw=bid_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    if price <= 0:
        return _failed_fill(
            side="VIRTUAL_SELL",
            market=market,
            reason="invalid_sell_price",
            requested_krw=requested_krw,
            price=price,
            depth_krw=bid_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    required_depth = requested_krw * min_liquidity_multiple
    low_liquidity = bid_depth_5_krw > 0 and bid_depth_5_krw < required_depth

    if low_liquidity and not allow_forced_exit_on_low_liquidity:
        return _failed_fill(
            side="VIRTUAL_SELL",
            market=market,
            reason="bid_depth_too_thin",
            requested_krw=requested_krw,
            price=price,
            depth_krw=bid_depth_5_krw,
            extra_slippage_pct=extra_slippage_pct,
        )

    if low_liquidity:
        price = base_price * (1.0 - ((extra_slippage_pct * 2.0) / 100.0))

    gross_exit_krw = price * qty
    fee_krw = calc_fee_krw(gross_exit_krw, fee_rate)

    return FillResult(
        ok=True,
        side="VIRTUAL_SELL",
        market=market,
        reason="forced_exit_low_liquidity" if low_liquidity else "filled_by_bid_depth",
        requested_krw=requested_krw,
        filled_krw=gross_exit_krw,
        price=price,
        qty=qty,
        fee_krw=fee_krw,
        depth_krw=bid_depth_5_krw,
        liquidity_multiple=_safe_divide(bid_depth_5_krw, requested_krw),
        extra_slippage_pct=extra_slippage_pct * 2.0 if low_liquidity else extra_slippage_pct,
    )


def _failed_fill(
    side: str,
    market: str,
    reason: str,
    requested_krw: float,
    price: float,
    depth_krw: float,
    extra_slippage_pct: float,
) -> FillResult:
    return FillResult(
        ok=False,
        side=side,
        market=market,
        reason=reason,
        requested_krw=requested_krw,
        filled_krw=0.0,
        price=price,
        qty=0.0,
        fee_krw=0.0,
        depth_krw=depth_krw,
        liquidity_multiple=_safe_divide(depth_krw, requested_krw),
        extra_slippage_pct=extra_slippage_pct,
    )


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0

    return numerator / denominator


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0