import os
import json
import sqlite3
from datetime import datetime

SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "cross_market_payload_quality_audit_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "cross_market_payload_quality_audit_latest.txt")

SAMPLE_COUNT = 500
KEYWORDS = {"binance", "btcusdt", "ethusdt", "solusdt", "xrpusdt", "dogeusdt", "usdt"}


def analyze_payload():
    if not os.path.exists(SQLITE_CACHE):
        return {"error": "DB not found", "exists": False}

    conn = sqlite3.connect(SQLITE_CACHE)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]

    if "events" not in tables:
        conn.close()
        return {"error": "No events table", "exists": True, "tables": tables}

    cur.execute("SELECT COUNT(*) FROM events")
    total_rows = cur.fetchone()[0]

    cur.execute("SELECT market, COUNT(*) as cnt FROM events GROUP BY market ORDER BY cnt DESC LIMIT 20")
    top_markets = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT MIN(ts), MAX(ts) FROM events")
    min_ts, max_ts = cur.fetchone()

    # Fast stratified sampling via rowid modulo -- avoids full-table LIKE scan
    cur.execute("SELECT MIN(rowid), MAX(rowid) FROM events")
    min_rid, max_rid = cur.fetchone()
    step = max(1, (max_rid - min_rid) // SAMPLE_COUNT)

    sample_rowids = list(range(min_rid, max_rid + 1, step))[:SAMPLE_COUNT]
    placeholders = ",".join("?" * len(sample_rowids))
    cur.execute(
        f"SELECT ts, market, event_type, raw_json FROM events WHERE rowid IN ({placeholders})",
        sample_rowids,
    )
    all_samples = cur.fetchall()
    conn.close()

    # Python-level keyword filter (no SQL scan needed)
    keyword_hits = [
        r for r in all_samples if any(k in (r[3] or "").lower() for k in KEYWORDS)
    ]

    classifications = {
        "REAL_BINANCE_TICKER": 0,
        "REAL_BINANCE_ORDERBOOK": 0,
        "REAL_BINANCE_TRADE": 0,
        "UPBIT_ONLY": 0,
        "METADATA_ONLY": 0,
        "TEXT_MENTION_ONLY": 0,
        "UNKNOWN": 0,
    }

    binance_symbols_found = set()
    btc_usdt_found = False
    real_binance_count = 0
    min_b_ts = float("inf")
    max_b_ts = 0.0

    for ts, market, event_type, raw_json_str in keyword_hits:
        try:
            payload = json.loads(raw_json_str) if raw_json_str else {}
        except Exception:
            classifications["UNKNOWN"] += 1
            continue

        is_real_binance = False

        if "bids" in payload and "asks" in payload and "lastUpdateId" in payload:
            classifications["REAL_BINANCE_ORDERBOOK"] += 1
            is_real_binance = True
        elif "price" in payload and "qty" in payload and "isBuyerMaker" in payload:
            classifications["REAL_BINANCE_TRADE"] += 1
            is_real_binance = True
        elif "symbol" in payload and "price" in payload and len(payload) < 5:
            classifications["REAL_BINANCE_TICKER"] += 1
            is_real_binance = True
        elif "orderbook_units" in payload:
            classifications["UPBIT_ONLY"] += 1
        elif "trade_price" in payload and "trade_volume" in payload:
            classifications["UPBIT_ONLY"] += 1
        elif isinstance(payload, dict) and any(k.startswith("meta") for k in payload):
            classifications["METADATA_ONLY"] += 1
        else:
            classifications["TEXT_MENTION_ONLY"] += 1

        if is_real_binance:
            real_binance_count += 1
            if ts and ts < min_b_ts:
                min_b_ts = ts
            if ts and ts > max_b_ts:
                max_b_ts = ts
            sym = payload.get("symbol", payload.get("s"))
            if sym:
                binance_symbols_found.add(str(sym))
                if str(sym).upper() == "BTCUSDT":
                    btc_usdt_found = True

    if min_b_ts == float("inf"):
        min_b_ts = None
        max_b_ts = None

    overlap_possible = False
    if min_b_ts and max_b_ts and min_ts and max_ts:
        if max_b_ts >= min_ts and min_b_ts <= max_ts:
            overlap_possible = True

    keyword_hit_rate = len(keyword_hits) / len(all_samples) if all_samples else 0
    estimated_keyword_rows = int(total_rows * keyword_hit_rate)

    judgement = "ONLY_TEXT_MENTION_FOUND"
    if len(keyword_hits) == 0:
        judgement = "BINANCE_COLLECTOR_REQUIRED"
    elif real_binance_count > 0:
        if estimated_keyword_rows < 1000:
            judgement = "BINANCE_DATA_TOO_SPARSE"
        else:
            judgement = "REAL_BINANCE_DATA_AVAILABLE"

    return {
        "exists": True,
        "total_rows": total_rows,
        "top_markets": top_markets,
        "db_ts_range": [min_ts, max_ts],
        "samples_total": len(all_samples),
        "keyword_hits_in_sample": len(keyword_hits),
        "estimated_keyword_rows_in_db": estimated_keyword_rows,
        "classifications": classifications,
        "real_binance_count": real_binance_count,
        "binance_symbols": sorted(binance_symbols_found),
        "btc_usdt_found": btc_usdt_found,
        "binance_ts_range": [min_b_ts, max_b_ts],
        "timestamp_overlap_possible": overlap_possible,
        "judgement": judgement,
    }


def main():
    print("Auditing Payload Quality (fast rowid-sample mode)...")
    res = analyze_payload()

    judgement = res.get("judgement", "PAYLOAD_AUDIT_FAILED")
    next_step = (
        "Implement Binance public data collector (WebSocket/REST) and "
        "align timestamps with Upbit KRW data."
    )
    if judgement == "REAL_BINANCE_DATA_AVAILABLE":
        next_step = "Proceed with Cross-Market Lead-Lag strategy using existing Binance data in DB."
    elif judgement == "BINANCE_DATA_TOO_SPARSE":
        next_step = "Supplement existing sparse Binance data with new Binance public data collector."

    res["next_recommended_step"] = next_step
    res["generated_at"] = datetime.now().isoformat()

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    lines = [
        "========================================================================",
        "  CROSS-MARKET PAYLOAD QUALITY AUDIT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  Determine whether raw_json contains real Binance market data or only text mentions",
        "========================================================================",
        f"Generated              : {res.get('generated_at')}",
        f"Target DB              : {SQLITE_CACHE}",
        f"Total Rows             : {res.get('total_rows', 0):,}",
        f"Samples (rowid-based)  : {res.get('samples_total', 0)}",
        f"Keyword Hits in Sample : {res.get('keyword_hits_in_sample', 0)}",
        f"Est. Keyword Rows in DB: {res.get('estimated_keyword_rows_in_db', 0):,}",
        "",
        "[ Classification Results (keyword-hit rows only) ]",
    ]

    for k, v in res.get("classifications", {}).items():
        lines.append(f"  - {k:<30}: {v}")

    lines.extend(
        [
            "",
            "[ Binance Data Details ]",
            f"  Real Binance Samples : {res.get('real_binance_count', 0)}",
            f"  BTCUSDT Found        : {res.get('btc_usdt_found', False)}",
            f"  Symbols Extracted    : {', '.join(res.get('binance_symbols', [])) or 'None'}",
            f"  TS Overlap w/ Upbit  : {res.get('timestamp_overlap_possible', False)}",
            "",
            "========================================================================",
            f"  JUDGEMENT : {judgement}",
            f"  NEXT STEP : {next_step}",
            "========================================================================",
        ]
    )

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Done. Judgement: {judgement}")


if __name__ == "__main__":
    main()
