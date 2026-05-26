"""
audit_reversal_data_assets.py
Reversal Data Asset Audit Tool

Scans all reversal-related data assets in the project and produces
a structured audit report: file sizes, time coverage, market coverage,
SQLite schema/counts, and validation readiness assessment.

IMPORTANT:
  - Read-only audit. No files are modified, created, or deleted.
  - No config / candidate / live / raw files are modified.
  - SQLite is inspected via schema + COUNT/MIN/MAX only (no full scan).
"""
import glob
import json
import os
import sqlite3
from datetime import datetime, timezone

# ─── Scan roots ───────────────────────────────────────────────────────────────
SCAN_ROOTS = [
    "reports/experiments",
    "logs/experiments",
]

# ─── SQLite files to inspect ──────────────────────────────────────────────────
SQLITE_PATTERNS = [
    "logs/experiments/**/*.sqlite",
    "logs/experiments/**/*.db",
    "reports/experiments/**/*.sqlite",
]

# ─── Patterns for reversal-relevant files ─────────────────────────────────────
REVERSAL_KEYWORDS = [
    "reversal", "master", "discovery", "validation", "holdout",
    "chunk", "snapshot", "oos", "walk_forward", "feature", "histogram",
    "top10", "cross_market", "paper_candidate", "threshold",
]

# ─── Output ───────────────────────────────────────────────────────────────────
OUT_DIR  = "reports/experiments"
OUT_JSON = os.path.join(OUT_DIR, "reversal_data_asset_audit_latest.json")
OUT_TXT  = os.path.join(OUT_DIR, "reversal_data_asset_audit_latest.txt")


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _mtime_iso(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    except Exception:
        return "unknown"


def _size_human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _classify(fname):
    lower = fname.lower()
    if "master_dataset" in lower or "reversal_edge_master" in lower:
        return "master_dataset"
    if "discovery" in lower:
        return "discovery_report"
    if "validation" in lower and "threshold" not in lower and "histogram" not in lower:
        return "validation_report"
    if "histogram" in lower or "threshold" in lower:
        return "threshold_histogram"
    if "holdout" in lower:
        return "holdout_report"
    if "walk_forward" in lower or "oos" in lower:
        return "oos_walk_forward"
    if "paper_candidate" in lower or "design" in lower:
        return "paper_candidate_design"
    if "chunk" in lower:
        return "chunk_data"
    if "snapshot" in lower:
        return "snapshot_data"
    if "auto_research" in lower:
        return "auto_research_report"
    if "audit" in lower or "coverage" in lower:
        return "audit_report"
    if lower.endswith(".sqlite") or lower.endswith(".db"):
        return "sqlite_cache"
    if lower.endswith(".jsonl"):
        return "raw_jsonl"
    return "other"


def _is_reversal_relevant(fname):
    lower = fname.lower()
    return any(kw in lower for kw in REVERSAL_KEYWORDS)


def _quick_peek_json(path, max_bytes=4096):
    """Read first max_bytes and try to extract judgement/market/count keys."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            chunk = f.read(min(max_bytes, size)).decode("utf-8", errors="replace")
        hints = {}
        # Look for common keys
        for kw in ("judgement", "markets", "valid_markets", "total_snapshots",
                   "master_event_count", "after_dedup_count", "mode"):
            idx = chunk.find(f'"{kw}"')
            if idx != -1:
                snippet = chunk[idx : idx + 80].replace("\n", " ").replace("\r", "")
                hints[kw] = snippet.split(":", 1)[-1].strip().rstrip(",}").strip()[:60]
        return hints
    except Exception:
        return {}


def _count_jsonl_lines(path, max_read=500_000):
    """Count lines in a jsonl file up to max_read bytes."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return 0
        lines = 0
        with open(path, "rb") as f:
            buf = f.read(max_read)
        lines = buf.count(b"\n")
        if size > max_read:
            # Estimate total
            lines = int(lines * size / max_read)
            return f"~{lines:,} (estimated)"
        return lines
    except Exception:
        return "unknown"


def inspect_sqlite(path):
    """Return schema + stats without full scan."""
    info = {
        "path": path,
        "size": _size_human(os.path.getsize(path)),
        "size_bytes": os.path.getsize(path),
        "mtime": _mtime_iso(path),
        "tables": {},
        "error": None,
    }
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.cursor()

        # Table list
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]

        for tbl in tables:
            tbl_info = {}
            # Column list
            try:
                cur.execute(f"PRAGMA table_info({tbl})")
                cols = [r[1] for r in cur.fetchall()]
                tbl_info["columns"] = cols
            except Exception as e:
                tbl_info["columns"] = [f"error: {e}"]

            # Row count
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                tbl_info["row_count"] = cur.fetchone()[0]
            except Exception:
                tbl_info["row_count"] = "error"

            # Distinct markets
            if "market" in tbl_info.get("columns", []):
                try:
                    cur.execute(f"SELECT COUNT(DISTINCT market) FROM {tbl}")
                    tbl_info["distinct_markets"] = cur.fetchone()[0]
                    cur.execute(
                        f"SELECT market, COUNT(*) FROM {tbl} "
                        f"WHERE market IS NOT NULL GROUP BY market "
                        f"ORDER BY COUNT(*) DESC LIMIT 20"
                    )
                    tbl_info["top_markets"] = {r[0]: r[1] for r in cur.fetchall()}
                except Exception as e:
                    tbl_info["distinct_markets"] = f"error: {e}"

            # Time range
            ts_col = None
            for c in tbl_info.get("columns", []):
                if c in ("ts", "timestamp", "received_at", "created_at"):
                    ts_col = c
                    break
            if ts_col:
                try:
                    cur.execute(
                        f"SELECT MIN({ts_col}), MAX({ts_col}) FROM {tbl}"
                    )
                    mn, mx = cur.fetchone()
                    tbl_info["ts_min"] = mn
                    tbl_info["ts_max"] = mx
                    if mn and mx:
                        dur_h = (float(mx) - float(mn)) / 3600
                        tbl_info["duration_hours"] = round(dur_h, 1)
                except Exception as e:
                    tbl_info["ts_range"] = f"error: {e}"

            # Unknown market count
            if "market" in tbl_info.get("columns", []):
                try:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {tbl} WHERE market='unknown' OR market IS NULL OR market=''"
                    )
                    tbl_info["unknown_market_count"] = cur.fetchone()[0]
                except Exception:
                    pass

            info["tables"][tbl] = tbl_info

        conn.close()
    except Exception as e:
        info["error"] = str(e)

    return info


