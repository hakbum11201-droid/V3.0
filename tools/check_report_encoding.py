import os
import argparse
from pathlib import Path

def check_and_fix_encoding(root_dir: str, fix: bool):
    """
    reports 디렉토리 내의 txt 파일 인코딩을 검사하고 필요 시 utf-8-sig로 변환합니다.
    """
    root = Path(root_dir)
    if not root.exists():
        print(f"Directory not found: {root_dir}")
        return

    txt_files = list(root.rglob("*.txt"))
    print(f"Found {len(txt_files)} text files in {root_dir}")

    for file_path in txt_files:
        try:
            with open(file_path, "rb") as f:
                raw = f.read(3)
                has_bom = (raw == b'\xef\xbb\xbf')

            if has_bom:
                print(f"[OK] {file_path.relative_to(root)} (UTF-8 BOM detected)")
            else:
                if fix:
                    print(f"[FIXING] {file_path.relative_to(root)} (Adding BOM...)")
                    # UTF-8로 읽어서 UTF-8-SIG로 저장
                    content = file_path.read_text(encoding="utf-8")
                    file_path.write_text(content, encoding="utf-8-sig")
                else:
                    print(f"[WARN] {file_path.relative_to(root)} (No BOM detected)")

        except Exception as e:
            print(f"[ERROR] Failed to process {file_path}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check and fix report encoding (UTF-8-SIG)")
    parser.add_argument("--root", default="reports", help="Root directory to scan")
    parser.add_argument("--fix", action="store_true", help="Fix encoding by adding UTF-8 BOM")
    args = parser.parse_args()

    check_and_fix_encoding(args.root, args.fix)
