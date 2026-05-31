import os
import json
import sqlite3
import requests
from datetime import datetime

SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "cross_market_data_availability_audit_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "cross_market_data_availability_audit_latest.txt")

def check_sqlite(db_path):
    if not os.path.exists(db_path):
        return {"exists": False}
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    
    if "events" not in tables:
        return {"exists": True, "tables": tables, "events_table": False}
        
    cur.execute("PRAGMA table_info(events)")
    cols = [r[1] for r in cur.fetchall()]
    
    cur.execute("SELECT COUNT(*) FROM events")
    total_rows = cur.fetchone()[0]
    
    cur.execute("SELECT DISTINCT market FROM events LIMIT 100")
    markets = [r[0] for r in cur.fetchall()]
    
    has_binance_market = any("USDT" in m or "BINANCE" in m.upper() for m in markets)
    
    event_types = []
    if "event_type" in cols:
        cur.execute("SELECT DISTINCT event_type FROM events LIMIT 50")
        event_types = [r[0] for r in cur.fetchall()]
        
    binance_keywords_found = False
    if "raw_json" in cols:
        cur.execute("SELECT raw_json FROM events LIMIT 50")
        for row in cur.fetchall():
            text = str(row[0]).lower()
            if "binance" in text or "usdt" in text or "btcusdt" in text or "source" in text or "exchange" in text:
                binance_keywords_found = True
                break
                
    cur.execute("SELECT MIN(ts), MAX(ts) FROM events")
    min_ts, max_ts = cur.fetchone()
    
    cur.execute("SELECT market, COUNT(*) as cnt FROM events GROUP BY market ORDER BY cnt DESC LIMIT 20")
    market_counts = {r[0]: r[1] for r in cur.fetchall()}
    
    conn.close()
    return {
        "exists": True,
        "tables": tables,
        "events_table": True,
        "total_rows": total_rows,
        "markets": markets,
        "has_binance_market": has_binance_market,
        "event_types": event_types,
        "binance_keywords_in_json": binance_keywords_found,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "top_market_counts": market_counts
    }

def get_mapping(markets):
    mappings = []
    for m in markets:
        if m.startswith("KRW-"):
            base = m.split("-")[1]
            binance_sym = base + "USDT"
            mappings.append({
                "upbit_market": m,
                "base_symbol": base,
                "binance_symbol_candidate": binance_sym,
                "mapping_status": "LIKELY_AVAILABLE"
            })
    return mappings

def check_binance_api():
    res1 = {"endpoint": "ticker/price?symbol=BTCUSDT", "success": False, "error": None}
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
        if r.status_code == 200:
            res1["success"] = True
        else:
            res1["error"] = f"HTTP {r.status_code}"
    except Exception as e:
        res1["error"] = str(e)
        
    res2 = {"endpoint": "depth?symbol=BTCUSDT&limit=5", "success": False, "error": None}
    try:
        r = requests.get("https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=5", timeout=5)
        if r.status_code == 200:
            res2["success"] = True
        else:
            res2["error"] = f"HTTP {r.status_code}"
    except Exception as e:
        res2["error"] = str(e)
        
    return [res1, res2]

def main():
    print("Auditing DB...")
    db_info = check_sqlite(SQLITE_CACHE)
    
    print("Generating Mappings...")
    mappings = get_mapping(db_info.get("markets", []))
    
    print("Testing Binance API...")
    api_results = check_binance_api()
    api_success = all(r["success"] for r in api_results)
    
    if db_info.get("has_binance_market") or db_info.get("binance_keywords_in_json"):
        if any("USDT" in m for m in db_info.get("markets", [])):
            judgement = "BINANCE_DATA_ALREADY_AVAILABLE"
        else:
            judgement = "PARTIAL_CROSS_MARKET_DATA_AVAILABLE"
    else:
        judgement = "NO_CROSS_MARKET_DATA_FOUND"
        
    if judgement == "NO_CROSS_MARKET_DATA_FOUND" and api_success:
        judgement = "BINANCE_PUBLIC_COLLECTOR_NEEDED"
    elif judgement == "NO_CROSS_MARKET_DATA_FOUND" and not api_success:
        judgement = "AUDIT_FAILED"
        
    next_step = "Implement Binance public data collector for orderbook/trade synchronization." if "NEEDED" in judgement else "Analyze existing Binance data."
    if "FAILED" in judgement:
        next_step = "Fix Binance API connection issues."
        
    report = {
        "generated_at": datetime.now().isoformat(),
        "db_info": db_info,
        "market_mappings": mappings,
        "api_test_results": api_results,
        "judgement": judgement,
        "next_recommended_step": next_step
    }
    
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    lines = [
        "========================================================================",
        "  CROSS-MARKET DATA AVAILABILITY AUDIT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  Binance public market data does not require trading API key",
        "========================================================================",
        f"Generated            : {report['generated_at']}",
        f"Target DB            : {SQLITE_CACHE}",
        f"DB Exists            : {db_info.get('exists')}",
        f"Total Rows           : {db_info.get('total_rows', 0)}",
        f"Has Binance Data     : {db_info.get('has_binance_market', False)}",
        f"Has Binance Keywords : {db_info.get('binance_keywords_in_json', False)}",
        "",
        "[ Binance API Test ]"
    ]
    
    for r in api_results:
        lines.append(f"  - {r['endpoint']} : {'SUCCESS' if r['success'] else 'FAILED (' + str(r['error']) + ')'}")
        
    lines.extend([
        "",
        "[ Market Mapping ]",
        f"  Mappable Markets   : {len(mappings)}"
    ])
    for m in mappings[:10]:
        lines.append(f"  - {m['upbit_market']} -> {m['binance_symbol_candidate']} ({m['mapping_status']})")
    if len(mappings) > 10:
        lines.append("  ... (truncated)")
        
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
