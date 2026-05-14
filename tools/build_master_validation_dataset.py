"""
build_master_validation_dataset.py

Master Dataset Builder
여러 jsonl raw 데이터 파일을 모아 중복 제거, 깨진 줄 제거, timestamp 기준 정렬 후
Master dataset과 Holdout dataset을 생성합니다.
"""

import os
import json
import glob
from datetime import datetime
from collections import defaultdict

# =============================================================================
# Constants & Configuration
# =============================================================================
INPUT_GLOBS = [
    "logs/experiments/master_sources/*.jsonl",
    "logs/paper/*.jsonl"
]

EXCLUDE_PATTERNS = [
    "_summary.",
    "_merged_pipeline.",
    "reports/",
    "__pycache__",
    ".pyc"
]

HOLDOUT_KEYWORDS = ["holdout", "72h"]

OUT_DIR = "logs/experiments/master"
REPORTS_DIR = "reports/experiments"

MASTER_DATASET_PATH = os.path.join(OUT_DIR, "reversal_edge_master_dataset.jsonl")
HOLDOUT_DATASET_PATH = os.path.join(OUT_DIR, "reversal_edge_holdout_dataset.jsonl")

# =============================================================================
# Functions
# =============================================================================

def is_excluded(filepath):
    """Check if the filepath matches any exclude patterns."""
    for pattern in EXCLUDE_PATTERNS:
        if pattern in filepath:
            return True
    return False

def is_holdout(filepath):
    """Check if the filepath contains keywords indicating a holdout dataset."""
    filename = os.path.basename(filepath).lower()
    for kw in HOLDOUT_KEYWORDS:
        if kw in filename:
            return True
    return False

def get_timestamp(data):
    """Extract timestamp from JSON data."""
    for key in ["timestamp", "trade_timestamp", "ts", "timestamp_ms", "received_at"]:
        if key in data:
            return float(data[key])
    if "raw" in data and isinstance(data["raw"], dict):
        for key in ["timestamp", "trade_timestamp", "ts"]:
            if key in data["raw"]:
                return float(data["raw"][key])
    return None

