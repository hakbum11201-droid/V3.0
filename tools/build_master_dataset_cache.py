import sqlite3
import json
import os
import sys
import time
import argparse
from datetime import datetime
from collections import defaultdict

# Paths
INPUT_JSONL = "logs/experiments/master/reversal_edge_master_dataset.jsonl"
OUTPUT_SQLITE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
REPORTS_DIR = "reports/experiments"
JSON_REPORT = os.path.join(REPORTS_DIR, "master_dataset_cache_latest.json")
TXT_REPORT = os.path.join(REPORTS_DIR, "master_dataset_cache_latest.txt")

BATCH_SIZE = 10000

def get_timestamp(data):
    for key in ["timestamp", "trade_timestamp", "ts", "timestamp_ms", "received_at"]:
        if key in data:
            return float(data[key])
    if "raw" in data and isinstance(data["raw"], dict):
        for key in ["timestamp", "trade_timestamp", "ts"]:
            if key in data["raw"]:
                return float(data["raw"][key])
    return 0.0

def get_event_type(data):
    if "event_type" in data:
        return data["event_type"]
    if "type" in data:
        return data["type"]
    if "raw" in data and isinstance(data["raw"], dict):
        if "type" in data["raw"]:
            return data["raw"]["type"]
    return "unknown"

def get_market(data):
    if "market" in data:
        return data["market"]
    if "code" in data:
        return data["code"]
    if "raw" in data and isinstance(data["raw"], dict):
        if "code" in data["raw"]:
            return data["raw"]["code"]
    return "unknown"

