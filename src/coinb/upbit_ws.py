from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

from .jsonl import append_jsonl


UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


@dataclass
class UpbitWsEvent:
    received_at: float
    event_type: str
    market: str
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_market(market: str) -> str:
    market = market.strip().upper()

    if not market.startswith("KRW-"):
        raise ValueError(f"only Upbit KRW market is allowed: {market}")

    return market


def normalize_markets(markets: Iterable[str]) -> List[str]:
    normalized = [normalize_market(market) for market in markets]

    if not normalized:
        raise ValueError("markets must not be empty")

    return normalized


def build_subscription_message(
    markets: Iterable[str],
    include_trade: bool = True,
    include_orderbook: bool = True,
) -> List[Dict[str, Any]]:
    codes = normalize_markets(markets)

    message: List[Dict[str, Any]] = [
        {
            "ticket": f"coinB-{uuid.uuid4()}",
        }
    ]

    if include_trade:
        message.append(
            {
                "type": "trade",
                "codes": codes,
                "is_only_realtime": True,
            }
        )

    if include_orderbook:
        message.append(
            {
                "type": "orderbook",
                "codes": codes,
                "is_only_realtime": True,
            }
        )

    message.append(
        {
            "format": "DEFAULT",
        }
    )

    return message


def parse_ws_payload(payload: bytes | str) -> Dict[str, Any]:
    if isinstance(payload, bytes):
        text = payload.decode("utf-8")
    else:
        text = payload

    data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError("unexpected websocket payload format")

    return data


def get_event_type(data: Dict[str, Any]) -> str:
    return str(data.get("type", data.get("ty", "unknown")))


def get_market(data: Dict[str, Any]) -> str:
    return str(data.get("code", data.get("cd", "")))


def collect_upbit_ws_events(
    markets: Iterable[str],
    output_path: str = "logs/upbit_ws_events.jsonl",
    seconds: int = 30,
    include_trade: bool = True,
    include_orderbook: bool = True,
) -> Dict[str, Any]:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError(
            "websocket-client is not installed. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc

    if seconds <= 0:
        raise ValueError("seconds must be positive")

    normalized_markets = normalize_markets(markets)
    subscription_message = build_subscription_message(
        markets=normalized_markets,
        include_trade=include_trade,
        include_orderbook=include_orderbook,
    )

    started_at = time.time()
    received_count = 0
    type_counts: Dict[str, int] = {}

    ws = websocket.create_connection(
        UPBIT_WS_URL,
        timeout=10,
    )

    try:
        ws.send(json.dumps(subscription_message))

        while True:
            now = time.time()

            if now - started_at >= seconds:
                break

            payload = ws.recv()
            data = parse_ws_payload(payload)

            event_type = get_event_type(data)
            market = get_market(data)

            event = UpbitWsEvent(
                received_at=now,
                event_type=event_type,
                market=market,
                raw=data,
            )

            append_jsonl(output_path, event.to_dict())

            received_count += 1
            type_counts[event_type] = type_counts.get(event_type, 0) + 1

    finally:
        ws.close()

    return {
        "ok": True,
        "exchange": "upbit",
        "market_type": "KRW",
        "markets": normalized_markets,
        "seconds": seconds,
        "received_count": received_count,
        "type_counts": type_counts,
        "output_path": output_path,
    }


def print_collection_summary(result: Dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))