"""
merge_ws_chunks.py
Merges JSONL chunks collected by run_reversal_oos_chunk_runner.py.

- Reads successful chunks from the manifest (or globs them if manifest missing).
- Parses each line, handling JSON decode errors gracefully.
- Deduplicates events based on key fields (market, type, timestamp, price, volume, etc.).
- Sorts the merged events by timestamp.
- Writes the merged output to a single JSONL file.
- Produces a summary JSON and TXT.
"""

import argparse
import glob
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[Merge] {ts}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[Merge] {ts}  {msg}".encode("ascii", errors="replace").decode(), flush=True)


def get_event_signature(ev: dict) -> int:
    """Generate a signature for deduplication based on key fields."""
    ev_type = ev.get("type", "")
    market = ev.get("code") or ev.get("market", "")
    timestamp = ev.get("timestamp") or ev.get("trade_timestamp") or ev.get("ts", "")
    
    if ev_type == "trade":
        price = ev.get("trade_price") or ev.get("price", "")
        volume = ev.get("trade_volume") or ev.get("volume", "")
        return hash((market, ev_type, timestamp, price, volume))
    elif ev_type == "orderbook":
        total_ask_size = ev.get("total_ask_size", "")
        total_bid_size = ev.get("total_bid_size", "")
        return hash((market, ev_type, timestamp, total_ask_size, total_bid_size))
    else:
        # Fallback to full content hash if type is unknown
        return hash(json.dumps(ev, sort_keys=True))


def get_event_timestamp(ev: dict) -> float:
    """Extract a sortable timestamp from the event."""
    ts = ev.get("timestamp") or ev.get("trade_timestamp") or ev.get("ts")
    if ts is not None:
        try:
            return float(ts)
        except ValueError:
            pass
    return 0.0


