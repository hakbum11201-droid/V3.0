import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import product

# Config
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "multi_signal_price_path_comparison_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "multi_signal_price_path_comparison_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
SLIPPAGE_CANDS = [0.03, 0.05, 0.10]

TP_CANDS = [0.15, 0.20, 0.25, 0.30, 0.40]
SL_CANDS = [-0.08, -0.10, -0.15, -0.20]
TO_CANDS = [120, 180, 300, 450, 600]

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_ENTRIES_PER_MARKET_PER_SIGNAL = 1000
ENTRY_COOLDOWN_SEC = 60.0

def _get_schema_mode(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(events)")
    cols = [row[1] for row in cur.fetchall()]
    return "direct_columns" if "price" in cols else "raw_json"

def _load_window(conn, market, t_start, t_end, mode):
    cur = conn.cursor()
    if mode == "direct_columns":
        cur.execute(
            "SELECT ts, price, qty, is_buy FROM events "
            "WHERE market=? AND ts >= ? AND ts <= ? ORDER BY ts ASC",
            (market, t_start, t_end)
        )
    else:
        cur.execute(
            "SELECT ts, raw_json FROM events "
            "WHERE market=? AND ts >= ? AND ts <= ? ORDER BY ts ASC",
            (market, t_start, t_end)
        )
    return cur.fetchall()

def _parse_rows(rows, mode, market):
    if not rows:
        return None
    t_ts_list, t_pr_list, t_qty_list, t_is_buy_list = [], [], [], []
    o_ts_list, o_pr_list, o_bsz_list, o_asz_list = [], [], [], []

    if mode == "direct_columns":
        for r in rows:
            t_ts_list.append(float(r[0]))
            t_pr_list.append(float(r[1]))
            t_qty_list.append(float(r[2]))
            t_is_buy_list.append(int(r[3]))
    else:
        for r in rows:
            ts = float(r[0])
            try:
                obj = json.loads(r[1]) if isinstance(r[1], str) else r[1]
                if isinstance(obj, str):
                    obj = json.loads(obj)
            except Exception:
                continue

            payload = obj.get("raw", obj)
            if not isinstance(payload, dict):
                payload = obj
                
            et = obj.get("event_type") or payload.get("type")

            if et == "orderbook":
                units = payload.get("orderbook_units", [])
                if units and len(units) > 0:
                    try:
                        ap = float(units[0]["ask_price"])
                        bp = float(units[0]["bid_price"])
                        a_sz = float(units[0]["ask_size"])
                        b_sz = float(units[0]["bid_size"])
                        pr = (ap + bp) / 2.0
                        o_ts_list.append(ts)
                        o_pr_list.append(pr)
                        o_bsz_list.append(b_sz)
                        o_asz_list.append(a_sz)
                    except Exception:
                        pass
            else:
                pr = None
                tp_val = payload.get("trade_price")
                if tp_val is None: tp_val = payload.get("price")
                
                if tp_val is not None:
                    try: pr = float(tp_val)
                    except Exception: pass

                if pr is not None:
                    q_val = payload.get("trade_volume")
                    if q_val is None: q_val = payload.get("volume")
                    if q_val is None: q_val = payload.get("qty")
                    try: qty = float(q_val) if q_val is not None else 0.0
                    except Exception: qty = 0.0

                    side_val = payload.get("ask_bid")
                    if side_val is None: side_val = payload.get("trade_side")
                    if side_val is None: side_val = payload.get("side")
                    
                    side_str = str(side_val).upper() if side_val is not None else ""
                    if side_str in ("BID", "1", "BUY", "TRUE"): is_buy = 1
                    elif side_str in ("ASK", "0", "SELL", "FALSE", "-1"): is_buy = 0
                    else: is_buy = -1

                    t_ts_list.append(ts)
                    t_pr_list.append(pr)
                    t_qty_list.append(qty)
                    t_is_buy_list.append(is_buy)

    if not t_ts_list:
        return None

    t_sort = np.argsort(t_ts_list)
    o_sort = np.argsort(o_ts_list) if o_ts_list else []

    return {
        "t_ts": np.array(t_ts_list, dtype=float)[t_sort],
        "t_pr": np.array(t_pr_list, dtype=float)[t_sort],
        "t_qty": np.array(t_qty_list, dtype=float)[t_sort],
        "t_is_buy": np.array(t_is_buy_list, dtype=int)[t_sort],
        "o_ts": np.array(o_ts_list, dtype=float)[o_sort] if len(o_ts_list) > 0 else np.array([]),
        "o_pr": np.array(o_pr_list, dtype=float)[o_sort] if len(o_pr_list) > 0 else np.array([]),
        "o_bsz": np.array(o_bsz_list, dtype=float)[o_sort] if len(o_bsz_list) > 0 else np.array([]),
        "o_asz": np.array(o_asz_list, dtype=float)[o_sort] if len(o_asz_list) > 0 else np.array([])
    }

def _evaluate_future(entry_pr, entry_ts, f_ts, f_pr, tp_list, sl_list, to_list):
    results = {}
    if len(f_pr) == 0:
        for tp in tp_list:
            for sl in sl_list:
                for to in to_list:
                    results[(tp, sl, to)] = {"res": "TIMEOUT", "pnl": 0.0}
        return results

    returns = (f_pr - entry_pr) / entry_pr * 100.0

    tp_hits = {}
    for tp in tp_list:
        mask = returns >= tp
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        tp_hits[tp] = f_ts[idx] if idx >= 0 else np.inf

    sl_hits = {}
    for sl in sl_list:
        mask = returns <= sl
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        sl_hits[sl] = f_ts[idx] if idx >= 0 else np.inf

    for tp in tp_list:
        for sl in sl_list:
            for to in to_list:
                t_tp = tp_hits[tp]
                t_sl = sl_hits[sl]
                limit_ts = entry_ts + to

                hit_tp = t_tp <= limit_ts
                hit_sl = t_sl <= limit_ts

                if hit_tp and hit_sl:
                    if t_tp < t_sl:
                        res, pnl = "WIN", tp
                    else:
                        res, pnl = "LOSS", sl
                elif hit_tp:
                    res, pnl = "WIN", tp
                elif hit_sl:
                    res, pnl = "LOSS", sl
                else:
                    res = "TIMEOUT"
                    idx = np.searchsorted(f_ts, limit_ts, side='right') - 1
                    if idx < 0: idx = 0
                    pnl = returns[idx] if idx < len(returns) else 0.0

                results[(tp, sl, to)] = {"res": res, "pnl": float(pnl)}
    return results

def process_market(conn, market, mode):
    print(f"  [{market}] Extracting snapshots across {N_BANDS} bands ...")
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None:
        return {}

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to:
        return {}

    band_starts = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    
    snapshots = []
    
    for w_start in band_starts:
        w_end = min(w_start + win_sec, max_ts)
        rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
        arrs = _parse_rows(rows, mode, market)
        if not arrs: continue

        t_ts, t_pr, t_qty, t_is_buy = arrs["t_ts"], arrs["t_pr"], arrs["t_qty"], arrs["t_is_buy"]
        o_ts, o_pr, o_bsz, o_asz = arrs["o_ts"], arrs["o_pr"], arrs["o_bsz"], arrs["o_asz"]
        
        def gidx(v): return np.searchsorted(t_ts, v, side="right")
        def ogidx(v): return np.searchsorted(o_ts, v, side="right") if len(o_ts) > 0 else 0

        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - max_to, STEP_SEC):
            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            pr_curr = t_pr[i_curr - 1]
            ts_curr = t_ts[i_curr - 1]

            if i_curr == gidx(snap_ts - 10): continue

            i_10s = gidx(snap_ts - 10)
            i_30s = gidx(snap_ts - 30)
            i_60s = gidx(snap_ts - 60)

            pr_10s = t_pr[i_10s] if i_10s < len(t_pr) else pr_curr
            pr_30s = t_pr[i_30s] if i_30s < len(t_pr) else pr_curr
            pr_60s = t_pr[i_60s] if i_60s < len(t_pr) else pr_curr

            ret_10s = float((pr_curr - pr_10s) / pr_10s * 100.0) if pr_10s > 0 else 0.0
            ret_30s = float((pr_curr - pr_30s) / pr_30s * 100.0) if pr_30s > 0 else 0.0
            ret_60s = float((pr_curr - pr_60s) / pr_60s * 100.0) if pr_60s > 0 else 0.0

            def get_pressure(idx_start):
                qty_win = t_qty[idx_start:i_curr]
                buy_win = t_is_buy[idx_start:i_curr]
                b_vol = np.sum(qty_win[buy_win == 1])
                s_vol = np.sum(qty_win[buy_win == 0])
                return b_vol, s_vol
                
            b_10, s_10 = get_pressure(i_10s)
            b_30, s_30 = get_pressure(i_30s)
            
            spr_10s = float(s_10 / (b_10 + s_10 + 1e-8))
            spr_30s = float(s_30 / (b_30 + s_30 + 1e-8))
            bpr_10s = float(b_10 / (b_10 + s_10 + 1e-8))
            
            ob_imb = 0.5
            bid_depth_change_30s = 1.0
            if len(o_ts) > 0:
                oi_curr = ogidx(snap_ts) - 1
                if oi_curr >= 0:
                    bsz_curr = o_bsz[oi_curr]
                    asz_curr = o_asz[oi_curr]
                    ob_imb = float(bsz_curr / (bsz_curr + asz_curr + 1e-8))
                    
                    oi_30s = ogidx(snap_ts - 30) - 1
                    if oi_30s >= 0:
                        bsz_old = o_bsz[oi_30s]
                        if bsz_old > 0:
                            bid_depth_change_30s = float(bsz_curr / bsz_old)
                        else:
                            bid_depth_change_30s = 1.0

            snapshots.append({
                "ts": ts_curr,
                "pr": pr_curr,
                "arrs": arrs,
                "feats": {
                    "ret_10s": ret_10s, "ret_30s": ret_30s, "ret_60s": ret_60s,
                    "spr_10s": spr_10s, "spr_30s": spr_30s, "bpr_10s": bpr_10s,
                    "ob_imb": ob_imb, "bid_depth_change_30s": bid_depth_change_30s
                }
            })

    if not snapshots: return {}
    
    print(f"    -> Collected {len(snapshots)} valid snapshots. Calculating percentiles...")

    feats_dict = defaultdict(list)
    for s in snapshots:
        for k, v in s["feats"].items():
            feats_dict[k].append(v)
            
    p = {}
    for k, v in feats_dict.items():
        arr = np.array(v)
        p[f"{k}_p10"] = np.percentile(arr, 10)
        p[f"{k}_p15"] = np.percentile(arr, 15)
        p[f"{k}_p35"] = np.percentile(arr, 35)
        p[f"{k}_p50"] = np.percentile(arr, 50)
        p[f"{k}_p55"] = np.percentile(arr, 55)
        p[f"{k}_p60"] = np.percentile(arr, 60)
        p[f"{k}_p70"] = np.percentile(arr, 70)
        p[f"{k}_p75"] = np.percentile(arr, 75)
        p[f"{k}_p85"] = np.percentile(arr, 85)

    entries = {
        "reversal_selloff": [],
        "absorption_reversal": [],
        "sweep_recovery": [],
        "continuation_buy_pressure": [],
        "failed_breakdown": []
    }
    
    last_ts = {k: 0.0 for k in entries.keys()}

    for s in snapshots:
        ts = s["ts"]
        pr = s["pr"]
        f = s["feats"]
        arrs = s["arrs"]

        signals = []
        if f["ret_30s"] <= p["ret_30s_p10"] and f["spr_10s"] >= p["spr_10s_p75"]:
            signals.append("reversal_selloff")
        
        if f["spr_30s"] >= p["spr_30s_p75"] and f["ret_30s"] >= p["ret_30s_p35"] and f["ob_imb"] >= p["ob_imb_p60"]:
            signals.append("absorption_reversal")
            
        if f["ret_60s"] <= p["ret_60s_p15"] and f["ret_10s"] >= max(p["ret_10s_p55"], 0.0) and f["bid_depth_change_30s"] >= p["bid_depth_change_30s_p70"]:
            signals.append("sweep_recovery")
            
        if f["ret_30s"] >= p["ret_30s_p85"] and f["bpr_10s"] >= p["bpr_10s_p70"] and f["ob_imb"] >= p["ob_imb_p60"]:
            signals.append("continuation_buy_pressure")
            
        if f["ret_60s"] <= p["ret_60s_p15"] and f["ret_10s"] >= p["ret_10s_p50"] and f["spr_10s"] < p["spr_10s_p75"]:
            signals.append("failed_breakdown")

        if signals:
            o_ts, o_pr = arrs["o_ts"], arrs["o_pr"]
            t_ts, t_pr = arrs["t_ts"], arrs["t_pr"]
            
            if len(o_ts) > 0:
                f_mask = (o_ts > ts) & (o_ts <= ts + max(TO_CANDS) + 10)
                f_ts = o_ts[f_mask]
                f_pr = o_pr[f_mask]
            else:
                f_mask = (t_ts > ts) & (t_ts <= ts + max(TO_CANDS) + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]
                
            if len(f_ts) == 0:
                f_mask = (t_ts > ts) & (t_ts <= ts + max(TO_CANDS) + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]

            eval_res = None
            for sig in signals:
                if ts >= last_ts[sig] + ENTRY_COOLDOWN_SEC:
                    if eval_res is None:
                        eval_res = _evaluate_future(pr, ts, f_ts, f_pr, TP_CANDS, SL_CANDS, TO_CANDS)
                    entries[sig].append({"market": market, "ts": ts, "pr": pr, "eval": eval_res})
                    last_ts[sig] = ts

    for k in entries:
        if len(entries[k]) > MAX_ENTRIES_PER_MARKET_PER_SIGNAL:
            idx = np.linspace(0, len(entries[k])-1, MAX_ENTRIES_PER_MARKET_PER_SIGNAL, dtype=int)
            entries[k] = [entries[k][i] for i in idx]

    return entries

