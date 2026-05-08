from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent

LF_EXTENSIONS = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".csv",
}

CRLF_EXTENSIONS = {
    ".bat",
    ".cmd",
}


def should_skip(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}

    return (
        ".git" in parts
        or ".vs" in parts
        or "__pycache__" in parts
    )


def normalize_file(path: Path) -> bool:
    ext = path.suffix.lower()

    if ext not in LF_EXTENSIONS and ext not in CRLF_EXTENSIONS:
        return False

    if should_skip(path):
        return False

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    if ext in CRLF_EXTENSIONS:
        text = text.replace("\n", "\r\n")

    path.write_text(text, encoding="utf-8", newline="")
    return True


def remove_cache_files() -> int:
    count = 0

    for cache_dir in ROOT.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
            count += 1

    for pyc_file in ROOT.rglob("*.pyc"):
        pyc_file.unlink(missing_ok=True)
        count += 1

    return count


def main() -> None:
    normalized_count = 0

    for path in ROOT.rglob("*"):
        if path.is_file() and normalize_file(path):
            normalized_count += 1

    removed_count = remove_cache_files()

    print("========================================")
    print("coinB line ending normalization")
    print("========================================")
    print(f"normalized files: {normalized_count}")
    print(f"removed cache items: {removed_count}")
    print("[OK] done")


if __name__ == "__main__":
    main()