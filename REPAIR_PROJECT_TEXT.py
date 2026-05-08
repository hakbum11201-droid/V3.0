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

LF_FILENAMES = {
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
}

CRLF_EXTENSIONS = {
    ".bat",
    ".cmd",
}

SKIP_DIRS = {
    ".git",
    ".vs",
    ".vscode",
    ".idea",
    ".venv",
    "venv",
    "env",
    "__pycache__",
}

EDITORCONFIG_TEXT = """root = true

[*]
charset = utf-8
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
end_of_line = lf
indent_style = space
indent_size = 4

[*.json]
end_of_line = lf
indent_style = space
indent_size = 2

[*.md]
end_of_line = lf
trim_trailing_whitespace = false

[*.txt]
end_of_line = lf

[*.csv]
end_of_line = lf

[*.bat]
end_of_line = crlf

[*.cmd]
end_of_line = crlf
"""

GITATTRIBUTES_TEXT = """* text=auto

*.py text eol=lf
*.json text eol=lf
*.md text eol=lf
*.txt text eol=lf
*.csv text eol=lf
*.gitignore text eol=lf
*.gitattributes text eol=lf
*.editorconfig text eol=lf

*.bat text eol=crlf
*.cmd text eol=crlf
"""

GITIGNORE_TEXT = """# Python cache
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
.venv/
venv/
env/

# IDE / editor
.vs/
.vscode/
.idea/

# OS files
.DS_Store
Thumbs.db

# Runtime outputs
logs/*.jsonl
reports/*.json
runtime/*.json

# Keep folder placeholders
!logs/.gitkeep
!reports/.gitkeep
!runtime/.gitkeep

# Local secrets / keys
.env
.env.*
*.key
*.pem
secrets/
config/secrets.json

# Temporary files
*.tmp
*.bak
*.log

# Source folders should stay tracked
!src/
!config/
!docs/
!tests/
"""


def should_skip(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    return any(skip in lowered_parts for skip in SKIP_DIRS)


def target_line_ending(path: Path) -> str | None:
    name = path.name.lower()
    ext = path.suffix.lower()

    if name in LF_FILENAMES:
        return "lf"

    if ext in LF_EXTENSIONS:
        return "lf"

    if ext in CRLF_EXTENSIONS:
        return "crlf"

    return None


def normalize_text(text: str, line_ending: str) -> str:
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    if line_ending == "crlf":
        text = text.replace("\n", "\r\n")

    return text


def write_fixed_file(path: Path, text: str, line_ending: str) -> None:
    normalized = normalize_text(text, line_ending)
    path.write_text(normalized, encoding="utf-8", newline="")


def normalize_file(path: Path) -> bool:
    if should_skip(path):
        return False

    line_ending = target_line_ending(path)

    if line_ending is None:
        return False

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return False

    write_fixed_file(path, text, line_ending)
    return True


def remove_generated_outputs() -> int:
    count = 0

    generated_patterns = [
        "logs/*.jsonl",
        "reports/*.json",
        "runtime/*.json",
    ]

    for pattern in generated_patterns:
        for path in ROOT.glob(pattern):
            if path.is_file() and path.name != ".gitkeep":
                path.unlink()
                count += 1

    return count


def remove_python_cache() -> int:
    count = 0

    for cache_dir in ROOT.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
            count += 1

    for pyc_file in ROOT.rglob("*.pyc"):
        if pyc_file.is_file():
            pyc_file.unlink(missing_ok=True)
            count += 1

    return count


def has_cr_only(data: bytes) -> bool:
    for i, byte in enumerate(data):
        if byte == 13:
            next_byte = data[i + 1] if i + 1 < len(data) else None
            if next_byte != 10:
                return True

    return False


def verify_file(path: Path) -> dict:
    data = path.read_bytes()

    return {
        "path": str(path.relative_to(ROOT)),
        "lf": data.count(b"\n"),
        "cr": data.count(b"\r"),
        "cr_only": has_cr_only(data),
    }


def main() -> None:
    print("========================================")
    print("coinB project text repair")
    print("========================================")

    write_fixed_file(ROOT / ".editorconfig", EDITORCONFIG_TEXT, "lf")
    write_fixed_file(ROOT / ".gitattributes", GITATTRIBUTES_TEXT, "lf")
    write_fixed_file(ROOT / ".gitignore", GITIGNORE_TEXT, "lf")

    normalized_count = 0

    for path in ROOT.rglob("*"):
        if path.is_file() and normalize_file(path):
            normalized_count += 1

    removed_outputs = remove_generated_outputs()
    removed_cache = remove_python_cache()

    print(f"normalized files: {normalized_count}")
    print(f"removed generated output files: {removed_outputs}")
    print(f"removed python cache items: {removed_cache}")

    important_files = [
        ROOT / ".editorconfig",
        ROOT / ".gitattributes",
        ROOT / ".gitignore",
        ROOT / "config" / "config.json",
        ROOT / "START_COINB.bat",
        ROOT / "src" / "coinb" / "execution_model.py",
        ROOT / "src" / "coinb" / "orderflow_paper.py",
        ROOT / "tests" / "test_execution_model.py",
    ]

    print()
    print("verification:")
    failed = False

    for path in important_files:
        if not path.exists():
            print(f"[MISS] {path.relative_to(ROOT)}")
            failed = True
            continue

        result = verify_file(path)
        status = "OK" if not result["cr_only"] else "FAIL"

        print(
            f"[{status}] {result['path']} "
            f"LF={result['lf']} CR={result['cr']} CR_ONLY={result['cr_only']}"
        )

        if result["cr_only"]:
            failed = True

    if failed:
        print()
        print("[FAIL] repair completed, but verification failed.")
        raise SystemExit(1)

    print()
    print("[OK] repair completed.")


if __name__ == "__main__":
    main()
