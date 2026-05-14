"""
inspect_candidate_schema.py

Candidate 파일의 전체 구조와 파라미터 계층을 심층 탐색하여 
숨겨진 threshold, score, cost, tp, sl 설정값들을 찾아냅니다.
"""

import os
import json
from datetime import datetime

CANDIDATE_JSON = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"
REPORTS_DIR = "reports/experiments"

def recursive_find(d, keywords, path=""):
    found = {}
    if isinstance(d, dict):
        for k, v in d.items():
            current_path = f"{path}.{k}" if path else k
            if any(kw in k.lower() for kw in keywords):
                found[current_path] = v
            if isinstance(v, (dict, list)):
                found.update(recursive_find(v, keywords, current_path))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            current_path = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                found.update(recursive_find(v, keywords, current_path))
    return found

def get_top_level_keys(d):
    if isinstance(d, dict):
        return list(d.keys())
    return []

def main():
    print("============================================================")
    print(" Candidate Schema Inspection")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    if not os.path.exists(CANDIDATE_JSON):
        print(f"[Error] Candidate file not found: {CANDIDATE_JSON}")
        return
        
    with open(CANDIDATE_JSON, "r", encoding="utf-8") as f:
        candidate = json.load(f)
        
    top_keys = get_top_level_keys(candidate)
    keywords = ["threshold", "score", "cost", "tp", "sl", "timeout", "mode", "market"]
    found_keys = recursive_find(candidate, keywords)
    
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "candidate_file": CANDIDATE_JSON,
        "top_level_keys": top_keys,
        "found_parameters": found_keys
    }
    
    json_path = os.path.join(REPORTS_DIR, "candidate_schema_inspection_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "candidate_schema_inspection_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  Candidate Schema Inspection Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        f"대상 파일: {CANDIDATE_JSON}",
        "",
        "[Top Level Keys]",
    ]
    
    for k in top_keys:
        txt_lines.append(f" - {k}")
        
    txt_lines.extend([
        "",
        "[심층 탐색된 파라미터 (keyword match)]",
    ])
    
    for k, v in found_keys.items():
        txt_lines.append(f" - {k} : {v}")
        
    txt_lines.extend([
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 원본 코드 및 설정 무단 변경 금지",
        " 🚫 실거래 기능 추가 금지",
        "------------------------------------------------------------"
    ])
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print("\n[Done] Inspection complete.")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
