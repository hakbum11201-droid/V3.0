import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import product

# ─── Config ───────────────────────────────────────────────────────────────────
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
HISTOGRAMS_JSON = "reports/experiments/reversal_threshold_histograms_latest.json"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "reversal_market_adaptive_price_path_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "reversal_market_adaptive_price_path_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

STATIC_COND_RET_30S = -0.3891
STATIC_COND_SELL_10S = 0.9929

UPBIT_FEE_PCT = 0.05
SLIPPAGE_CANDS = [0.03, 0.05, 0.10]

TP_CANDS = [0.20, 0.25, 0.30]
SL_CANDS = [-0.10, -0.15, -0.20]
TO_CANDS = [180, 300, 450]

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_ENTRIES_PER_MARKET = 1000
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
    o_ts_list, o_pr_list = [], []

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
                pr = None
                units = payload.get("orderbook_units", [])
                if units and len(units) > 0:
                    try:
                        ap = float(units[0]["ask_price"])
                        bp = float(units[0]["bid_price"])
                        pr = (ap + bp) / 2.0
                    except Exception:
                        pass
                if pr is not None:
                    o_ts_list.append(ts)
                    o_pr_list.append(pr)
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
        "o_pr": np.array(o_pr_list, dtype=float)[o_sort] if len(o_pr_list) > 0 else np.array([])
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
                    elif t_sl < t_tp:
                        res, pnl = "LOSS", sl
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

def load_market_thresholds():
    if not os.path.exists(HISTOGRAMS_JSON):
        print(f"[Warn] {HISTOGRAMS_JSON} not found. Will use loose fallbacks.")
        return {}
        
    with open(HISTOGRAMS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    per_market = data.get("per_market", {})
    thresholds = {}
    
    for market in TARGET_MARKETS:
        if market not in per_market:
            print(f"[Warn] {market} not found in histograms.")
            thresholds[market] = None
            continue
            
        m_data = per_market[market]
        
        try:
            # Percentile based
            ret_p10 = m_data["recent_return_30s"]["ALL"]["percentiles"]["p10"]
            spr_p75 = m_data["sell_pressure_ratio_10s"]["ALL"]["percentiles"]["p75"]
            
            # Volatility based (Mean - 1.5 * StdDev)
            ret_mean = m_data["recent_return_30s"]["ALL"]["stats"]["mean"]
            ret_std = m_data["recent_return_30s"]["ALL"]["stats"]["std"]
            ret_vol = ret_mean - 1.5 * ret_std
            
            spr_p70 = m_data["sell_pressure_ratio_10s"]["ALL"]["percentiles"]["p70"]
            
            thresholds[market] = {
                "percentile": {
                    "ret_30s": ret_p10,
                    "spr_10s": spr_p75
                },
                "volatility": {
                    "ret_30s": ret_vol,
                    "spr_10s": spr_p70
                }
            }
        except KeyError:
            print(f"[Warn] Missing stats keys for {market}")
            thresholds[market] = None
            
    return thresholds

def process_market(conn, market, market_thresholds, mode):
    print(f"  [{market}] Scanning {N_BANDS} bands ...")
    
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None:
        return {"static": [], "percentile": [], "volatility": []}

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to:
        return {"static": [], "percentile": [], "volatility": []}

    band_starts = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    
    entries = {"static": [], "percentile": [], "volatility": []}
    
    for w_start in band_starts:
        w_end = min(w_start + win_sec, max_ts)
        rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
        arrs = _parse_rows(rows, mode, market)
        if not arrs:
            continue

        t_ts = arrs["t_ts"]
        t_pr = arrs["t_pr"]
        t_qty = arrs["t_qty"]
        t_is_buy = arrs["t_is_buy"]
        
        o_ts = arrs["o_ts"]
        o_pr = arrs["o_pr"]

        def gidx(v): return np.searchsorted(t_ts, v, side="right")

        last_ts = {"static": 0.0, "percentile": 0.0, "volatility": 0.0}
        
        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - max_to, STEP_SEC):
            
            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            pr_curr = t_pr[i_curr - 1]
            ts_curr = t_ts[i_curr - 1]

            if i_curr == gidx(snap_ts - 10): continue

            i_10s = gidx(snap_ts - 10)
            i_30s = gidx(snap_ts - 30)

            pr_30s = t_pr[i_30s] if i_30s < len(t_pr) else pr_curr
            ret_30s = float((pr_curr - pr_30s) / pr_30s * 100.0) if pr_30s > 0 else 0.0

            qty_win = t_qty[i_10s:i_curr]
            is_buy_win = t_is_buy[i_10s:i_curr]

            buy_vol = np.sum(qty_win[is_buy_win == 1])
            sell_vol = np.sum(qty_win[is_buy_win == 0])
            spr = sell_vol / (buy_vol + sell_vol + 1e-8)
            
            can_static = (ret_30s <= STATIC_COND_RET_30S and spr >= STATIC_COND_SELL_10S) and (snap_ts >= last_ts["static"] + ENTRY_COOLDOWN_SEC)
            
            can_perc = False
            can_vol = False
            if market_thresholds and market_thresholds.get(market):
                th = market_thresholds[market]
                can_perc = (ret_30s <= th["percentile"]["ret_30s"] and spr >= th["percentile"]["spr_10s"]) and (snap_ts >= last_ts["percentile"] + ENTRY_COOLDOWN_SEC)
                can_vol = (ret_30s <= th["volatility"]["ret_30s"] and spr >= th["volatility"]["spr_10s"]) and (snap_ts >= last_ts["volatility"] + ENTRY_COOLDOWN_SEC)

            if not (can_static or can_perc or can_vol):
                continue
                
            if len(o_ts) > 0:
                f_mask = (o_ts > ts_curr) & (o_ts <= ts_curr + max_to + 10)
                f_ts = o_ts[f_mask]
                f_pr = o_pr[f_mask]
            else:
                f_mask = (t_ts > ts_curr) & (t_ts <= ts_curr + max_to + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]
                
            if len(f_ts) == 0:
                f_mask = (t_ts > ts_curr) & (t_ts <= ts_curr + max_to + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]

            eval_res = _evaluate_future(pr_curr, ts_curr, f_ts, f_pr, TP_CANDS, SL_CANDS, TO_CANDS)

            if can_static:
                entries["static"].append({"market": market, "ts": ts_curr, "pr": pr_curr, "eval": eval_res})
                last_ts["static"] = ts_curr
            if can_perc:
                entries["percentile"].append({"market": market, "ts": ts_curr, "pr": pr_curr, "eval": eval_res})
                last_ts["percentile"] = ts_curr
            if can_vol:
                entries["volatility"].append({"market": market, "ts": ts_curr, "pr": pr_curr, "eval": eval_res})
                last_ts["volatility"] = ts_curr

    # limit entries
    for k in entries:
        if len(entries[k]) > MAX_ENTRIES_PER_MARKET:
            idx = np.linspace(0, len(entries[k])-1, MAX_ENTRIES_PER_MARKET, dtype=int)
            entries[k] = [entries[k][i] for i in idx]

    return entries

