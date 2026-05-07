from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def ensure_parent(path: str | Path) -> Path:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def append_jsonl(path: str | Path, row: Dict[str, Any]) -> None:
    file_path = ensure_parent(path)

    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False))
        file.write("\n")


def write_json(path: str | Path, data: Dict[str, Any]) -> None:
    file_path = ensure_parent(path)

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def read_json(path: str | Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        return default or {}

    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    file_path = Path(path)

    if not file_path.exists():
        return []

    rows: List[Dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue

            rows.append(json.loads(stripped))

    return rows


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    file_path = ensure_parent(path)

    with file_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False))
            file.write("\n")