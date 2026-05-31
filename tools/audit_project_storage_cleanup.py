import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "project_storage_cleanup_audit_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "project_storage_cleanup_audit_latest.txt")

KEEP_CRITICAL_DIRS = ["src", "config", "configs", "tests"]
KEEP_CRITICAL_FILES = ["requirements.txt", "README.md", "AGENTS.md", "START_COINB.bat", "STOP_COINB_ALL.bat", "RUN_COINB_ALL.bat"]

def run_git_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return set(result.stdout.splitlines())
    except Exception as e:
        print(f"Git command failed: {e}")
        return set()

def get_git_status():
    tracked = run_git_command(["git", "ls-files"])
    
    # Untracked
    try:
        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True)
        untracked = set()
        for line in result.stdout.splitlines():
            if line.startswith("??"):
                untracked.add(line[3:].strip())
    except:
        untracked = set()
        
    # Ignored
    try:
        result = subprocess.run(["git", "status", "--short", "--ignored"], capture_output=True, text=True, check=True)
        ignored = set()
        for line in result.stdout.splitlines():
            if line.startswith("!!"):
                ignored.add(line[3:].strip())
    except:
        ignored = set()
        
    return tracked, untracked, ignored

def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(os.path.floor(os.math.log(size_bytes, 1024)))
    p = os.math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

import math
def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

def is_git_tracked(filepath, tracked, untracked, ignored):
    # normalize path
    norm_path = filepath.replace("\\", "/")
    if norm_path in tracked:
        return "tracked_by_git"
    if norm_path in untracked:
        return "untracked"
    if norm_path in ignored:
        return "ignored"
    
    # check parents for ignored (git status only shows parent dir if entire dir is ignored)
    parts = norm_path.split('/')
    for i in range(1, len(parts)):
        parent_dir = '/'.join(parts[:i]) + '/'
        if parent_dir in ignored:
            return "ignored"
            
    return "unknown"

def determine_category(filepath, size, is_tracked, ext):
    norm_path = filepath.replace("\\", "/")
    parts = norm_path.split("/")
    filename = parts[-1]
    
    # A. KEEP_CRITICAL
    if parts[0] in KEEP_CRITICAL_DIRS:
        return "KEEP_CRITICAL"
    if filename in KEEP_CRITICAL_FILES:
        return "KEEP_CRITICAL"
    if is_tracked == "tracked_by_git" and (norm_path.startswith("tools/") and ext == ".py"):
        return "KEEP_CRITICAL"
    if is_tracked == "tracked_by_git" and (norm_path.startswith("docs/") and ext == ".md"):
        return "KEEP_CRITICAL"
        
    # B. KEEP_DATA_FOR_RESEARCH
    if "reversal_edge_master_dataset.sqlite" in filename or "binance_public_market_data.sqlite" in filename:
        return "KEEP_DATA_FOR_RESEARCH"
    if "latest" in filename and ext in [".json", ".txt"]:
        return "KEEP_DATA_FOR_RESEARCH"
        
    # C. SAFE_DELETE_CANDIDATE
    if "__pycache__" in parts or ext == ".pyc":
        return "SAFE_DELETE_CANDIDATE"
    if ext in [".tmp", ".bak", ".old"]:
        return "SAFE_DELETE_CANDIDATE"
    if size == 0:
        return "SAFE_DELETE_CANDIDATE"
    if "_cleanup_quarantine" in parts or "_review_snapshot_" in norm_path:
        return "SAFE_DELETE_CANDIDATE"
        
    # D. QUARANTINE_CANDIDATE
    if filename.startswith("RUN_") and ext == ".bat" and filename not in KEEP_CRITICAL_FILES:
        return "QUARANTINE_CANDIDATE"
    if ext in [".md", ".jsonl", ".log", ".txt", ".json", ".sqlite"] and not is_tracked == "tracked_by_git":
        # simple heuristic for quarantine
        if "reports" in parts or "logs" in parts:
             return "QUARANTINE_CANDIDATE"
             
    # E. REVIEW_MANUALLY
    return "REVIEW_MANUALLY"