def scan_file_assets():
    """Scan SCAN_ROOTS for reversal-relevant files."""
    assets = []
    for root in SCAN_ROOTS:
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if not _is_reversal_relevant(fname):
                    continue
                fpath = os.path.join(dirpath, fname)
                size  = os.path.getsize(fpath)
                ext   = os.path.splitext(fname)[1].lower()
                asset = {
                    "path":       fpath,
                    "filename":   fname,
                    "type":       _classify(fname),
                    "size":       _size_human(size),
                    "size_bytes": size,
                    "mtime":      _mtime_iso(fpath),
                }
                if ext == ".json" and size < 20_000_000:
                    asset["peek"] = _quick_peek_json(fpath)
                elif ext == ".jsonl":
                    asset["line_count_estimate"] = _count_jsonl_lines(fpath)
                assets.append(asset)
    # Sort by size descending
    assets.sort(key=lambda x: x["size_bytes"], reverse=True)
    return assets


def scan_sqlite():
    """Find and inspect all SQLite files."""
    results = []
    seen = set()
    for pattern in SQLITE_PATTERNS:
        for path in glob.glob(pattern, recursive=True):
            if path not in seen:
                seen.add(path)
                print(f"  [SQLite] {path}")
                results.append(inspect_sqlite(path))
    return results