def analyze_strategy_entries(entries, name):
    if not entries:
        return {
            "name": name,
            "judgement": "NO_TRADES",
            "best_combo": {
                "tp": 0,
                "sl": 0,
                "timeout": 0,
                "trades": 0,
                "win_rate": 0.0,
                "avg_gross_pnl": 0.0,
                "cost_scenarios": {
                    "slip_0.05": {
                        "avg_net_pnl": 0.0,
                        "total_net_pnl": 0.0,
                        "max_cons_losses": 0
                    }
                }
            },
            "trades": 0,
            "per_market": {},
            "top_market": None,
            "top_market_share": 0.0,
            "doge_up2_share": 0.0,
            "large_market_share": 0.0,
            "weak_markets": [],
            "is_survived": False,
            "net_pnl_slip_05": 0.0
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
                "slippage_pct": slip,
                "avg_net_pnl": float(avg_net),
                "total_net_pnl": float(np.sum(net_pnls)),
                "profit_factor": float(pf),
                "max_cons_losses": max_dd,
                "is_positive": bool(avg_net > 0)
            }
            
        combo_stats.append({
            "tp": tp, "sl": sl, "timeout": to,
            "trades": trades,
            "win_count": win, "loss_count": loss, "timeout_count": to_c,
            "win_rate": win / trades if trades else 0,
            "timeout_ratio": to_c / trades if trades else 0,
            "avg_gross_pnl": float(avg_gross),
            "cost_scenarios": cost_scenarios
        })

    # Sort by net pnl at 0.05% slippage
    combo_stats.sort(key=lambda x: x["cost_scenarios"]["slip_0.05"]["avg_net_pnl"], reverse=True)
    best_combo = combo_stats[0]
    best_key = (best_combo["tp"], best_combo["sl"], best_combo["timeout"])

    # Per market stats for best combo
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
        rt_cost_05 = (UPBIT_FEE_PCT + 0.05) * 2
        avg_net_m_05 = avg_gross_m - rt_cost_05
        
        per_market[m] = {
            "trades": m_trades,
            "win_rate": w / m_trades,
            "avg_gross": avg_gross_m,
            "avg_net_slip_0.05": avg_net_m_05
        }

    top_m = max(per_market.keys(), key=lambda k: per_market[k]["trades"])
    top_share = per_market[top_m]["trades"] / best_combo["trades"]
    
    doge_up2_trades = per_market.get("KRW-DOGE", {}).get("trades", 0) + per_market.get("KRW-UP2", {}).get("trades", 0)
    doge_up2_share = doge_up2_trades / best_combo["trades"] if best_combo["trades"] > 0 else 0

    large_markets = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL"]
    large_market_trades = sum(per_market.get(m, {}).get("trades", 0) for m in large_markets)
    large_market_share = large_market_trades / best_combo["trades"] if best_combo["trades"] > 0 else 0

    weak_markets = [m for m, stats in per_market.items() if stats["avg_net_slip_0.05"] < 0]

    slip05_net = best_combo["cost_scenarios"]["slip_0.05"]["avg_net_pnl"]
    
    if slip05_net > 0 and large_market_share >= 0.05:
        judgement = "MARKET_ADAPTIVE_SURVIVES_COSTS"
    elif slip05_net > 0:
        judgement = "MARKET_SPECIFIC_ONLY"
    elif best_combo["cost_scenarios"]["slip_0.03"]["avg_net_pnl"] > 0:
        judgement = "COST_SENSITIVE_WEAK"
    elif best_combo["avg_gross_pnl"] > 0:
        judgement = "REJECT_COMMON_STATIC" if name == "common_static" else "MARKET_ADAPTIVE_FAILED"
    else:
        judgement = "MARKET_ADAPTIVE_FAILED"

    return {
        "name": name,
        "judgement": judgement,
        "best_combo": best_combo,
        "trades": best_combo["trades"],
        "per_market": per_market,
        "top_market": top_m,
        "top_market_share": top_share,
        "doge_up2_share": doge_up2_share,
        "large_market_share": large_market_share,
        "weak_markets": weak_markets,
        "is_survived": slip05_net > 0,
        "net_pnl_slip_05": slip05_net
    }