def audit_directory(root_dir):
    tracked, untracked, ignored = get_git_status()
    
    total_size = 0
    files_info = []
    folders_size = {}
    ext_size = {}
    ext_count = {}
    level1_folders = {}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Ignore .git
        if '.git' in dirnames:
            dirnames.remove('.git')
            
        rel_dir = os.path.relpath(dirpath, root_dir)
        if rel_dir == ".":
            rel_dir = ""
            
        dir_size = 0
        for f in filenames:
            filepath = os.path.join(dirpath, f)
            rel_filepath = os.path.relpath(filepath, root_dir)
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue
                
            total_size += size
            dir_size += size
            
            ext = os.path.splitext(f)[1].lower()
            ext_size[ext] = ext_size.get(ext, 0) + size
            ext_count[ext] = ext_count.get(ext, 0) + 1
            
            mtime = os.path.getmtime(filepath)
            is_tracked = is_git_tracked(rel_filepath, tracked, untracked, ignored)
            category = determine_category(rel_filepath, size, is_tracked, ext)
            
            files_info.append({
                "path": rel_filepath,
                "size": size,
                "mtime": mtime,
                "ext": ext,
                "tracked": is_tracked,
                "category": category
            })
            
        folders_size[rel_dir] = folders_size.get(rel_dir, 0) + dir_size
        
        if rel_dir != "":
            parts = rel_dir.split(os.sep)
            if len(parts) >= 1:
                level1 = parts[0]
                level1_folders[level1] = level1_folders.get(level1, 0) + dir_size
                
    # Bubble up folder sizes
    # (A simple way is to sort by depth descending, but we just want relative path sizes)
    # Actually folders_size currently only has files directly in it. Let's compute recursive.
    recursive_folders_size = {}
    for d in folders_size:
        recursive_size = sum(v for k, v in folders_size.items() if k == d or k.startswith(d + os.sep))
        recursive_folders_size[d] = recursive_size
        
    return {
        "total_size": total_size,
        "files_info": files_info,
        "folders_size": recursive_folders_size,
        "level1_folders": level1_folders,
        "ext_size": ext_size,
        "ext_count": ext_count
    }