def determine_judgement(file_assets, sqlite_results):
    """Derive overall data readiness judgement."""
    # Check master SQLite
    master_ok     = False
    master_rows   = 0
    master_mkts   = 0
    master_dur_h  = 0.0
    for sq in sqlite_results:
        for tbl, ti in sq.get("tables", {}).items():
            rc = ti.get("row_count", 0)
            if isinstance(rc, int) and rc > 100_000:
                master_ok = True
                master_rows = max(master_rows, rc)
                master_mkts = max(master_mkts, ti.get("distinct_markets", 0) or 0)
                master_dur_h = max(master_dur_h, ti.get("duration_hours", 0.0) or 0.0)

    # Check discovery + validation report presence
    has_discovery  = any(a["type"] == "discovery_report"  for a in file_assets)
    has_validation = any(a["type"] == "validation_report" for a in file_assets)
    has_histogram  = any(a["type"] == "threshold_histogram" for a in file_assets)
    has_chunks     = any(a["type"] == "chunk_data"          for a in file_assets)

    if master_ok and master_mkts >= 5 and master_dur_h >= 48:
        if has_discovery and has_validation:
            judgement = "FULL_DATA_VALIDATION_POSSIBLE"
        else:
            judgement = "SQLITE_MASTER_USABLE"
    elif master_ok and master_rows > 0:
        judgement = "SQLITE_MASTER_USABLE"
    elif has_chunks:
        judgement = "DATA_FRAGMENTED"
    else:
        judgement = "NEED_MORE_COLLECTION"

    summary = {
        "judgement":          judgement,
        "master_sqlite_ok":   master_ok,
        "master_row_count":   master_rows,
        "master_markets":     master_mkts,
        "master_duration_h":  master_dur_h,
        "has_discovery":      has_discovery,
        "has_validation":     has_validation,
        "has_histogram":      has_histogram,
        "has_chunks":         has_chunks,
        "total_assets_found": len(file_assets),
        "sqlite_files_found": len(sqlite_results),
    }
    return judgement, summary


