from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from .jsonl import read_json, write_json


@dataclass
class RuntimeState:
    mode: str = "paper"
    exchange: str = "upbit"
    market_type: str = "KRW"
    status: str = "initialized"
    last_updated: str = ""
    open_positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_prices: Dict[str, float] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)

        if not data["last_updated"]:
            data["last_updated"] = now_iso()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeState":
        return cls(
            mode=str(data.get("mode", "paper")),
            exchange=str(data.get("exchange", "upbit")),
            market_type=str(data.get("market_type", "KRW")),
            status=str(data.get("status", "initialized")),
            last_updated=str(data.get("last_updated", "")),
            open_positions=dict(data.get("open_positions", {})),
            last_prices=dict(data.get("last_prices", {})),
            risk=dict(data.get("risk", {})),
            stats=dict(data.get("stats", {})),
            messages=list(data.get("messages", [])),
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: str = "runtime/state.json") -> RuntimeState:
    data = read_json(path, default={})

    if not data:
        return RuntimeState(last_updated=now_iso())

    return RuntimeState.from_dict(data)


def save_state(
    state: RuntimeState,
    path: str = "runtime/state.json",
) -> None:
    state.last_updated = now_iso()
    write_json(path, state.to_dict())


def update_state(
    path: str,
    updates: Dict[str, Any],
) -> RuntimeState:
    state = load_state(path)
    data = state.to_dict()
    data.update(updates)

    updated_state = RuntimeState.from_dict(data)
    save_state(updated_state, path)

    return updated_state


def make_error_state(message: str) -> RuntimeState:
    return RuntimeState(
        status="error",
        last_updated=now_iso(),
        messages=[message],
    )