def analyze_strategy_entries(entries, name):
    if not entries:
        return {
            "name": name,
            "judgement": "NO_TRADES",
            "best_combo": {
                "tp": 0, "sl": 0, "timeout": 0, "trades": 0,
                "win_rate": 0.0, "avg_gross_pnl": 0.0,
                "cost_scenarios": { f"slip_{s:.2f}": {"avg_net_pnl": 0.0, "total_net_pnl": 0.0, "max_cons_losses": 0, "profit_factor": 0.0} for s in SLIPPAGE_CANDS }
            },
            "trades": 0, "per_market": {},
            "top_market": None, "top1_market_share": 0.0, "top2_market_share": 0.0,
            "large_market_share": 0.0, "weak_markets": [], "viable_markets": 0,
            "net_pnl_slip_05": 0.0, "warnings": ["NO_TRADES"]
        }
        
    combos = list(product(TP_CANDS, SL_CANDS, TO_CANDS))
    combo_stats = []

    for tp, sl, to in combos:
        key = (tp, sl, to)
        trades = len(entries)
        win = loss = to_c = 0
        pnls = []
        for e in entries:
            res = e["eval"][key]
            pnls.append(res["pnl"])
            if res["res"] == "WIN": win += 1
            elif res["res"] == "LOSS": loss += 1
            else: to_c += 1
            
        avg_gross = np.mean(pnls)
        cost_scenarios = {}
        for slip in SLIPPAGE_CANDS:
            rt_cost = (UPBIT_FEE_PCT + slip) * 2
            net_pnls = np.array(pnls) - rt_cost
            avg_net = np.mean(net_pnls)
            
            gains = net_pnls[net_pnls > 0]
            losses = net_pnls[net_pnls < 0]
            pf = np.sum(gains) / abs(np.sum(losses)) if np.sum(losses) != 0 else 999.0
            
            max_dd = 0
            curr_dd = 0
            for net in net_pnls:
                if net < 0:
                    curr_dd += 1
                    if curr_dd > max_dd: max_dd = curr_dd
                else:
                    curr_dd = 0
                    
            cost_scenarios[f"slip_{slip:.2f}"] = {
                "avg_net_pnl": float(avg_net),
                "total_net_pnl": float(np.sum(net_pnls)),
                "profit_factor": float(pf),
                "max_cons_losses": max_dd
            }
            
        combo_stats.append({
            "tp": tp, "sl": sl, "timeout": to,
            "trades": trades, "win_rate": win / trades if trades else 0,
            "timeout_ratio": to_c / trades if trades else 0,
            "avg_gross_pnl": float(avg_gross),
            "cost_scenarios": cost_scenarios
        })

    combo_stats.sort(key=lambda x: x["cost_scenarios"]["slip_0.05"]["avg_net_pnl"], reverse=True)
    bc = combo_stats[0]
    best_key = (bc["tp"], bc["sl"], bc["timeout"])

    per_market = {}
    for m in TARGET_MARKETS:
        m_entries = [e for e in entries if e["market"] == m]
        m_trades = len(m_entries)
        if m_trades == 0: continue
        w = l = t = 0
        m_pnls = []
        for e in m_entries:
            res = e["eval"][best_key]
            if res["res"] == "WIN": w += 1
            elif res["res"] == "LOSS": l += 1
            else: t += 1
            m_pnls.append(res["pnl"])
        
        avg_gross_m = float(np.mean(m_pnls))
        avg_net_m_05 = avg_gross_m - (UPBIT_FEE_PCT + 0.05) * 2
        per_market[m] = {
            "trades": m_trades, "win_rate": w / m_trades,
            "avg_gross": avg_gross_m, "avg_net_slip_0.05": avg_net_m_05
        }

    sorted_m = sorted(per_market.items(), key=lambda x: x[1]["trades"], reverse=True)
    top1_share = sorted_m[0][1]["trades"] / bc["trades"] if sorted_m else 0
    top2_share = (sorted_m[0][1]["trades"] + (sorted_m[1][1]["trades"] if len(sorted_m) > 1 else 0)) / bc["trades"] if sorted_m else 0

    large_markets = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL"]
    large_market_trades = sum(per_market.get(m, {}).get("trades", 0) for m in large_markets)
    large_market_share = large_market_trades / bc["trades"] if bc["trades"] > 0 else 0

    weak_markets = [m for m, stats in per_market.items() if stats["avg_net_slip_0.05"] <= 0]
    viable_markets = len(per_market) - len(weak_markets)

    slip05_net = bc["cost_scenarios"]["slip_0.05"]["avg_net_pnl"]
    pf_05 = bc["cost_scenarios"]["slip_0.05"]["profit_factor"]
    
    warnings = []
    if top1_share >= 0.4: warnings.append("market_bias_warning")
    if top2_share >= 0.7: warnings.append("strong_market_bias_warning")
    if bc["timeout_ratio"] > 0.35: warnings.append("timeout_warning")
    if pf_05 < 1.2 and slip05_net > 0: warnings.append("weak_profit_factor_warning")

    if slip05_net > 0 and viable_markets >= 3 and top1_share < 0.6:
        judgement = "SIGNAL_FAMILY_SURVIVES_COSTS"
    elif slip05_net > 0 and viable_markets < 3:
        judgement = "MARKET_SPECIFIC_ONLY"
    elif bc["cost_scenarios"]["slip_0.03"]["avg_net_pnl"] > 0:
        judgement = "COST_SENSITIVE_WEAK"
    elif bc["avg_gross_pnl"] > 0:
        judgement = "NO_SIGNAL_SURVIVES_COSTS"
    else:
        judgement = "REJECT_CURRENT_SIGNAL_SET"

    return {
        "name": name,
        "judgement": judgement,
        "best_combo": bc,
        "trades": bc["trades"],
        "per_market": per_market,
        "top_market": sorted_m[0][0] if sorted_m else None,
        "top1_market_share": top1_share,
        "top2_market_share": top2_share,
        "large_market_share": large_market_share,
        "weak_markets": weak_markets,
        "viable_markets": viable_markets,
        "net_pnl_slip_05": slip05_net,
        "warnings": warnings
    }