def _build_txt(report):
    judgement = report.get("judgement", "UNKNOWN")
    summary   = report.get("summary", {})
    lines = [
        "=" * 72,
        "  Reversal Data Asset Audit Report",
        "=" * 72,
        f"Generated  : {report.get('generated_at', 'N/A')}",
        f"Judgement  : {judgement}",
        "",
        "[ Summary ]",
        f"  Master SQLite usable  : {summary.get('master_sqlite_ok')}",
        f"  Master row count      : {summary.get('master_row_count', 0):,}",
        f"  Master markets        : {summary.get('master_markets')}",
        f"  Master duration (h)   : {summary.get('master_duration_h')}",
        f"  Discovery report      : {summary.get('has_discovery')}",
        f"  Validation report     : {summary.get('has_validation')}",
        f"  Histogram report      : {summary.get('has_histogram')}",
        f"  Chunk data present    : {summary.get('has_chunks')}",
        f"  Total assets found    : {summary.get('total_assets_found')}",
        f"  SQLite files found    : {summary.get('sqlite_files_found')}",
    ]

    # Judgement explanation
    lines += ["", "[ Judgement Explanation ]"]
    expls = {
        "FULL_DATA_VALIDATION_POSSIBLE": (
            "Master SQLite has sufficient data (>=5 markets, >=48h) and "
            "discovery+validation reports exist. Full integrated validation is feasible."
        ),
        "SQLITE_MASTER_USABLE": (
            "Master SQLite is present with meaningful data. "
            "Discovery/validation may need to be run or expanded."
        ),
        "DATA_FRAGMENTED": (
            "Data exists as chunks but no consolidated master SQLite with sufficient coverage. "
            "Run build_master_validation_dataset.py to consolidate."
        ),
        "NEED_MORE_COLLECTION": (
            "Insufficient data found. Run 72h chunk collection or expand existing data."
        ),
    }
    lines.append(f"  {expls.get(judgement, 'N/A')}")

    # SQLite detail
    lines += ["", "[ SQLite Files ]", "-" * 72]
    for sq in report.get("sqlite_results", []):
        lines.append(f"  {sq['path']}  ({sq['size']}  mtime={sq['mtime']})")
        if sq.get("error"):
            lines.append(f"    ERROR: {sq['error']}")
            continue
        for tbl, ti in sq.get("tables", {}).items():
            rc = ti.get("row_count", "?")
            dm = ti.get("distinct_markets", "?")
            dh = ti.get("duration_hours", "?")
            lines.append(
                f"    table={tbl}  rows={rc:,}" if isinstance(rc, int)
                else f"    table={tbl}  rows={rc}"
            )
            lines.append(f"      distinct_markets={dm}  duration_hours={dh}")
            tm = ti.get("top_markets")
            if tm:
                lines.append(f"      top markets: " +
                             "  ".join(f"{m}={n}" for m, n in list(tm.items())[:5]))
    lines.append("-" * 72)

    # File assets (top 20 by size)
    lines += ["", "[ File Assets (top 20 by size) ]", "-" * 72,
              f"  {'Type':<25} {'Size':<10} {'MTime':<22} Filename"]
    for a in report.get("file_assets", [])[:20]:
        lines.append(
            f"  {a['type']:<25} {a['size']:<10} {a['mtime'][:19]:<22} {a['filename']}"
        )
    lines.append("-" * 72)

    lines += [
        "",
        "[ Next Steps ]",
    ]
    next_steps = {
        "FULL_DATA_VALIDATION_POSSIBLE": [
            "1. Re-run run_cross_market_reversal_validation.py with full dataset.",
            "2. Re-run extract_reversal_threshold_histograms.py.",
            "3. Review design_reversal_paper_candidate.py output.",
            "4. Plan paper simulation with confirmed thresholds.",
        ],
        "SQLITE_MASTER_USABLE": [
            "1. Run discover_cross_market_reversal_features.py.",
            "2. Run run_cross_market_reversal_validation.py.",
            "3. Check coverage across all KRW markets.",
        ],
        "DATA_FRAGMENTED": [
            "1. Run build_master_validation_dataset.py to consolidate chunks.",
            "2. Verify chunk count and market coverage.",
            "3. Re-audit after consolidation.",
        ],
        "NEED_MORE_COLLECTION": [
            "1. Run RUN_TOP10_KRW_CHUNK_COLLECTOR_72H.bat.",
            "2. Run build_master_validation_dataset.py.",
            "3. Re-audit.",
        ],
    }
    for step in next_steps.get(judgement, ["N/A"]):
        lines.append(f"  {step}")

    lines += [
        "",
        "=" * 72,
        "  AUDIT REPORT ONLY.",
        "  No files were modified, created (beyond this report), or deleted.",
        "=" * 72,
    ]
    return lines


def main():
    print("=" * 60)
    print(" Reversal Data Asset Audit")
    print("=" * 60)

    print("[Step 1] Scanning file assets ...")
    file_assets = scan_file_assets()
    print(f"  Found {len(file_assets)} reversal-relevant files.")

    print("[Step 2] Inspecting SQLite files ...")
    sqlite_results = scan_sqlite()
    print(f"  Found {len(sqlite_results)} SQLite files.")

    print("[Step 3] Determining judgement ...")
    judgement, summary = determine_judgement(file_assets, sqlite_results)
    print(f"  Judgement: {judgement}")

    report = {
        "generated_at":   datetime.now().isoformat(),
        "judgement":      judgement,
        "summary":        summary,
        "sqlite_results": sqlite_results,
        "file_assets":    file_assets,
        "note": (
            "Audit only. No config / candidate / live files were modified. "
            "No validation or discovery scripts were executed."
        ),
    }

    txt_lines = _build_txt(report)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")

    print(f"[Done] JSON : {OUT_JSON}")
    print(f"[Done] TXT  : {OUT_TXT}")
    print(f"Judgement   : {judgement}")


if __name__ == "__main__":
    main()
