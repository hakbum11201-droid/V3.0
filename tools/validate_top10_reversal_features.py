"""
validate_top10_reversal_features.py
Top 10 KRW 마켓 대상 빠른 샘플링 기반 1차 리포트 생성기.

Mode: fast_sampling
- SQLite full-scan / ORDER BY RANDOM() 금지
- 마켓당 최대 3,000 rows (rowid 간격 샘플링)
- Reversal 수익성 판단 없음
- 항상 JSON/TXT 리포트 저장 후 종료
"""
import os
import json
import sqlite3
from datetime import datetime

# ─────────────────────────────────────────────
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "top10_reversal_feature_validation_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "top10_reversal_feature_validation_latest.txt")

SAMPLE_LIMIT = 3000   # rows per market
MIN_GOOD_MARKETS = 5
MIN_GOOD_FOR_READY = 5   # need >= 5 good markets with data to call READY
GOOD_MIN_ROWS = 10000
GOOD_MIN_HOURS = 12.0
GOOD_MIN_TRADE = 100
GOOD_MIN_OB = 100
# ─────────────────────────────────────────────


def db_connect():
    conn = sqlite3.connect(SQLITE_CACHE)
    conn.row_factory = sqlite3.Row
    return conn


def get_markets(conn):
    cur = conn.execute("SELECT DISTINCT market FROM events")
    return [r[0] for r in cur.fetchall()]