def create_db_schema(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            market TEXT,
            event_type TEXT,
            normalized_event_type TEXT,
            source_file TEXT,
            line_index INTEGER,
            raw_json TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_meta (
            source_path TEXT,
            source_size INTEGER,
            source_mtime REAL,
            source_line_count INTEGER,
            cache_created_at TEXT,
            cache_version TEXT
        )
    ''')
    
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);",
        "CREATE INDEX IF NOT EXISTS idx_events_market ON events(market);",
        "CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);",
        "CREATE INDEX IF NOT EXISTS idx_events_normalized_event_type ON events(normalized_event_type);",
        "CREATE INDEX IF NOT EXISTS idx_events_market_ts ON events(market, ts);",
        "CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(normalized_event_type, ts);",
        "CREATE INDEX IF NOT EXISTS idx_events_market_type_ts ON events(market, normalized_event_type, ts);"
    ]
    
    for idx in indices:
        cursor.execute(idx)
    conn.commit()

def build_cache(rebuild=False):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_SQLITE), exist_ok=True)
    
    if not os.path.exists(INPUT_JSONL):
        print(f"[Error] Input file not found: {INPUT_JSONL}")
        return

    if os.path.exists(OUTPUT_SQLITE):
        if rebuild:
            print(f"[Info] Rebuild flag set. Removing existing cache: {OUTPUT_SQLITE}")
            os.remove(OUTPUT_SQLITE)
        else:
            print(f"[Error] SQLite cache already exists: {OUTPUT_SQLITE}")
            print("Use --rebuild to overwrite.")
            return

    conn = sqlite3.connect(OUTPUT_SQLITE)
    cursor = conn.cursor()
    
    # Performance Optimizations
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    
    create_db_schema(conn)
    
    print(f"[Info] Starting cache build from {INPUT_JSONL}...")
    start_time = time.time()
    
    batch = []
    line_index = 0
    total_parsed = 0
    
    market_counts = defaultdict(int)
    event_type_counts = defaultdict(int)
    norm_event_type_counts = defaultdict(int)
    
    min_ts = float('inf')
    max_ts = 0.0
    
    try:
        with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
            for line in f:
                line_index += 1
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    ts = get_timestamp(data)
                    market = get_market(data)
                    event_type = get_event_type(data)
                    
                    if ts > 1e11:
                        ts = ts / 1000.0
                        
                    norm_event_type = event_type
                    if event_type == "orderbook_sample" or event_type == "orderbook":
                        norm_event_type = "orderbook"
                    elif event_type == "trade":
                        norm_event_type = "trade"
                    
                    batch.append((
                        ts, market, event_type, norm_event_type, 
                        INPUT_JSONL, line_index, line
                    ))
                    
                    if ts < min_ts and ts > 0:
                        min_ts = ts
                    if ts > max_ts:
                        max_ts = ts
                        
                    market_counts[market] += 1
                    event_type_counts[event_type] += 1
                    norm_event_type_counts[norm_event_type] += 1
                    total_parsed += 1
                    
                except json.JSONDecodeError:
                    continue
                
                if len(batch) >= BATCH_SIZE:
                    cursor.executemany('''
                        INSERT INTO events (ts, market, event_type, normalized_event_type, source_file, line_index, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', batch)
                    conn.commit()
                    batch = []
                
                if line_index % 100000 == 0:
                    print(f"[Progress] Processed {line_index} lines...")
                    
        if batch:
            cursor.executemany('''
                INSERT INTO events (ts, market, event_type, normalized_event_type, source_file, line_index, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', batch)
            conn.commit()
            
        # Write metadata
        source_size = os.path.getsize(INPUT_JSONL)
        source_mtime = os.path.getmtime(INPUT_JSONL)
        cache_created_at = datetime.now().isoformat()
        
        cursor.execute("DELETE FROM cache_meta")
        cursor.execute('''
            INSERT INTO cache_meta (source_path, source_size, source_mtime, source_line_count, cache_created_at, cache_version)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (INPUT_JSONL, source_size, source_mtime, line_index, cache_created_at, "1.0"))
        conn.commit()
            
    except Exception as e:
        print(f"[Error] Exception during build: {e}")
    finally:
        conn.close()
        
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    file_size_mb = os.path.getsize(OUTPUT_SQLITE) / (1024 * 1024)
    
    if min_ts == float('inf'):
        min_ts = 0.0
        
    print(f"\n[Info] Build completed in {elapsed_time:.2f} seconds.")
    print(f"[Info] Total rows inserted: {total_parsed}")
    
    summary = {
        "generated_at": datetime.now().isoformat(),
        "input_file": INPUT_JSONL,
        "output_sqlite": OUTPUT_SQLITE,
        "total_rows": total_parsed,
        "market_counts": dict(market_counts),
        "event_type_counts": dict(event_type_counts),
        "normalized_event_type_counts": dict(norm_event_type_counts),
        "earliest_ts": min_ts,
        "latest_ts": max_ts,
        "earliest_time": datetime.fromtimestamp(min_ts).isoformat() if min_ts > 0 else None,
        "latest_time": datetime.fromtimestamp(max_ts).isoformat() if max_ts > 0 else None,
        "db_size_mb": round(file_size_mb, 2),
        "build_elapsed_sec": round(elapsed_time, 2)
    }
    
    with open(JSON_REPORT, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        " Master Dataset SQLite Cache Build Report",
        "============================================================",
        f"생성 시각: {summary['generated_at']}",
        f"입력 JSONL: {summary['input_file']}",
        f"출력 DB: {summary['output_sqlite']}",
        f"DB 크기: {summary['db_size_mb']} MB",
        f"빌드 소요 시간: {summary['build_elapsed_sec']} 초",
        "",
        "[전체 통계]",
        f" - 총 로우 수: {summary['total_rows']}",
        f" - 시작 시간: {summary['earliest_time']} ({summary['earliest_ts']})",
        f" - 종료 시간: {summary['latest_time']} ({summary['latest_ts']})",
        "",
        "[Market별 로우 수]"
    ]
    for k, v in sorted(market_counts.items(), key=lambda x: x[1], reverse=True):
        txt_lines.append(f" - {k}: {v}")
        
    txt_lines.append("")
    txt_lines.append("[Event Type별 로우 수]")
    for k, v in sorted(event_type_counts.items(), key=lambda x: x[1], reverse=True):
        txt_lines.append(f" - {k}: {v}")
        
    txt_lines.append("")
    txt_lines.append("[Normalized Event Type별 로우 수]")
    for k, v in sorted(norm_event_type_counts.items(), key=lambda x: x[1], reverse=True):
        txt_lines.append(f" - {k}: {v}")
        
    txt_lines.extend([
        "",
        "------------------------------------------------------------",
        " 🚫 원본 JSONL 파일 삭제 금지",
        " 🚫 config.json 및 candidate 수정 금지",
        "------------------------------------------------------------"
    ])
    
    with open(TXT_REPORT, 'w', encoding='utf-8') as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print(f"[Done] Report saved to: {TXT_REPORT}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build SQLite cache from master JSONL.")
    parser.add_argument("--rebuild", action="store_true", help="Overwrite existing SQLite DB")
    args = parser.parse_args()
    build_cache(rebuild=args.rebuild)
