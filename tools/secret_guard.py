import os
import sys
import re

# 스캔 제외 폴더
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "logs",
    "reports",
    "runtime",
    "data",
    "tools"  # 도구 폴더 제외 (자기 자신 포함)
}

# 허용되는 예시 파일
EXAMPLE_FILES = {
    ".env.example",
    ".env.account.example",
    ".env.live.example"
}

# 존재 시 차단할 파일
FORBIDDEN_FILES = {
    ".env",
    ".env.account",
    ".env.live",
    "secrets.json",
    "credentials.json"
}

# 차단할 문자열 패턴 (실제값이 있는 경우)
# 예: UPBIT_ACCESS_KEY=ABCD (차단)
# 예: UPBIT_ACCESS_KEY= (허용)
FORBIDDEN_PATTERNS = [
    r"UPBIT_ACCESS_KEY=\S+",
    r"UPBIT_SECRET_KEY=\S+",
    r"UPBIT_ACCOUNT_ACCESS_KEY=\S+",
    r"UPBIT_ACCOUNT_SECRET_KEY=\S+",
    r"UPBIT_LIVE_ACCESS_KEY=\S+",
    r"UPBIT_LIVE_SECRET_KEY=\S+",
    r"Authorization:\s*\S+",
    r"Bearer\s+\S+",
    r"JWT\s+\S+"
]

def scan_files(root_dir):
    violations = []
    
    for root, dirs, files in os.walk(root_dir):
        # 제외 폴더 건너뛰기
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_dir)
            
            # 1. 금지 파일 존재 여부 체크
            if file in FORBIDDEN_FILES:
                violations.append(f"[FORBIDDEN FILE] {rel_path}")
                continue
                
            # 예시 파일은 내용 검사에서 특정 조건부 허용
            is_example = file in EXAMPLE_FILES
            
            # 2. 파일 내용 패턴 체크
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for pattern in FORBIDDEN_PATTERNS:
                        matches = re.findall(pattern, content)
                        if matches:
                            # 예시 파일이고 값이 비어있는 패턴이면 제외 (이미 re에서 \S+로 걸러지지만 명시적 확인)
                            violations.append(f"[PATTERN MATCH] {rel_path}: Found {matches}")
            except Exception as e:
                # 읽기 실패는 일단 넘어감 (바이너리 등)
                pass
                
    return violations

def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Scanning root: {root}")
    
    violations = scan_files(root)
    
    if violations:
        print("\n[FAILED] Secret Guard detected potential leaks:")
        for v in violations:
            print(f"  - {v}")
        print("\n[ACTION] Please remove actual keys/files before committing.")
        sys.exit(1)
    else:
        print("\n[OK] secret guard passed")
        sys.exit(0)

if __name__ == "__main__":
    main()