def main():
    print("=" * 72)
    print(" Reversal Market-Adaptive Price-Path Simulation")
    print("=" * 72)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite not found: {SQLITE_CACHE}")
        return

    market_thresholds = load_market_thresholds()
    
    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    all_static = []
    all_percentile = []
    all_volatility = []
    
    for market in TARGET_MARKETS:
        res = process_market(conn, market, market_thresholds, mode)
        all_static.extend(res["static"])
        all_percentile.extend(res["percentile"])
        all_volatility.extend(res["volatility"])
        print(f"    -> Found entries for {market}: Static={len(res['static'])}, Perc={len(res['percentile'])}, Vol={len(res['volatility'])}")
        
    conn.close()

    res_static = analyze_strategy_entries(all_static, "common_static")
    res_percentile = analyze_strategy_entries(all_percentile, "per_market_percentile")
    res_volatility = analyze_strategy_entries(all_volatility, "volatility_scaled")

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "MARKET_ADAPTIVE_SIMULATION",
        "market_thresholds": market_thresholds,
        "results": {
            "common_static": res_static,
            "per_market_percentile": res_percentile,
            "volatility_scaled": res_volatility
        }
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  MARKET-ADAPTIVE PRICE-PATH SIMULATION REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  DOGE-only is not the main objective. slip 0.05% survival is the key gate.",
        "  TOP10 MARKET-ADAPTIVE TEST",
        "=" * 72,
        f"Generated  : {report_data['generated_at']}",
        "",
        "[ Threshold Dictionary ]"
    ]
    
    for m in TARGET_MARKETS:
        th = market_thresholds.get(m)
        if th:
            lines.append(f"  {m}:")
            lines.append(f"    Percentile -> ret_30s <= {th['percentile']['ret_30s']:.4f}, spr_10s >= {th['percentile']['spr_10s']:.4f}")
            lines.append(f"    Volatility -> ret_30s <= {th['volatility']['ret_30s']:.4f}, spr_10s >= {th['volatility']['spr_10s']:.4f}")
    
    lines.append("")
    
    for res in [res_static, res_percentile, res_volatility]:
        lines.append("-" * 72)
        lines.append(f" [ Strategy : {res['name']} ]")
        if res['trades'] == 0:
            lines.append("   -> NO TRADES")
            continue
            
        lines.append(f"   Judgement          : {res['judgement']}")
        
        bc = res['best_combo']
        lines.append(f"   Best Combo         : TP +{bc['tp']}% / SL {bc['sl']}% / TO {bc['timeout']}s")
        lines.append(f"   Total Trades       : {bc['trades']:,}")
        lines.append(f"   Win Rate           : {bc['win_rate']:.2%}")
        lines.append(f"   Avg Gross PnL      : {bc['avg_gross_pnl']:+.4f}%")
        
        lines.append("   [ Cost Scenarios ]")
        for slip_k, sc in bc["cost_scenarios"].items():
            lines.append(f"     {slip_k:<12} Net: {sc['avg_net_pnl']:>10.4f}%  Total: {sc['total_net_pnl']:>10.4f}%  MaxLoss: {sc['max_cons_losses']}")
            
        lines.append("   [ Market Analysis ]")
        lines.append(f"     DOGE+UP2 Share     : {res['doge_up2_share']:.2%}")
        lines.append(f"     Large Market Share : {res['large_market_share']:.2%}")
        lines.append(f"     Weak Markets       : {', '.join(res['weak_markets']) if res['weak_markets'] else 'None'}")
        lines.append("     Excluded Market Candidates: " + (", ".join(res['weak_markets']) if res['weak_markets'] else 'None') + " (Suggested only)")
        
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
        "  - Compare common_static vs per_market_percentile vs volatility_scaled.",
        "  - Check if any adaptive method survives 0.05% slippage across Top 10.",
        "=" * 72
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
