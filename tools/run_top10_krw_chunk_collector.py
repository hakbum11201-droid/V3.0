"""
run_top10_krw_chunk_collector.py
Top 10 KRW 마켓 72시간 30분 단위 분할 수집(Chunk Collector) 스크립트.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

MAX_RETRY = 3
RETRY_WAIT_SEC = 10

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[Chunk] {ts}  {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[Chunk] {ts}  {msg}".encode("ascii", errors="replace").decode(), flush=True)

def fetch_top10_markets():
    """업비트 공개 API를 사용하여 24시간 거래대금 상위 10개 KRW 마켓 조회"""
    try:
        # 1. 모든 KRW 마켓 조회 (유의종목 제외 옵션 가능하지만, 거래대금 상위면 보통 정상)
        req = urllib.request.Request('https://api.upbit.com/v1/market/all?isDetails=true')
        with urllib.request.urlopen(req) as res:
            markets_info = json.loads(res.read())
            
        # 정상 마켓만 필터링
        active_krw_markets = []
        excluded_markets = {"KRW-USDT", "KRW-USDC", "KRW-DAI"}
        for m in markets_info:
            market_name = m['market']
            if market_name.startswith('KRW-') and not m.get('market_event', {}).get('warning', False):
                if market_name not in excluded_markets:
                    active_krw_markets.append(market_name)
                
        # 2. Ticker 조회하여 거래대금(acc_trade_price_24h) 정렬
        chunked_markets = [active_krw_markets[i:i+50] for i in range(0, len(active_krw_markets), 50)]
        all_tickers = []
        for chunk in chunked_markets:
            req2 = urllib.request.Request(f"https://api.upbit.com/v1/ticker?markets={','.join(chunk)}")
            with urllib.request.urlopen(req2) as res2:
                all_tickers.extend(json.loads(res2.read()))
                
        sorted_tickers = sorted(all_tickers, key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)
        top10 = [t['market'] for t in sorted_tickers[:10]]
        return top10
    except Exception as e:
        log(f"⚠ Top 10 마켓 조회 실패: {e}")
        return []

def load_manifest(manifest_path: str):
    """Manifest 로드 (선정된 마켓 목록 및 청크 이력 반환)"""
    records = {}
    selected_markets = []
    if not os.path.exists(manifest_path):
        return records, selected_markets
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    if "selected_markets" in rec:
                        selected_markets = rec["selected_markets"]
                    elif "chunk_id" in rec:
                        records[rec["chunk_id"]] = rec
                except Exception:
                    pass
    return records, selected_markets

def append_manifest(manifest_path: str, record: dict):
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

def create_temp_config(original_config_path: str, temp_config_path: str, target_markets: list):
    """선정된 Top 10 마켓만 대상(target_markets)으로 하는 임시 config 생성"""
    with open(original_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    config["markets"] = target_markets
    
    with open(temp_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def run_collect_ws(chunk_path: str, seconds: int, config_path: str) -> bool:
    cmd = [
        sys.executable, "-m", "coinb.main",
        "collect-ws",
        "--config", config_path,
        "--seconds", str(seconds),
        "--output", chunk_path,
    ]
    log(f"collect-ws → {chunk_path}  ({seconds}s)")
    try:
        result = subprocess.run(cmd, timeout=seconds + 60)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("  ⚠ collect-ws timed out")
        return False
    except Exception as e:
        log(f"  ⚠ collect-ws exception: {e}")
        return False

def build_summary(
    run_id: str, start_wall: float, total_chunks: int,
    success_ids: list, failed_ids: list, selected_markets: list,
    output_dir: str, summary_json: str, summary_txt: str
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
        "selected_markets": selected_markets,
        "excluded_market_reasons": {
            "KRW-USDT": "stablecoin_or_fx_like_market_excluded",
            "KRW-USDC": "stablecoin_or_fx_like_market_excluded",
            "KRW-DAI": "stablecoin_or_fx_like_market_excluded"
        },
        "success_chunk_ids": success_ids,
        "failed_chunk_ids": failed_ids,
        "output_dir": output_dir,
        "live_orders_placed": 0,
    }

    try:
        os.makedirs(os.path.dirname(summary_json), exist_ok=True)
        with open(summary_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log(f"Summary JSON → {summary_json}")
    except Exception as e:
        log(f"  ⚠ Failed to write summary JSON: {e}")

    lines = [
        "=" * 60,
        "  Top 10 KRW Chunk Collector Summary",
        "=" * 60,
        f"Run ID         : {run_id}",
        f"완료 시각      : {report['run_time']}",
        f"총 경과 시간   : {elapsed:.0f}초",
        f"대상 마켓      : {selected_markets}",
        "제외된 마켓    : KRW-USDT, KRW-USDC, KRW-DAI (사유: stablecoin_or_fx_like_market_excluded)",
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
        "※ 수집 결과는 마스터 데이터셋 구축 파이프라인을 거쳐야 합니다.",
    ]
    try:
        with open(summary_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        log(f"Summary TXT  → {summary_txt}")
    except Exception as e:
        log(f"  ⚠ Failed to write summary TXT: {e}")

    return report

def main():
    parser = argparse.ArgumentParser(description="Top 10 KRW chunk collector")
    parser.add_argument("--duration-sec", type=int, default=259200, help="Total collection duration in seconds (72h)")
    parser.add_argument("--chunk-sec", type=int, default=1800, help="Duration per chunk in seconds (30m)")
    parser.add_argument("--output-dir", type=str, default="logs/experiments/top10_krw_72h_chunks", help="Output dir")
    args = parser.parse_args()

    import uuid
    run_id = str(uuid.uuid4())[:8]
    start_wall = time.time()

    total_chunks = max(1, args.duration_sec // args.chunk_sec)
    os.makedirs(args.output_dir, exist_ok=True)
    
    summary_json = os.path.join("reports/experiments", "top10_krw_chunk_collector_summary.json")
    summary_txt = os.path.join("reports/experiments", "top10_krw_chunk_collector_summary.txt")
    manifest_path = os.path.join(args.output_dir, "top10_krw_chunk_manifest.jsonl")
    temp_config_path = os.path.join(args.output_dir, "temp_config_top10.json")

    existing_chunks, selected_markets = load_manifest(manifest_path)

    if not selected_markets:
        log("No markets found in manifest. Fetching Top 10 from Upbit...")
        selected_markets = fetch_top10_markets()
        if not selected_markets:
            log("⚠ Could not fetch markets. Aborting.")
            return
        # Save to manifest
        append_manifest(manifest_path, {"selected_markets": selected_markets, "ts": time.time()})
    else:
        log(f"Loaded Top 10 markets from manifest.")

    log(f"Target Markets: {selected_markets}")
    create_temp_config("config/config.json", temp_config_path, selected_markets)

    log(f"run_id={run_id} duration={args.duration_sec}s chunk={args.chunk_sec}s total_chunks={total_chunks}")
    log("NOTE: No live orders. Public OOS data collection only.")

    success_ids = []
    failed_ids = []

    for i in range(1, total_chunks + 1):
        chunk_id = f"{i:04d}"
        chunk_path = os.path.join(args.output_dir, f"top10_krw_chunk_{chunk_id}.jsonl")

        if chunk_id in existing_chunks and existing_chunks[chunk_id].get("status") == "success":
            log(f"Chunk {chunk_id}/{total_chunks}  SKIP (already succeeded)")
            success_ids.append(chunk_id)
            continue

        ok = False
        for attempt in range(1, MAX_RETRY + 1):
            log(f"Chunk {chunk_id}/{total_chunks}  attempt {attempt}/{MAX_RETRY}")
            ok = run_collect_ws(chunk_path, args.chunk_sec, temp_config_path)
            if ok:
                break
            if attempt < MAX_RETRY:
                log(f"  → failed. waiting {RETRY_WAIT_SEC}s before retry…")
                time.sleep(RETRY_WAIT_SEC)

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

    log("=== All chunks processed. Writing summary… ===")
    build_summary(
        run_id, start_wall, total_chunks, success_ids, failed_ids, selected_markets,
        args.output_dir, summary_json, summary_txt
    )
    
    # Cleanup temp config
    try:
        os.remove(temp_config_path)
    except:
        pass
        
    log(f"Done. success={len(success_ids)} failed={len(failed_ids)}")

if __name__ == "__main__":
    main()