def main():
    print("=" * 72)
    print(" Multi-Signal Price-Path Comparison")
    print("=" * 72)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite not found: {SQLITE_CACHE}")
        return
    
    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    all_entries = {
        "reversal_selloff": [],
        "absorption_reversal": [],
        "sweep_recovery": [],
        "continuation_buy_pressure": [],
        "failed_breakdown": []
    }
    
    for market in TARGET_MARKETS:
        res = process_market(conn, market, mode)
        for k in all_entries.keys():
            if k in res:
                all_entries[k].extend(res[k])
                
    conn.close()

    results = {}
    for k in all_entries.keys():
        print(f"Analyzing {k}...")
        results[k] = analyze_strategy_entries(all_entries[k], k)

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "MULTI_SIGNAL_COMPARISON",
        "results": results
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  MULTI-SIGNAL PRICE-PATH COMPARISON REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  TOP10 MULTI-SIGNAL COMPARISON",
        "  This is not DOGE-only.",
        "  slip 0.05% survival is the key gate.",
        "=" * 72,
        f"Generated  : {report_data['generated_at']}",
        ""
    ]
    
    sorted_results = sorted(results.values(), key=lambda x: x["net_pnl_slip_05"], reverse=True)
    
    lines.append("[ Signal Family Ranking (by Net PnL slip 0.05%) ]")
    for i, res in enumerate(sorted_results):
        lines.append(f"  {i+1}. {res['name']:<30} : {res['net_pnl_slip_05']:>10.4f}%  ({res['judgement']})")
    lines.append("")
    
    for res in sorted_results:
        lines.append("-" * 72)
        lines.append(f" [ Signal : {res['name']} ]")
        if res['trades'] == 0:
            lines.append("   -> NO TRADES")
            continue
            
        lines.append(f"   Judgement          : {res['judgement']}")
        
        bc = res['best_combo']
        lines.append(f"   Best Combo         : TP +{bc['tp']}% / SL {bc['sl']}% / TO {bc['timeout']}s")
        lines.append(f"   Total Trades       : {bc['trades']:,}")
        lines.append(f"   Win Rate           : {bc['win_rate']:.2%} (Timeout: {bc['timeout_ratio']:.2%})")
        lines.append(f"   Avg Gross PnL      : {bc['avg_gross_pnl']:+.4f}%")
        
        lines.append("   [ Cost Scenarios ]")
        for slip_k, sc in bc["cost_scenarios"].items():
            lines.append(f"     {slip_k:<12} Net: {sc['avg_net_pnl']:>10.4f}%  Total: {sc['total_net_pnl']:>10.4f}%  MaxLoss: {sc['max_cons_losses']}  PF: {sc['profit_factor']:.2f}")
            
        lines.append("   [ Market Analysis ]")
        lines.append(f"     Top1 Share         : {res['top1_market_share']:.2%} ({res['top_market']})")
        lines.append(f"     Top2 Share         : {res['top2_market_share']:.2%}")
        lines.append(f"     Large Market Share : {res['large_market_share']:.2%}")
        lines.append(f"     Viable Markets     : {res['viable_markets']} / 10")
        lines.append(f"     Warnings           : {', '.join(res['warnings']) if res['warnings'] else 'None'}")
        
        lines.append("   [ Per-Market Breakdown ]")
        lines.append(f"     {'Market':<14} {'Trades':>6} {'WinRate':>9} {'AvgGross':>10} {'Net(Slip0.05)':>14}")
        
        for m, m_st in sorted(res['per_market'].items(), key=lambda x: x[1]['trades'], reverse=True):
            lines.append(
                f"     {m:<14} {m_st['trades']:>6} {m_st['win_rate']:>9.2%} "
                f"{m_st['avg_gross']:>10.4f} {m_st['avg_net_slip_0.05']:>14.4f}"
            )
        lines.append("")
        
    lines.extend([
        "=" * 72,
        "  CONCLUSION & NEXT STEPS",
        "  - Review the Signal Family Ranking to identify the most robust structure.",
        "  - If NO_SIGNAL_SURVIVES_COSTS, consider adjusting thresholds or extracting more features.",
        "  - Target candidate creation ONLY for signals that pass the slip 0.05% gate.",
        "=" * 72
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
