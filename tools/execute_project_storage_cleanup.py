import os
import json
import argparse
import subprocess
import shutil
import math
from datetime import datetime

OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "project_storage_cleanup_dry_run_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "project_storage_cleanup_dry_run_latest.txt")

KEEP_CRITICAL_DIRS = ["src", "tools", "docs", "config", "configs", "tests"]
KEEP_CRITICAL_FILES = [
    "requirements.txt", "README.md", "AGENTS.md", 
    "START_COINB.bat", "STOP_COINB_ALL.bat", "RUN_COINB_ALL.bat"
]

KEEP_CRITICAL_SQLITE = [
    "reversal_edge_master_dataset.sqlite",
    "binance_public_market_data.sqlite"
]

def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

def get_git_status():
    try:
        result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        tracked = set(result.stdout.splitlines())
    except:
        tracked = set()
    return tracked

def is_git_tracked(filepath, tracked):
    norm_path = filepath.replace("\\", "/")
    return norm_path in tracked

def audit_directory(root_dir, args, tracked):
    total_scanned_files = 0
    total_scanned_size = 0
    
    safe_delete_cands = []
    archive_cands = []
    keep_cands = []
    
    blocked_critical_count = 0
    blocked_git_tracked_count = 0
    
    safe_delete_size = 0
    archive_size = 0
    keep_size = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if '.git' in dirnames:
            dirnames.remove('.git')
            
        rel_dir = os.path.relpath(dirpath, root_dir)
        if rel_dir == ".": rel_dir = ""
        
        for f in filenames:
            filepath = os.path.join(dirpath, f)
            rel_filepath = os.path.relpath(filepath, root_dir)
            norm_path = rel_filepath.replace("\\", "/")
            parts = norm_path.split("/")
            
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue
                
            total_scanned_files += 1
            total_scanned_size += size
            
            ext = os.path.splitext(f)[1].lower()
            
            # 1. Critical Check
            is_critical = False
            if parts[0] in KEEP_CRITICAL_DIRS:
                is_critical = True
            elif f in KEEP_CRITICAL_FILES:
                is_critical = True
            elif f in KEEP_CRITICAL_SQLITE:
                is_critical = True
            elif ext in [".py", ".md"]:
                is_critical = True
                
            # 2. Git tracked
            is_tracked = is_git_tracked(rel_filepath, tracked)
            
            if is_critical:
                keep_cands.append((norm_path, size, "KEEP_CRITICAL"))
                keep_size += size
                blocked_critical_count += 1
                continue
                
            if is_tracked:
                keep_cands.append((norm_path, size, "BLOCKED_GIT_TRACKED"))
                keep_size += size
                blocked_git_tracked_count += 1
                continue
                
            # 3. Categorize
            category = "KEEP"
            
            # Safe delete criteria
            if "__pycache__" in parts or ext == ".pyc":
                category = "SAFE_DELETE"
            elif ext in [".tmp", ".bak", ".old"]:
                category = "SAFE_DELETE"
            elif size == 0:
                category = "SAFE_DELETE"
            elif "_review_snapshot_" in norm_path or "_cleanup_quarantine" in parts:
                category = "SAFE_DELETE"
                
            # Archive criteria
            if ext == ".jsonl":
                category = "ARCHIVE"
            elif ext == ".log" and "logs" in parts:
                category = "ARCHIVE"
            elif "reports/experiments/cross_market_validation/tmp_candidates" in norm_path and ext == ".jsonl":
                category = "ARCHIVE"
            elif "logs/experiments/temp_" in norm_path and ext == ".jsonl":
                category = "ARCHIVE"
            elif "ws_events" in norm_path and ext == ".jsonl":
                category = "ARCHIVE"
            elif "top10_krw_72h_chunks" in norm_path and size > 1024*1024:
                category = "ARCHIVE"
            elif "logs/experiments/walk_forward" in norm_path and size > 1024*1024:
                category = "ARCHIVE"
                
            # Size limits
            if category == "ARCHIVE" and size < args.min_size_mb * 1024 * 1024:
                category = "KEEP"
                if ext == ".jsonl": category = "ARCHIVE"
                
            if category == "SAFE_DELETE":
                safe_delete_cands.append((norm_path, size))
                safe_delete_size += size
            elif category == "ARCHIVE":
                archive_cands.append((norm_path, size))
                archive_size += size
            else:
                keep_cands.append((norm_path, size, "KEEP_UNCATEGORIZED"))
                keep_size += size
                
    return {
        "total_scanned_files": total_scanned_files,
        "total_scanned_size": total_scanned_size,
        "safe_delete": sorted(safe_delete_cands, key=lambda x: x[1], reverse=True),
        "archive": sorted(archive_cands, key=lambda x: x[1], reverse=True),
        "keep": sorted(keep_cands, key=lambda x: x[1], reverse=True),
        "safe_delete_size": safe_delete_size,
        "archive_size": archive_size,
        "keep_size": keep_size,
        "blocked_critical_count": blocked_critical_count,
        "blocked_git_tracked_count": blocked_git_tracked_count
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True, help="Always True unless --apply is passed")
    parser.add_argument("--apply", action="store_true", help="Execute the deletion/movement")
    parser.add_argument("--archive-root", default=r"D:\coinB_data_archive", help="Target archive folder")
    parser.add_argument("--delete-safe", action="store_true", help="Delete safe delete candidates")
    parser.add_argument("--move-archive", action="store_true", help="Move archive candidates")
    parser.add_argument("--include-quarantine", action="store_true", help="Include quarantine items")
    parser.add_argument("--max-files", type=int, default=0, help="Max files to process")
    parser.add_argument("--min-size-mb", type=float, default=1.0, help="Min size for archive")
    parser.add_argument("--confirm-token", type=str, default="", help="Token to confirm apply")
    args = parser.parse_args()
    
    if args.apply:
        args.dry_run = False
        
    if not args.dry_run and args.confirm_token != "CLEANUP_EXECUTE":
        print("ERROR: --confirm-token CLEANUP_EXECUTE required for --apply")
        return
        
    tracked = get_git_status()
    print("Auditing project storage for cleanup...")
    res = audit_directory(".", args, tracked)
    
    warnings = []
    if os.path.abspath(args.archive_root).startswith(os.path.abspath(".")):
        warnings.append(f"Archive root {args.archive_root} is inside the project!")
        
    if not os.path.exists(args.archive_root):
        warnings.append(f"Archive root {args.archive_root} does not exist. (Dry-run mode only warns)")
        if not args.dry_run:
            print("ERROR: Archive root does not exist.")
            return

    deleted_count = 0
    moved_count = 0
    if not args.dry_run:
        if args.delete_safe:
            for path, sz in res["safe_delete"]:
                try:
                    os.remove(path)
                    deleted_count += 1
                except Exception as e:
                    warnings.append(f"Failed to delete {path}: {e}")
        if args.move_archive:
            for path, sz in res["archive"]:
                try:
                    dst = os.path.join(args.archive_root, path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(path, dst)
                    moved_count += 1
                except Exception as e:
                    warnings.append(f"Failed to move {path}: {e}")
                    
    top_50_archive = res["archive"][:50]
    top_50_safe = res["safe_delete"][:50]
    
    cmd = "python tools/execute_project_storage_cleanup.py --apply --confirm-token CLEANUP_EXECUTE"
    if args.delete_safe: cmd += " --delete-safe"
    if args.move_archive: cmd += " --move-archive"
    if args.include_quarantine: cmd += " --include-quarantine"
    cmd += f" --archive-root {args.archive_root}"
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "is_dry_run": args.dry_run,
        "total_scanned_files": res["total_scanned_files"],
        "total_scanned_size": res["total_scanned_size"],
        "safe_delete_count": len(res["safe_delete"]),
        "safe_delete_size": res["safe_delete_size"],
        "archive_candidate_count": len(res["archive"]),
        "archive_candidate_size": res["archive_size"],
        "keep_count": len(res["keep"]),
        "keep_size": res["keep_size"],
        "blocked_critical_count": res["blocked_critical_count"],
        "blocked_git_tracked_count": res["blocked_git_tracked_count"],
        "top_50_archive_candidates": top_50_archive,
        "top_50_safe_delete_candidates": top_50_safe,
        "warnings": warnings,
        "exact_command_for_apply_mode": cmd
    }
    
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    lines = [
        "========================================================================",
        "  PROJECT STORAGE CLEANUP DRY RUN",
        f"  MODE: {'DRY-RUN' if args.dry_run else 'APPLIED'}",
        "========================================================================",
        f"Generated              : {report['generated_at']}",
        f"Total Scanned          : {format_size(report['total_scanned_size'])} ({report['total_scanned_files']} files)",
        f"Safe Delete Count      : {report['safe_delete_count']} files",
        f"Safe Delete Size       : {format_size(report['safe_delete_size'])}",
        f"Archive Candidate Count: {report['archive_candidate_count']} files",
        f"Archive Candidate Size : {format_size(report['archive_candidate_size'])}",
        f"Keep Count             : {report['keep_count']} files",
        f"Keep Size              : {format_size(report['keep_size'])}",
        f"Blocked Critical       : {report['blocked_critical_count']} files",
        f"Blocked Git Tracked    : {report['blocked_git_tracked_count']} files",
        "",
        "[ Warnings ]"
    ]
    for w in warnings:
        lines.append(f"  - {w}")
        
    lines.extend([
        "",
        "[ Top 10 Archive Candidates ]"
    ])
    for p, sz in top_50_archive[:10]:
        lines.append(f"  - {p:<60} : {format_size(sz)}")
        
    lines.extend([
        "",
        "[ Top 10 Safe Delete Candidates ]"
    ])
    for p, sz in top_50_safe[:10]:
        lines.append(f"  - {p:<60} : {format_size(sz)}")
        
    lines.extend([
        "",
        "========================================================================",
        "  EXACT COMMAND FOR APPLY MODE:",
        f"  {cmd}",
        "========================================================================"
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"Done. Dry run mode: {args.dry_run}")
    
if __name__ == "__main__":
    main()