def main():
    print("Auditing project storage...")
    audit = audit_directory(".")
    
    total_size = audit["total_size"]
    files_info = audit["files_info"]
    
    # Sort files by size
    files_sorted_size = sorted(files_info, key=lambda x: x["size"], reverse=True)
    top_50_files = files_sorted_size[:50]
    
    # Sort folders by size
    folders_sorted = sorted(audit["folders_size"].items(), key=lambda x: x[1], reverse=True)
    top_30_folders = folders_sorted[:30]
    
    # Category stats
    cat_stats = {}
    for f in files_info:
        cat = f["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"count": 0, "size": 0}
        cat_stats[cat]["count"] += 1
        cat_stats[cat]["size"] += f["size"]
        
    safe_delete_size = cat_stats.get("SAFE_DELETE_CANDIDATE", {}).get("size", 0)
    quarantine_size = cat_stats.get("QUARANTINE_CANDIDATE", {}).get("size", 0)
    
    # Data Archive candidates (large sqlite/db/jsonl/log/zip)
    data_archive_cands = [f for f in files_info if f["ext"] in [".sqlite", ".db", ".jsonl", ".log", ".zip"] and f["size"] > 10 * 1024 * 1024 and f["category"] not in ["KEEP_CRITICAL", "KEEP_DATA_FOR_RESEARCH"]]
    data_archive_size = sum(f["size"] for f in data_archive_cands)
    
    # Bat files
    bat_files = [f for f in files_info if f["ext"] == ".bat"]
    
    # MD files
    md_files = [f for f in files_info if f["ext"] == ".md"]
    
    # Judgement
    if total_size > 50 * 1024 * 1024 * 1024:
        judgement = "STORAGE_TOO_LARGE_DATA_ARCHIVE_NEEDED"
    elif safe_delete_size > 1 * 1024 * 1024 * 1024:
        judgement = "SAFE_DELETE_AVAILABLE"
    elif quarantine_size > 1 * 1024 * 1024 * 1024:
        judgement = "MANUAL_REVIEW_REQUIRED"
    else:
        judgement = "CLEANUP_AUDIT_READY"
        
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_size": total_size,
        "total_size_fmt": format_size(total_size),
        "safe_delete_size": safe_delete_size,
        "quarantine_size": quarantine_size,
        "data_archive_size": data_archive_size,
        "judgement": judgement,
        "next_recommended_step": "Review report and selectively delete SAFE_DELETE_CANDIDATE files, or archive large datasets."
    }
    
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    lines = [
        "========================================================================",
        "  PROJECT STORAGE CLEANUP AUDIT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO FILES DELETED. AUDIT ONLY.",
        "========================================================================",
        f"Generated              : {report['generated_at']}",
        f"Total Project Size     : {format_size(total_size)}",
        f"Safe Delete Candidate  : {format_size(safe_delete_size)} ({cat_stats.get('SAFE_DELETE_CANDIDATE', {}).get('count', 0)} files)",
        f"Quarantine Candidate   : {format_size(quarantine_size)} ({cat_stats.get('QUARANTINE_CANDIDATE', {}).get('count', 0)} files)",
        f"Data Archive Candidate : {format_size(data_archive_size)} ({len(data_archive_cands)} files)",
        "",
        "[ Top 10 Level-1 Folders ]"
    ]
    
    l1_sorted = sorted(audit["level1_folders"].items(), key=lambda x: x[1], reverse=True)
    for d, sz in l1_sorted[:10]:
        lines.append(f"  - {d:<20} : {format_size(sz)}")
        
    lines.extend([
        "",
        "[ Top 10 Large Folders ]"
    ])
    for d, sz in top_30_folders[:10]:
        if d: lines.append(f"  - {d:<40} : {format_size(sz)}")
        
    lines.extend([
        "",
        "[ Top 10 Large Files ]"
    ])
    for f in top_50_files[:10]:
        lines.append(f"  - {f['path']:<50} : {format_size(f['size'])} ({f['category']})")
        
    lines.extend([
        "",
        "[ BAT Files Summary ]",
        f"  Total BAT files: {len(bat_files)}"
    ])
    for cat in ["KEEP_CRITICAL", "SAFE_DELETE_CANDIDATE", "QUARANTINE_CANDIDATE", "REVIEW_MANUALLY"]:
        cat_bats = [f for f in bat_files if f['category'] == cat]
        if cat_bats:
            lines.append(f"  - {cat}: {len(cat_bats)}")
            
    lines.extend([
        "",
        "[ MD Files Summary ]",
        f"  Total MD files: {len(md_files)}"
    ])
    for cat in ["KEEP_CRITICAL", "SAFE_DELETE_CANDIDATE", "QUARANTINE_CANDIDATE", "REVIEW_MANUALLY"]:
        cat_mds = [f for f in md_files if f['category'] == cat]
        if cat_mds:
            lines.append(f"  - {cat}: {len(cat_mds)}")

    lines.extend([
        "",
        "[ Critical Files (DO NOT DELETE) ]"
    ])
    for f in files_info:
        if f["category"] == "KEEP_CRITICAL" and f["path"].count('/') == 0:
            lines.append(f"  - {f['path']}")
            
    lines.extend([
        "",
        "========================================================================",
        f"  JUDGEMENT : {judgement}",
        f"  NEXT STEP : {report['next_recommended_step']}",
        "========================================================================"
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"Done. Judgement: {judgement}")

if __name__ == "__main__":
    main()