def fast_audit(conn, market):
    """
    rowid 기반 간격 샘플링으로 market의 기초 통계를 빠르게 계산한다.
    """
    # 1. market의 min/max rowid 확인 (인덱스 우선 활용)
    cur = conn.execute(
        "SELECT MIN(rowid), MAX(rowid), COUNT(*) FROM events WHERE market = ?",
        (market,),
    )
    row = cur.fetchone()
    if row is None or row[2] == 0:
        return {"market": market, "status": "MISSING", "total_rows": 0}

    min_rid, max_rid, total_rows = row[0], row[1], row[2]

    # 2. rowid 간격 계산 → SAMPLE_LIMIT개 샘플
    if total_rows <= SAMPLE_LIMIT:
        step = 1
    else:
        step = max(1, (max_rid - min_rid) // SAMPLE_LIMIT)

    # 3. 간격 샘플링: rowid % step == 0 또는 LIMIT 제한
    cur = conn.execute(
        """
        SELECT ts, event_type, raw_json
        FROM events
        WHERE market = ?
          AND rowid >= ?
          AND rowid <= ?
          AND (rowid - ?) % ? = 0
        LIMIT ?
        """,
        (market, min_rid, max_rid, min_rid, step, SAMPLE_LIMIT),
    )
    sample_rows = cur.fetchall()

    rows_checked = len(sample_rows)
    if rows_checked == 0:
        return {"market": market, "status": "UNUSABLE", "total_rows": total_rows}

    ts_list = []
    etype_counts: dict = {}
    trade_count = 0
    ob_count = 0

    for r in sample_rows:
        ts_val = r["ts"] if r["ts"] else None
        etype = r["event_type"] or "unknown"

        if ts_val:
            ts_list.append(float(ts_val))
        etype_counts[etype] = etype_counts.get(etype, 0) + 1
        if etype == "trade":
            trade_count += 1
        elif etype == "orderbook":
            ob_count += 1

    if not ts_list:
        return {"market": market, "status": "UNUSABLE", "total_rows": total_rows}

    min_ts = min(ts_list)
    max_ts = max(ts_list)
    duration_hours = (max_ts - min_ts) / 3600.0

    # Scale up counts proportionally
    scale = total_rows / rows_checked if rows_checked > 0 else 1.0
    est_trade = int(trade_count * scale)
    est_ob = int(ob_count * scale)

    # GOOD 판정
    if (
        total_rows >= GOOD_MIN_ROWS
        and duration_hours >= GOOD_MIN_HOURS
        and est_trade >= GOOD_MIN_TRADE
        and est_ob >= GOOD_MIN_OB
    ):
        status = "GOOD"
    elif total_rows < 1000 or (trade_count == 0 and ob_count == 0):
        status = "UNUSABLE"
    else:
        status = "WEAK"

    return {
        "market": market,
        "status": status,
        "total_rows": total_rows,
        "rows_checked": rows_checked,
        "sample_limit": SAMPLE_LIMIT,
        "scale_factor": round(scale, 2),
        "event_type_counts_in_sample": etype_counts,
        "est_trade_total": est_trade,
        "est_ob_total": est_ob,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "duration_hours": round(duration_hours, 2),
    }


def save_reports(result: dict):
    os.makedirs(OUT_DIR, exist_ok=True)

    # JSON
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # TXT (UTF-8, no broken chars)
    per = result.get("per_market_summary", [])
    warns = result.get("warnings", [])
    lines = [
        "=" * 72,
        " Top 10 Reversal Feature Validation Report  [fast_sampling mode]",
        "=" * 72,
        f"Generated      : {result['generated_at']}",
        f"Mode           : {result.get('mode', 'fast_sampling')}",
        f"Sample limit   : {result.get('sample_limit_per_market', SAMPLE_LIMIT)} rows/market",
        f"Judgement      : {result['judgement']}",
        f"GOOD  markets  : {result['good_markets_count']}  {result['good_markets']}",
        f"WEAK  markets  : {len(result.get('weak_markets', []))}  {result.get('weak_markets', [])}",
        f"UNUSABLE/MISS  : {len(result.get('unusable_markets', []))}  {result.get('unusable_markets', [])}",
        "",
        "[ Per-Market Sampling Summary ]",
        "-" * 72,
        f"{'Market':<14} {'Status':<10} {'TotalRows':>10} {'Checked':>8} {'Hours':>7} {'EstTrade':>10} {'EstOB':>10}",
        "-" * 72,
    ]
    for pm in per:
        m = pm.get("market", "?")
        st = pm.get("status", "?")
        tr = pm.get("total_rows", 0)
        ch = pm.get("rows_checked", 0)
        hr = pm.get("duration_hours", 0.0)
        et = pm.get("est_trade_total", 0)
        eo = pm.get("est_ob_total", 0)
        lines.append(f"{m:<14} {st:<10} {tr:>10,} {ch:>8,} {hr:>7.1f} {et:>10,} {eo:>10,}")
    lines.append("-" * 72)

    if warns:
        lines += ["", "[ Warnings ]"] + [f"  ! {w}" for w in warns]

    lines += [
        "",
        f"[ Next Action ]",
        f"  {result.get('next_action', 'N/A')}",
        "",
        "NOTE: This is a fast sampling report only.",
        "      No config / candidate / live files were modified.",
    ]

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")
    print(f"Judgement   : {result['judgement']}")


def main():
    print("=" * 60)
    print(" Top 10 Reversal Feature Validation  [fast_sampling]")
    print("=" * 60)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite cache not found: {SQLITE_CACHE}")
        return

    conn = db_connect()

    markets = get_markets(conn)
    if not markets:
        print("[Error] No markets found in SQLite cache.")
        conn.close()
        return

    print(f"[Info] Total markets in DB: {len(markets)}")

    good_markets = []
    weak_markets = []
    unusable_markets = []
    per_market_summary = []
    warnings = []

    for i, m in enumerate(markets):
        print(f"[Info] Sampling {m} ({i+1}/{len(markets)}) ...", end=" ", flush=True)
        try:
            res = fast_audit(conn, m)
            per_market_summary.append(res)
            st = res.get("status", "MISSING")
            if st == "GOOD":
                good_markets.append(m)
                print(f"GOOD  ({res.get('total_rows',0):,} rows, {res.get('duration_hours',0):.1f}h)")
            elif st == "WEAK":
                weak_markets.append(m)
                print(f"WEAK  ({res.get('total_rows',0):,} rows)")
            else:
                unusable_markets.append(m)
                print(f"UNUSABLE ({res.get('total_rows',0):,} rows)")
        except Exception as ex:
            warnings.append(f"{m}: audit error - {ex}")
            unusable_markets.append(m)
            print(f"ERROR: {ex}")

    conn.close()

    good_count = len(good_markets)
    print(f"\n[Info] GOOD: {good_count}  WEAK: {len(weak_markets)}  UNUSABLE: {len(unusable_markets)}")

    # ── COVERAGE INSUFFICIENT ──────────────────────────────────────────────
    if good_count < MIN_GOOD_MARKETS:
        judgement = "TOP10_COVERAGE_INSUFFICIENT"
        next_action = (
            "GOOD markets insufficient for cross-market feature validation. "
            "Run RUN_TOP10_KRW_CHUNK_COLLECTOR_72H.bat to collect more data, "
            "rebuild the master dataset, then re-run this tool."
        )
    elif good_count >= MIN_GOOD_FOR_READY:
        judgement = "TOP10_SAMPLE_REPORT_READY"
        next_action = (
            "Sampling complete. Enough GOOD markets found. "
            "Proceed to RUN_DISCOVER_CROSS_MARKET_REVERSAL_FEATURES.bat "
            "for deeper feature analysis."
        )
    else:
        judgement = "TOP10_SAMPLE_REPORT_WEAK"
        next_action = (
            "Some GOOD markets found but coverage is borderline. "
            "Consider collecting more data before promoting any candidate."
        )

    result = {
        "generated_at": datetime.now().isoformat(),
        "mode": "fast_sampling",
        "sample_limit_per_market": SAMPLE_LIMIT,
        "good_markets_count": good_count,
        "good_markets": good_markets,
        "weak_markets": weak_markets,
        "unusable_markets": unusable_markets,
        "per_market_summary": per_market_summary,
        "judgement": judgement,
        "warnings": warnings,
        "next_action": next_action,
    }

    save_reports(result)


if __name__ == "__main__":
    main()
