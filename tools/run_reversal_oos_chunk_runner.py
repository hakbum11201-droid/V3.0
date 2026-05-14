"""
run_reversal_oos_chunk_runner.py
Resilient OOS chunk collector for Reversal Edge v2.

- Splits total duration into fixed-size chunks.
- Runs collect-ws for each chunk into a separate .jsonl file.
- Retries on failure (up to MAX_RETRY times, 10s wait).
- Records success/failure per chunk in a manifest JSONL.
- Skips already-successful chunks on resume (idempotent).
- Writes a final summary JSON + TXT.
- NO live orders. NO API keys. Paper/OOS data collection only.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

MAX_RETRY = 3
RETRY_WAIT_SEC = 10


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[Chunk] {ts}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[Chunk] {ts}  {msg}".encode("ascii", errors="replace").decode(), flush=True)


def load_manifest(manifest_path: str) -> dict:
    """Load existing manifest into {chunk_id: record} dict."""
    records = {}
    if not os.path.exists(manifest_path):
        return records
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    records[rec["chunk_id"]] = rec
                except Exception:
                    pass
    return records


def append_manifest(manifest_path: str, record: dict):
    """Append one record to manifest JSONL."""
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def run_collect_ws(chunk_path: str, seconds: int) -> bool:
    """
    Run coinb collect-ws for `seconds` seconds, output to chunk_path.
    Returns True on success (exit code 0).
    """
    cmd = [
        sys.executable, "-m", "coinb.main",
        "collect-ws",
        "--config", "config/config.json",
        "--seconds", str(seconds),
        "--output", chunk_path,
    ]
    log(f"collect-ws → {chunk_path}  ({seconds}s)")
    try:
        result = subprocess.run(cmd, timeout=seconds + 60)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("  ⚠ collect-ws timed out (hard limit exceeded)")
        return False
    except Exception as e:
        log(f"  ⚠ collect-ws exception: {e}")
        return False


def build_summary(
    run_id: str,
    start_wall: float,
    total_chunks: int,
    success_ids: list,
    failed_ids: list,
    output_dir: str,
    summary_json: str,
    summary_txt: str,
):
    elapsed = time.time() - start_wall
    report = {
        "ok": True,
        "run_id": run_id,
        "run_time": datetime.now().isoformat(),
        "elapsed_sec": round(elapsed, 1),
        "total_chunks": total_chunks,
        "success_count": len(success_ids),
        "failed_count": len(failed_ids),
        "success_chunk_ids": success_ids,
        "failed_chunk_ids": failed_ids,
        "output_dir": output_dir,
        "live_orders_placed": 0,
    }

    # JSON
    try:
        os.makedirs(os.path.dirname(summary_json), exist_ok=True)
        with open(summary_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log(f"Summary JSON → {summary_json}")
    except Exception as e:
        log(f"  ⚠ Failed to write summary JSON: {e}")

    # TXT
    lines = [
        "=" * 60,
        "  Reversal Edge v2 OOS Chunk Runner Summary",
        "=" * 60,
        f"Run ID         : {run_id}",
        f"완료 시각      : {report['run_time']}",
        f"총 경과 시간   : {elapsed:.0f}초",
        f"계획 Chunk 수  : {total_chunks}",
        f"성공 Chunk 수  : {len(success_ids)}",
        f"실패 Chunk 수  : {len(failed_ids)}",
        "",
        "성공한 Chunk ID:",
        *[f"  - {cid}" for cid in success_ids],
        "",
        "실패한 Chunk ID:",
        *([f"  - {cid}" for cid in failed_ids] if failed_ids else ["  (없음)"]),
        "",
        "--- [안전 경고] ---",
        "※ 실거래 아님: 데이터 수집 전용이며 주문을 발생시키지 않습니다.",
        "※ config 자동 반영 금지: 수집 결과는 별도 분석 단계를 거쳐야 합니다.",
    ]
    try:
        with open(summary_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log(f"Summary TXT  → {summary_txt}")
    except Exception as e:
        log(f"  ⚠ Failed to write summary TXT: {e}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Resilient OOS chunk collector for Reversal Edge v2"
    )
    parser.add_argument("--duration-sec", type=int, default=86400,
                        help="Total collection duration in seconds (default: 86400 = 24h)")
    parser.add_argument("--chunk-sec", type=int, default=1800,
                        help="Duration per chunk in seconds (default: 1800 = 30min)")
    parser.add_argument("--output-dir", type=str,
                        default="logs/experiments/chunks",
                        help="Directory to store chunk .jsonl files")
    parser.add_argument("--summary-json", type=str,
                        default="reports/experiments/reversal_oos_chunk_runner_summary.json")
    parser.add_argument("--summary-txt", type=str,
                        default="reports/experiments/reversal_oos_chunk_runner_summary.txt")
    args = parser.parse_args()

    import uuid
    run_id = str(uuid.uuid4())[:8]
    start_wall = time.time()

    total_chunks = max(1, args.duration_sec // args.chunk_sec)
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.summary_json), exist_ok=True)

    manifest_path = os.path.join(args.output_dir, "reversal_oos_chunk_manifest.jsonl")
    existing = load_manifest(manifest_path)

    log(f"run_id={run_id}  duration={args.duration_sec}s  chunk={args.chunk_sec}s  total_chunks={total_chunks}")
    log(f"output_dir={args.output_dir}")
    log(f"manifest={manifest_path}")
    log("NOTE: No live orders. OOS data collection only.")

    success_ids = []
    failed_ids = []

    for i in range(1, total_chunks + 1):
        chunk_id = f"{i:04d}"
        chunk_path = os.path.join(args.output_dir, f"reversal_oos_chunk_{chunk_id}.jsonl")

        # ── 이미 성공한 chunk는 건너뜀
        if chunk_id in existing and existing[chunk_id].get("status") == "success":
            log(f"Chunk {chunk_id}/{total_chunks}  SKIP (already succeeded)")
            success_ids.append(chunk_id)
            continue

        # ── 수집 (최대 MAX_RETRY 회 재시도)
        ok = False
        for attempt in range(1, MAX_RETRY + 1):
            log(f"Chunk {chunk_id}/{total_chunks}  attempt {attempt}/{MAX_RETRY}")
            ok = run_collect_ws(chunk_path, args.chunk_sec)
            if ok:
                break
            if attempt < MAX_RETRY:
                log(f"  → failed. waiting {RETRY_WAIT_SEC}s before retry…")
                time.sleep(RETRY_WAIT_SEC)

        # ── manifest 기록
        rec = {
            "chunk_id": chunk_id,
            "chunk_path": chunk_path,
            "status": "success" if ok else "failed",
            "attempt": attempt,
            "ts": time.time(),
        }
        append_manifest(manifest_path, rec)

        if ok:
            log(f"  OK Chunk {chunk_id} succeeded")
            success_ids.append(chunk_id)
        else:
            log(f"  FAIL Chunk {chunk_id} FAILED after {MAX_RETRY} attempts")
            failed_ids.append(chunk_id)

    # ── 최종 summary
    log("=== All chunks processed. Writing summary… ===")
    build_summary(
        run_id=run_id,
        start_wall=start_wall,
        total_chunks=total_chunks,
        success_ids=success_ids,
        failed_ids=failed_ids,
        output_dir=args.output_dir,
        summary_json=args.summary_json,
        summary_txt=args.summary_txt,
    )
    log(f"Done. success={len(success_ids)}  failed={len(failed_ids)}")


if __name__ == "__main__":
    main()
