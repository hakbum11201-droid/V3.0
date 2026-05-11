import json
import os
from pathlib import Path

def write_text_report(path: str, text: str):
    """
    텍스트 리포트를 Windows 친화적인 UTF-8-SIG 인코딩으로 저장합니다.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Windows PowerShell/CMD에서의 한글 깨짐 방지를 위해 utf-8-sig 사용
    # 줄바꿈은 Windows 표준인 \r\n 권장
    content = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        f.write(content)

def write_json_report(path: str, data: dict):
    """
    JSON 데이터를 UTF-8 인코딩으로 저장합니다. (기존 데이터 구조 유지)
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def read_json_report(path: str) -> dict:
    """
    JSON 데이터를 읽어옵니다.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
