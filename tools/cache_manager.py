import os
import sqlite3
import time
import subprocess
from datetime import datetime

MASTER_JSONL = "logs/experiments/master/reversal_edge_master_dataset.jsonl"
MASTER_SQLITE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
CACHE_VERSION = "1.0"

def get_cache_status():
    """Check the status of the SQLite cache against the JSONL file."""
    if not os.path.exists(MASTER_JSONL):
        return {"valid": False, "reason": "source_jsonl_missing", "source_path": MASTER_JSONL}
        
    source_size = os.path.getsize(MASTER_JSONL)
    source_mtime = os.path.getmtime(MASTER_JSONL)
    
    if not os.path.exists(MASTER_SQLITE):
        return {"valid": False, "reason": "sqlite_missing"}
        
    try:
        conn = sqlite3.connect(MASTER_SQLITE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cache_meta'")
        if not cursor.fetchone():
            conn.close()
            return {"valid": False, "reason": "cache_meta_table_missing"}
            
        cursor.execute("SELECT source_path, source_size, source_mtime, source_line_count, cache_created_at, cache_version FROM cache_meta LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {"valid": False, "reason": "cache_meta_empty"}
            
        _, cached_size, cached_mtime, cached_line_count, _, cached_version = row
        
        if cached_version != CACHE_VERSION:
            return {"valid": False, "reason": "cache_version_mismatch"}
            
        if cached_size != source_size:
            return {"valid": False, "reason": "source_size_changed"}
            
        if cached_mtime != source_mtime:
            return {"valid": False, "reason": "source_mtime_changed"}
            
        return {
            "valid": True,
            "reason": "cache_is_valid",
            "sqlite_path": MASTER_SQLITE,
            "cached_rows": cached_line_count
        }
    except Exception as e:
        return {"valid": False, "reason": f"db_read_error_{e}"}

def is_cache_valid():
    """Return True if the cache is valid and up-to-date."""
    return get_cache_status().get("valid", False)

def ensure_cache():
    """
    Ensure the cache exists and is up-to-date.
    If not, automatically run the build_master_dataset_cache.py script to rebuild it.
    Returns: (bool success, str status_reason)
    """
    status = get_cache_status()
    if status["valid"]:
        return True, "cache_valid"
        
    reason = status["reason"]
    if reason == "source_jsonl_missing":
        print(f"[CacheManager] Error: Source JSONL missing at {MASTER_JSONL}. Cannot build cache.")
        return False, reason
        
    print(f"[CacheManager] Cache is invalid or outdated (Reason: {reason}). Rebuilding automatically...")
    
    cmd = [
        "python",
        "tools/build_master_dataset_cache.py",
        "--rebuild"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("[CacheManager] Cache rebuilt successfully.")
        
        new_status = get_cache_status()
        if new_status["valid"]:
            return True, "cache_rebuilt"
        else:
            print(f"[CacheManager] Warning: Rebuild completed but status is still invalid: {new_status['reason']}")
            return False, f"rebuild_failed_{new_status['reason']}"
            
    except subprocess.CalledProcessError as e:
        print(f"[CacheManager] Cache rebuild failed with error code {e.returncode}")
        print(f"[CacheManager] STDOUT: {e.stdout}")
        print(f"[CacheManager] STDERR: {e.stderr}")
        return False, "rebuild_subprocess_error"