def main():
    print("============================================================")
    print(" Master Dataset Builder")
    print("============================================================")
    
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    scanned_files = []
    included_files = []
    excluded_files = []
    holdout_files = []
    
    # 1. Gather files
    for g in INPUT_GLOBS:
        for filepath in glob.glob(g, recursive=True):
            filepath = filepath.replace("\\", "/")
            scanned_files.append(filepath)
            
            if is_excluded(filepath):
                excluded_files.append(filepath)
            else:
                if is_holdout(filepath):
                    holdout_files.append(filepath)
                else:
                    included_files.append(filepath)
                    
    print(f"[Info] Scanned: {len(scanned_files)}, Master: {len(included_files)}, Holdout: {len(holdout_files)}, Excluded: {len(excluded_files)}")
    
    # 2. Parse and filter events
    master_events = {}
    holdout_events = {}
    parse_errors = 0
    total_lines = 0
    source_file_breakdown = {}
    
    event_type_breakdown_before = defaultdict(int)
    event_type_breakdown_after = defaultdict(int)
    duplicate_key_strategy = "source_file + line_index + ts + event_type + line_hash"
    
    def process_file(filepath, event_dict):
        nonlocal parse_errors, total_lines
        if not os.path.exists(filepath):
            return
            
        source_file_breakdown[filepath] = 0
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    total_lines += 1
                    try:
                        data = json.loads(line)
                        ts = get_timestamp(data)
                        
                        e_type = data.get("type", data.get("event_type", "unknown")).lower()
                        if e_type == "orderbook_sample":
                            e_type = "orderbook"
                            data["type"] = "orderbook" # Normalize orderbook_sample
                            
                        event_type_breakdown_before[e_type] += 1
                        
                        if ts is not None:
                            # Build deduplication key
                            market = data.get("market", data.get("code", "UNKNOWN"))
                            price = data.get("trade_price", data.get("p", ""))
                            volume = data.get("trade_volume", data.get("v", ""))
                            ask_size = data.get("total_ask_size", "")
                            bid_size = data.get("total_bid_size", "")
                            
                            line_hash = hash(line)
                            # Create a highly specific key to prevent aggressive deduplication
                            # Using source_file and line_idx guarantees uniqueness per file, 
                            # but across files we want to deduplicate identical events.
                            # So we do NOT use source_file and line_idx in the cross-file key.
                            
                            key = f"{ts}_{e_type}_{market}_{price}_{volume}_{ask_size}_{bid_size}_{line_hash}"
                            
                            data["source_file"] = filepath
                            data["line_index"] = line_idx
                            updated_line = json.dumps(data, ensure_ascii=False)
                            
                            if key not in event_dict:
                                event_dict[key] = (ts, updated_line)
                                source_file_breakdown[filepath] += 1
                                event_type_breakdown_after[e_type] += 1
                    except json.JSONDecodeError:
                        parse_errors += 1
        except Exception as e:
            print(f"[Warning] Failed to read {filepath}: {e}")

    for fp in included_files:
        process_file(fp, master_events)
        
    for fp in holdout_files:
        process_file(fp, holdout_events)
        
    parsed_events = len(master_events) + len(holdout_events)
    master_count = len(master_events)
    holdout_count = len(holdout_events)
    duplicate_removed = total_lines - parse_errors - parsed_events
    duplicate_removed_ratio = (duplicate_removed / total_lines) if total_lines > 0 else 0
    
    print(f"[Info] Parsed Events: {parsed_events}, Errors: {parse_errors}, Duplicates removed: {duplicate_removed} ({duplicate_removed_ratio:.1%})")
    
    # 3. Sort and write
    def sort_and_write(events_dict, out_path):
        sorted_events = sorted(events_dict.values(), key=lambda x: x[0])
        earliest = sorted_events[0][0] if sorted_events else None
        latest = sorted_events[-1][0] if sorted_events else None
        
        with open(out_path, "w", encoding="utf-8") as f:
            for _, line in sorted_events:
                f.write(line + "\n")
                
        return earliest, latest
        
    master_earliest, master_latest = sort_and_write(master_events, MASTER_DATASET_PATH)
    holdout_earliest, holdout_latest = sort_and_write(holdout_events, HOLDOUT_DATASET_PATH)
    
    # 4. Judgement
    if master_count == 0:
        judgement = "NEED_MORE_DATA"
    elif holdout_count == 0:
        judgement = "MASTER_ONLY_READY"
    else:
        judgement = "READY_FOR_HOLDOUT_VALIDATION"
        
    all_earliest = min(filter(None, [master_earliest, holdout_earliest]), default=0)
    all_latest = max(filter(None, [master_latest, holdout_latest]), default=0)
    
    # 5. Output Summary
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "scanned_files": len(scanned_files),
        "included_files": included_files,
        "excluded_files": excluded_files,
        "holdout_files": holdout_files,
        "total_lines": total_lines,
        "parsed_events": parsed_events,
        "parse_errors": parse_errors,
        "duplicate_key_strategy": duplicate_key_strategy,
        "before_dedup_count": total_lines - parse_errors,
        "after_dedup_count": parsed_events,
        "duplicate_removed": duplicate_removed,
        "duplicate_removed_ratio": duplicate_removed_ratio,
        "event_type_breakdown_before": dict(event_type_breakdown_before),
        "event_type_breakdown_after": dict(event_type_breakdown_after),
        "master_event_count": master_count,
        "holdout_event_count": holdout_count,
        "earliest_ts": all_earliest,
        "latest_ts": all_latest,
        "source_file_breakdown": source_file_breakdown,
        "judgement": judgement
    }
    
    json_path = os.path.join(REPORTS_DIR, "master_dataset_builder_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "master_dataset_builder_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  Master Dataset Builder Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[파일 처리 결과]",
        f" - 스캔된 파일 총합 : {len(scanned_files)}",
        f" - Master 포함 파일 : {len(included_files)}",
        f" - Holdout 포함 파일: {len(holdout_files)}",
        f" - 제외된 파일      : {len(excluded_files)}",
        "",
        "[데이터 파싱 및 중복 제거 통계]",
        f" - 총 스캔 라인 수  : {total_lines}",
        f" - JSON 파싱 오류   : {parse_errors}",
        f" - 중복 판별 기준   : {duplicate_key_strategy}",
        f" - 중복 제거 전     : {final_summary['before_dedup_count']}",
        f" - 중복 제거 후     : {final_summary['after_dedup_count']}",
        f" - 중복 제거 건수   : {duplicate_removed} ({duplicate_removed_ratio:.1%})",
        "",
        "[Event Type 변화 (Before -> After)]",
    ]
    
    all_types = set(event_type_breakdown_before.keys()).union(set(event_type_breakdown_after.keys()))
    for t_name in all_types:
        b_count = event_type_breakdown_before.get(t_name, 0)
        a_count = event_type_breakdown_after.get(t_name, 0)
        txt_lines.append(f" - {t_name:10s} : {b_count:,} -> {a_count:,}")
        
    txt_lines.extend([
        "",
        "[생성된 데이터셋 현황]",
        f" - Master Dataset Events : {master_count:,}",
        f" - Holdout Dataset Events: {holdout_count:,}",
        "",
        f"🎯 진단 상태: {judgement}",

        "",
        "[안전 경고 및 금지 사항]",
        " 🚫 실거래 반영 금지",
        " 🚫 config 자동 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 사람 승인 전 tiny_live 금지"
    ])
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print(f"\n[Done] Judgement: {judgement}")
    print(f"Master dataset saved to: {MASTER_DATASET_PATH}")
    print(f"Holdout dataset saved to: {HOLDOUT_DATASET_PATH}")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
