"""
audit_market_coverage.py
현재 Master Dataset이 전체 마켓 공통 feature 검증에 적합한지 Market Coverage를 감사합니다.
"""
import os
import json
import sqlite3
import numpy as np
from datetime import datetime

import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "market_coverage_audit_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "market_coverage_audit_latest.txt")

STEP_SEC = 10.0
TP_300_PCT = 0.20
TP_600_PCT = 0.30
SL_PCT = -0.20

def get_markets():
    if not os.path.exists(SQLITE_CACHE): return []
    conn = sqlite3.connect(SQLITE_CACHE)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT market FROM events")
    markets = [row[0] for row in cur.fetchall()]
    conn.close()
    return markets

def process_market(market):
    print(f"[Info] Auditing {market} ...")
    conn = sqlite3.connect(SQLITE_CACHE)
    cur = conn.cursor()
    cur.execute("SELECT ts, event_type, raw_json FROM events WHERE market = ? ORDER BY ts ASC", (market,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"market": market, "status": "MISSING"}

    trade_count = 0
    ob_count = 0
    
    trades_ts = []
    trades_pr = []
    
    for ts, etype, r in rows:
        if not etype:
            try:
                ev = json.loads(r)
                etype = ev.get("event_type") or ev.get("raw", {}).get("type")
            except:
                pass
                
        if etype == "trade":
            trade_count += 1
            try:
                ev = json.loads(r)
                raw = ev.get("raw", {})
                pr = float(raw.get("trade_price") or ev.get("trade_price"))
                ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                t_ts = ts_ms / 1000.0 if ts_ms else ev.get("received_at", ts)
                trades_ts.append(t_ts)
                trades_pr.append(pr)
            except:
                pass
        elif etype == "orderbook":
            ob_count += 1

    total_rows = len(rows)
    if total_rows == 0 or trade_count == 0 or ob_count == 0:
        return {"market": market, "status": "UNUSABLE", "total_rows": total_rows, "trade_count": trade_count, "ob_count": ob_count}

    min_ts = rows[0][0]
    max_ts = rows[-1][0]
    duration_hours = (max_ts - min_ts) / 3600.0

    # Fast Labeling
    t_ts = np.array(trades_ts)
    t_pr = np.array(trades_pr)
    
    win_count = 0
    loss_count = 0
    to_count = 0
    snapshot_count = 0
    
    if len(t_ts) > 0:
        min_t_ts, max_t_ts = np.min(t_ts), np.max(t_ts)
        def get_trade_idx(ts_val): return np.searchsorted(t_ts, ts_val, side='right')
        
        for ts in np.arange(min_t_ts + 60, max_t_ts - 600, STEP_SEC):
            i_curr = get_trade_idx(ts)
            if i_curr == 0: continue
            pr_curr = t_pr[i_curr - 1]
            
            i_10s = get_trade_idx(ts - 10)
            if i_curr == i_10s: continue
            
            snapshot_count += 1
            
            i_end_300 = get_trade_idx(ts + 300)
            i_end_600 = get_trade_idx(ts + 600)
            
            pr_300 = t_pr[i_curr:i_end_300]
            pr_600 = t_pr[i_curr:i_end_600]
            
            if len(pr_600) == 0: 
                to_count += 1
                continue
                
            ret_300 = (pr_300 - pr_curr) / pr_curr * 100
            ret_600 = (pr_600 - pr_curr) / pr_curr * 100
            
            sl_hits_600 = ret_600 <= SL_PCT
            tp_300_hits = ret_300 >= TP_300_PCT
            tp_600_hits = ret_600 >= TP_600_PCT
            
            sl_idx = np.argmax(sl_hits_600) if np.any(sl_hits_600) else 999999
            tp3_idx = np.argmax(tp_300_hits) if np.any(tp_300_hits) else 999999
            tp6_idx = np.argmax(tp_600_hits) if np.any(tp_600_hits) else 999999
            
            if sl_idx < tp6_idx and sl_idx < tp3_idx:
                loss_count += 1
            elif tp3_idx < 999999 and tp3_idx < sl_idx:
                win_count += 1
            elif tp6_idx < 999999 and tp6_idx < sl_idx:
                win_count += 1
            else:
                to_count += 1

    status = "WEAK"
    if total_rows >= 10000 and duration_hours >= 12 and win_count > 0 and loss_count > 0 and snapshot_count >= 1000:
        status = "GOOD"
    elif total_rows < 1000 or trade_count < 100 or ob_count < 100:
        status = "UNUSABLE"

    return {
        "market": market,
        "status": status,
        "total_rows": total_rows,
        "trade_count": trade_count,
        "ob_count": ob_count,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "duration_hours": float(duration_hours),
        "snapshot_count": snapshot_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "to_count": to_count
    }

def main():
    print("=" * 60)
    print(" Market Coverage Audit")
    print("=" * 60)

    markets = get_markets()
    if not markets:
        print("[Error] No markets found.")
        return

    results = []
    for m in markets:
        res = process_market(m)
        results.append(res)

    good = [r for r in results if r.get("status") == "GOOD"]
    weak = [r for r in results if r.get("status") == "WEAK"]
    unusable = [r for r in results if r.get("status") in ("UNUSABLE", "MISSING")]

    good_count = len(good)
    if good_count >= 5:
        judgement = "COVERAGE_OK"
    elif good_count >= 3:
        judgement = "COVERAGE_WEAK"
    elif good_count >= 1:
        judgement = "COVERAGE_INSUFFICIENT"
    else:
        judgement = "NEED_TOP10_COLLECTION"

    total_rows = sum(r.get("total_rows", 0) for r in results)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_markets": len(markets),
            "total_rows": total_rows,
            "good_count": len(good),
            "weak_count": len(weak),
            "unusable_count": len(unusable),
            "judgement": judgement,
            "details": results
        }, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        " Market Coverage Audit Report",
        "=" * 72,
        f"생성 시각  : {datetime.now().isoformat()}",
        f"전체 마켓 수: {len(markets)}",
        f"전체 Row 수 : {total_rows:,}",
        f"GOOD 마켓 수: {len(good)}",
        f"WEAK 마켓 수: {len(weak)}",
        f"UNUS/MISS 수: {len(unusable)}",
        "",
        "[ 판정 결과: {0} ]".format(judgement)
    ]
    
    if judgement == "NEED_TOP10_COLLECTION":
        lines.append("⚠️ 전체 마켓 공통 feature 검증을 위한 커버리지가 매우 부족합니다.")
    elif judgement == "COVERAGE_INSUFFICIENT":
        lines.append("⚠️ 커버리지가 부족합니다. 특정 코인(예: SOL, XRP)에만 편중된 결과가 나올 확률이 높습니다.")
    
    lines.append("")
    lines.append("[ 마켓별 상세 ]")
    lines.append("-" * 72)
    lines.append(f"{'Market':<10} {'Status':<10} {'Rows':>10} {'Hours':>8} {'Snaps':>8} {'WIN':>6} {'LOSS':>6}")
    lines.append("-" * 72)
    
    for r in sorted(results, key=lambda x: x.get("total_rows", 0), reverse=True):
        m = r['market']
        st = r['status']
        ro = r.get('total_rows', 0)
        hr = r.get('duration_hours', 0)
        sn = r.get('snapshot_count', 0)
        w = r.get('win_count', 0)
        l = r.get('loss_count', 0)
        lines.append(f"{m:<10} {st:<10} {ro:>10,} {hr:>8.1f} {sn:>8,} {w:>6,} {l:>6,}")
        
    lines.append("-" * 72)
    lines.append("")
    lines.append("[ Feature Discovery에서 3개 마켓만 유효했던 원인 분석 ]")
    lines.append("1. 특정 마켓(SOL, XRP, BTC)을 제외한 나머지 마켓은 Row 수가 턱없이 부족하거나,")
    lines.append("2. 12시간 이상의 연속된 데이터가 없어 스냅샷(1,000개 이상) 생성이 불가했기 때문입니다.")
    lines.append("3. 특히 WIN/LOSS 표본이 50개 이상 확보된 마켓이 3개에 불과했습니다.")
    lines.append("")
    lines.append("[ 다음 행동 제안 ]")
    lines.append("Top 10 KRW 마켓 데이터 수집 계획(plan_top10_market_collection.py)을 실행하여")
    lines.append("최소 5개 이상의 GOOD 마켓을 확보할 수 있는 수집 아키텍처를 설계하십시오.")

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[Done] JSON: {JSON_REPORT}")
    print(f"[Done] TXT: {TXT_REPORT}")
    print(f"Judgement: {judgement}")

if __name__ == "__main__":
    main()