def main():
    parser = argparse.ArgumentParser(description="Merge OOS Chunk JSONL files")
    parser.add_argument("--input-dir", type=str, default="logs/experiments/chunks", help="Directory containing chunk files")
    parser.add_argument("--manifest", type=str, default="logs/experiments/chunks/reversal_oos_chunk_manifest.jsonl", help="Manifest file path")
    parser.add_argument("--output", type=str, default="logs/experiments/reversal_oos_chunks_merged.jsonl", help="Merged output JSONL file")
    parser.add_argument("--summary-json", type=str, default="reports/experiments/reversal_oos_chunk_merge_summary.json", help="Summary JSON output path")
    parser.add_argument("--summary-txt", type=str, default="reports/experiments/reversal_oos_chunk_merge_summary.txt", help="Summary TXT output path")
    args = parser.parse_args()

    start_wall = time.time()
    log(f"Input dir  : {args.input_dir}")
    log(f"Manifest   : {args.manifest}")
    log(f"Output     : {args.output}")

    chunk_files = []
    
    # 1. Read manifest if available
    if os.path.exists(args.manifest):
        log("Reading manifest...")
        try:
            with open(args.manifest, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("status") == "success":
                            chunk_path = rec.get("chunk_path")
                            # Make path relative to input-dir if it's not absolute or if it exists
                            if chunk_path and os.path.exists(chunk_path):
                                chunk_files.append(chunk_path)
                            elif chunk_path:
                                basename = os.path.basename(chunk_path)
                                alt_path = os.path.join(args.input_dir, basename)
                                if os.path.exists(alt_path):
                                    chunk_files.append(alt_path)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            log(f"Error reading manifest: {e}")
    
    # Deduplicate chunk file list while preserving order
    chunk_files = list(dict.fromkeys(chunk_files))

    # 2. Fallback to globbing if no files found from manifest
    if not chunk_files:
        log("No successful chunks found via manifest. Globbing directory...")
        pattern = os.path.join(args.input_dir, "reversal_oos_chunk_*.jsonl")
        globbed = glob.glob(pattern)
        # Exclude manifest if it matches somehow
        chunk_files = sorted([f for f in globbed if "manifest" not in f])
        
    log(f"Found {len(chunk_files)} chunk files to merge.")
    
    if not chunk_files:
        log("No chunks to merge. Exiting.")
        sys.exit(0)

    # 3. Read and deduplicate events
    events = []
    seen_signatures = set()
    
    lines_read = 0
    parse_errors = 0
    duplicates = 0
    
    market_counts = defaultdict(int)
    type_counts = defaultdict(int)

    log("Reading and parsing chunks...")
    for chunk_file in chunk_files:
        if not os.path.exists(chunk_file):
            log(f"  Warning: File missing: {chunk_file}")
            continue
            
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    lines_read += 1
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        parse_errors += 1
                        continue
                        
                    sig = get_event_signature(ev)
                    if sig in seen_signatures:
                        duplicates += 1
                        continue
                        
                    seen_signatures.add(sig)
                    events.append(ev)
                    
                    market = ev.get("code") or ev.get("market") or "UNKNOWN"
                    ev_type = ev.get("type", "UNKNOWN")
                    market_counts[market] += 1
                    type_counts[ev_type] += 1
                    
        except Exception as e:
            log(f"  Error reading {chunk_file}: {e}")

    # 4. Sort events by timestamp
    log(f"Sorting {len(events)} events by timestamp...")
    events.sort(key=get_event_timestamp)

    # Calculate time bounds
    min_ts, max_ts = None, None
    if events:
        min_ts = get_event_timestamp(events[0])
        max_ts = get_event_timestamp(events[-1])

    # 5. Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    log(f"Writing merged events to {args.output}...")
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"Error writing output: {e}")
        
    # 6. Generate summary
    elapsed = time.time() - start_wall
    
    summary = {
        "ok": True,
        "merge_time": datetime.now().isoformat(),
        "elapsed_sec": round(elapsed, 1),
        "input_chunks_count": len(chunk_files),
        "lines_read": lines_read,
        "parse_errors": parse_errors,
        "duplicates_removed": duplicates,
        "final_events_count": len(events),
        "market_counts": dict(market_counts),
        "type_counts": dict(type_counts),
        "start_timestamp": min_ts,
        "end_timestamp": max_ts,
        "output_file": args.output
    }
    
    os.makedirs(os.path.dirname(args.summary_json), exist_ok=True)
    try:
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log(f"Summary JSON saved to {args.summary_json}")
    except Exception as e:
        log(f"Error saving summary JSON: {e}")
        
    summary_txt_lines = [
        "=" * 60,
        "  Reversal Edge v2 OOS Chunk Merge Summary",
        "=" * 60,
        f"완료 시각        : {summary['merge_time']}",
        f"경과 시간        : {elapsed:.1f}초",
        f"입력 Chunk 수    : {len(chunk_files)}",
        f"총 읽은 줄 수    : {lines_read}",
        f"파싱 실패 줄 수  : {parse_errors}",
        f"중복 제거 수     : {duplicates}",
        f"최종 이벤트 수   : {len(events)}",
        f"출력 파일        : {args.output}",
        "",
        "마켓별 이벤트 수:",
    ]
    
    for mkt, cnt in sorted(market_counts.items(), key=lambda x: x[1], reverse=True):
        summary_txt_lines.append(f"  - {mkt}: {cnt}")
        
    summary_txt_lines.extend([
        "",
        "타입별 이벤트 수:",
    ])
    
    for typ, cnt in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        summary_txt_lines.append(f"  - {typ}: {cnt}")
        
    if min_ts and max_ts:
        summary_txt_lines.extend([
            "",
            f"시작 Timestamp   : {min_ts}",
            f"종료 Timestamp   : {max_ts}",
        ])
        
    os.makedirs(os.path.dirname(args.summary_txt), exist_ok=True)
    try:
        with open(args.summary_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_txt_lines) + "\n")
        log(f"Summary TXT saved to {args.summary_txt}")
    except Exception as e:
        log(f"Error saving summary TXT: {e}")

    log("Merge completed successfully.")


if __name__ == "__main__":
    main()
