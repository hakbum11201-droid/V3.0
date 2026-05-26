"""
run_reversal_price_path_paper_simulation.py
Preliminary Price-Path Paper Simulation

Evaluates Reversal Edge entry conditions against the master SQLite dataset.
Instead of label-based estimation, it tracks actual future price paths
to determine WIN (TP hit), LOSS (SL hit), or TIMEOUT outcomes for multiple
TP/SL/Timeout parameter combinations.

IMPORTANT:
  - This is a PRELIMINARY PRICE-PATH PAPER SIMULATION.
  - It does NOT place real orders.
  - It does NOT generate candidate or config files.
  - Positive results do NOT confirm production readiness.
"""
import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import product

# ─── Config ───────────────────────────────────────────────────────────────────
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR      = "reports/experiments"
JSON_REPORT  = os.path.join(OUT_DIR, "reversal_price_path_paper_simulation_latest.json")
TXT_REPORT   = os.path.join(OUT_DIR, "reversal_price_path_paper_simulation_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

# Entry conditions
COND_RET_30S = -0.3891
COND_SELL_10S = 0.9929

# Candidates for exit logic
TP_CANDS = [0.20, 0.25, 0.30]
SL_CANDS = [-0.10, -0.15, -0.20]
TO_CANDS = [180, 300, 450]

# Cost model
UPBIT_FEE_PCT = 0.05
SLIPPAGE_CANDS = [0.03, 0.05, 0.10]

# Sampling
N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_ENTRIES_PER_MARKET = 1000
ENTRY_COOLDOWN_SEC = 60.0


STATS = {
    "schema_mode": "unknown",
    "skipped_rows_missing_price": 0,
    "parsed_rows": 0
}

DEBUG_STATS = {
    "candidate_snapshots_checked": 0,
    "recent_return_30s_list": [],
    "sell_pressure_ratio_10s_list": [],
    "return_condition_pass": 0,
    "pressure_condition_pass": 0,
    "both_condition_pass": 0,
    "per_market": defaultdict(lambda: {
        "loaded_rows": 0,
        "parsed_price_rows": 0,
        "orderbook_price_rows": 0,
        "trade_rows": 0,
        "buy_rows": 0,
        "sell_rows": 0,
        "snapshot_checked": 0,
        "return_condition_pass": 0,
        "pressure_condition_pass": 0,
        "both_condition_pass": 0
    })
}


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
    DEBUG_STATS["per_market"][market]["loaded_rows"] += len(rows)
    t_ts_list, t_pr_list, t_qty_list, t_is_buy_list = [], [], [], []
    o_ts_list, o_pr_list = [], []

    if mode == "direct_columns":
        for r in rows:
            t_ts_list.append(float(r[0]))
            t_pr_list.append(float(r[1]))
            t_qty_list.append(float(r[2]))
            t_is_buy_list.append(int(r[3]))
        STATS["parsed_rows"] += len(rows)
    else:
        for r in rows:
            ts = float(r[0])
            try:
                obj = json.loads(r[1]) if isinstance(r[1], str) else r[1]
                if isinstance(obj, str):
                    obj = json.loads(obj)
            except Exception:
                STATS["skipped_rows_missing_price"] += 1
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
                    DEBUG_STATS["per_market"][market]["orderbook_price_rows"] += 1
                else:
                    STATS["skipped_rows_missing_price"] += 1
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

                    DEBUG_STATS["per_market"][market]["trade_rows"] += 1
                    if is_buy == 1:
                        DEBUG_STATS["per_market"][market]["buy_rows"] += 1
                    elif is_buy == 0:
                        DEBUG_STATS["per_market"][market]["sell_rows"] += 1
                else:
                    STATS["skipped_rows_missing_price"] += 1

        STATS["parsed_rows"] += (len(t_ts_list) + len(o_ts_list))

    if not t_ts_list:
        return None

    DEBUG_STATS["per_market"][market]["parsed_price_rows"] += (len(t_ts_list) + len(o_ts_list))
    
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


def process_market(conn, market):
    print(f"  [{market}] Scanning {N_BANDS} bands ...")
    mode = _get_schema_mode(conn)
    STATS["schema_mode"] = mode

    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None:
        return []

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to:
        return []

    band_starts = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    market_entries = []

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

        last_entry_ts = 0.0
        
        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - max_to, STEP_SEC):
            DEBUG_STATS["candidate_snapshots_checked"] += 1
            DEBUG_STATS["per_market"][market]["snapshot_checked"] += 1

            if snap_ts < last_entry_ts + ENTRY_COOLDOWN_SEC:
                continue

            i_curr = gidx(snap_ts)
            if i_curr == 0:
                continue
            pr_curr = t_pr[i_curr - 1]
            ts_curr = t_ts[i_curr - 1]

            if i_curr == gidx(snap_ts - 10):
                continue

            i_10s = gidx(snap_ts - 10)
            i_30s = gidx(snap_ts - 30)

            pr_30s = t_pr[i_30s] if i_30s < len(t_pr) else pr_curr
            ret_30s = float((pr_curr - pr_30s) / pr_30s * 100.0) if pr_30s > 0 else 0.0

            DEBUG_STATS["recent_return_30s_list"].append(ret_30s)

            if ret_30s <= COND_RET_30S:
                DEBUG_STATS["return_condition_pass"] += 1
                DEBUG_STATS["per_market"][market]["return_condition_pass"] += 1

                qty_win = t_qty[i_10s:i_curr]
                is_buy_win = t_is_buy[i_10s:i_curr]

                buy_vol = np.sum(qty_win[is_buy_win == 1])
                sell_vol = np.sum(qty_win[is_buy_win == 0])
                spr = sell_vol / (buy_vol + sell_vol + 1e-8)

                DEBUG_STATS["sell_pressure_ratio_10s_list"].append(spr)

                if spr >= COND_SELL_10S:
                    DEBUG_STATS["pressure_condition_pass"] += 1
                    DEBUG_STATS["both_condition_pass"] += 1
                    DEBUG_STATS["per_market"][market]["pressure_condition_pass"] += 1
                    DEBUG_STATS["per_market"][market]["both_condition_pass"] += 1

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

                    market_entries.append({
                        "market": market,
                        "ts": ts_curr,
                        "pr": pr_curr,
                        "eval": eval_res
                    })
                    last_entry_ts = ts_curr

    if len(market_entries) > MAX_ENTRIES_PER_MARKET:
        idx = np.linspace(0, len(market_entries)-1, MAX_ENTRIES_PER_MARKET, dtype=int)
        market_entries = [market_entries[i] for i in idx]

    return market_entries


def main():
    print("=" * 60)
    print(" Reversal Price-Path Paper Simulation")
    print("=" * 60)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite not found: {SQLITE_CACHE}")
        return

    conn = sqlite3.connect(SQLITE_CACHE)
    
    all_entries_flat = []
    for market in TARGET_MARKETS:
        entries = process_market(conn, market)
        all_entries_flat.extend(entries)
        print(f"    -> Found {len(entries)} entries for {market}")
    conn.close()

    if not all_entries_flat:
        print("[Error] No entries found.")
        _save_debug_report("NO_ENTRIES_FOUND_DEBUG_REQUIRED")
        return

    all_entries_flat.sort(key=lambda x: x["ts"])
    
    combos = list(product(TP_CANDS, SL_CANDS, TO_CANDS))
    combo_stats = []

    for tp, sl, to in combos:
        key = (tp, sl, to)
        trades = len(all_entries_flat)
        
        win = loss = to_c = 0
        pnls = []
        for e in all_entries_flat:
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
        m_entries = [e for e in all_entries_flat if e["market"] == m]
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
        
        per_market[m] = {
            "trades": m_trades,
            "win": w, "loss": l, "timeout": t,
            "win_rate": w / m_trades,
            "avg_gross": float(np.mean(m_pnls))
        }

    market_bias_warning = None
    if best_combo["trades"] > 0:
        top_m = max(per_market.keys(), key=lambda k: per_market[k]["trades"])
        top_share = per_market[top_m]["trades"] / best_combo["trades"]
        if top_share > 0.6:
            market_bias_warning = f"{top_m} contributes {top_share:.0%} of trades."

    slip05_net = best_combo["cost_scenarios"]["slip_0.05"]["avg_net_pnl"]
    slip10_net = best_combo["cost_scenarios"]["slip_0.10"]["avg_net_pnl"]
    
    if slip05_net > 0 and slip10_net > 0:
        judgement = "PRICE_PATH_PAPER_POSITIVE"
    elif slip05_net > 0:
        judgement = "COST_SENSITIVE"
    elif best_combo["avg_gross_pnl"] > 0:
        judgement = "PRICE_PATH_PAPER_WEAK"
    else:
        judgement = "PRICE_PATH_PAPER_FAILED"
        
    if market_bias_warning and judgement != "PRICE_PATH_PAPER_FAILED":
        judgement = "MARKET_BIAS_WARNING"

    report = {
        "generated_at": datetime.now().isoformat(),
        "judgement": judgement,
        "status": "PRELIMINARY_PRICE_PATH_PAPER_SIMULATION",
        "entry_conditions": {
            "recent_return_30s": {"op": "<=", "value": COND_RET_30S},
            "sell_pressure_ratio_10s": {"op": ">=", "value": COND_SELL_10S}
        },
        "best_combination": {
            "tp": best_combo["tp"],
            "sl": best_combo["sl"],
            "timeout": best_combo["timeout"]
        },
        "best_combo_results": best_combo,
        "market_bias_warning": market_bias_warning,
        "per_market_trades": per_market,
        "top_5_combinations": combo_stats[:5],
        "parsing_stats": STATS,
        "note": "Preliminary price-path paper simulation. Not for production use."
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  Reversal Price-Path Paper Simulation",
        "  STATUS: PRELIMINARY SIMULATION ONLY",
        "=" * 72,
        f"Generated  : {report['generated_at']}",
        f"Judgement  : {judgement}",
        f"Schema Mode: {STATS['schema_mode']}",
        f"Parsed Rows: {STATS['parsed_rows']:,}",
        f"Skipped Rows (no price): {STATS['skipped_rows_missing_price']:,}",
        "",
        "[ Entry Conditions ]",
        f"  recent_return_30s <= {COND_RET_30S}",
        f"  sell_pressure_ratio_10s >= {COND_SELL_10S}",
        "",
        "[ Best TP / SL / Timeout Combination ]",
        f"  TP: +{best_combo['tp']}%  |  SL: {best_combo['sl']}%  |  Timeout: {best_combo['timeout']}s",
        f"  Total Trades : {best_combo['trades']:,}",
        f"  WIN Count    : {best_combo['win_count']:,} ({best_combo['win_rate']:.2%})",
        f"  LOSS Count   : {best_combo['loss_count']:,}",
        f"  TIMEOUT Count: {best_combo['timeout_count']:,} ({best_combo['timeout_ratio']:.2%})",
        f"  Avg Gross PnL: {best_combo['avg_gross_pnl']:+.4f}%",
        "",
        "[ Cost Scenarios (Best Combo) ]",
        f"  {'Scenario':<18} {'Net PnL':>10} {'Total PnL':>10} {'ProfFact':>10} {'MaxLoss':>8}",
        "  " + "-" * 56
    ]
    for slip_k, sc in best_combo["cost_scenarios"].items():
        lines.append(
            f"  {slip_k:<18} {sc['avg_net_pnl']:>10.4f} "
            f"{sc['total_net_pnl']:>10.4f} {sc['profit_factor']:>10.2f} "
            f"{sc['max_cons_losses']:>8}"
        )

    if market_bias_warning:
        lines += ["", f"  ! WARNING: {market_bias_warning}"]

    lines += [
        "",
        "[ Per-Market Results (Best Combo) ]",
        f"  {'Market':<14} {'Trades':>6} {'WinRate':>9} {'AvgGross':>10}",
        "  " + "-" * 42
    ]
    for m, m_st in sorted(per_market.items(), key=lambda x: x[1]['trades'], reverse=True):
        lines.append(
            f"  {m:<14} {m_st['trades']:>6} {m_st['win_rate']:>9.2%} "
            f"{m_st['avg_gross']:>10.4f}"
        )

    lines += [
        "",
        "=" * 72,
        "  IMPORTANT:",
        "  No real orders were placed. No config or candidate files modified.",
        "  Positive results are preliminary and require further safety checks.",
        "=" * 72
    ]

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")
    print(f"Judgement   : {judgement}")


def _save_debug_report(judgement):
    ret_list = DEBUG_STATS["recent_return_30s_list"]
    spr_list = DEBUG_STATS["sell_pressure_ratio_10s_list"]

    ret_stats = {
        "min": float(np.min(ret_list)) if ret_list else 0.0,
        "max": float(np.max(ret_list)) if ret_list else 0.0,
        "p10": float(np.percentile(ret_list, 10)) if ret_list else 0.0,
        "p50": float(np.percentile(ret_list, 50)) if ret_list else 0.0,
        "p90": float(np.percentile(ret_list, 90)) if ret_list else 0.0
    }
    spr_stats = {
        "min": float(np.min(spr_list)) if spr_list else 0.0,
        "max": float(np.max(spr_list)) if spr_list else 0.0,
        "p10": float(np.percentile(spr_list, 10)) if spr_list else 0.0,
        "p50": float(np.percentile(spr_list, 50)) if spr_list else 0.0,
        "p90": float(np.percentile(spr_list, 90)) if spr_list else 0.0
    }

    report = {
        "generated_at": datetime.now().isoformat(),
        "judgement": judgement,
        "schema_mode": STATS["schema_mode"],
        "parsed_rows": STATS["parsed_rows"],
        "skipped_rows_missing_price": STATS["skipped_rows_missing_price"],
        "candidate_snapshots_checked": DEBUG_STATS["candidate_snapshots_checked"],
        "condition_stats": {
            "recent_return_30s": ret_stats,
            "sell_pressure_ratio_10s": spr_stats,
            "return_condition_pass_count": DEBUG_STATS["return_condition_pass"],
            "pressure_condition_pass_count": DEBUG_STATS["pressure_condition_pass"],
            "both_condition_pass_count": DEBUG_STATS["both_condition_pass"]
        },
        "per_market_debug": dict(DEBUG_STATS["per_market"])
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  Reversal Price-Path Paper Simulation - DEBUG REPORT",
        "=" * 72,
        f"Judgement: {judgement}",
        f"Schema Mode: {STATS['schema_mode']}",
        f"Parsed Rows: {STATS['parsed_rows']:,}",
        f"Skipped Rows (no price): {STATS['skipped_rows_missing_price']:,}",
        f"Candidate Snapshots Checked: {DEBUG_STATS['candidate_snapshots_checked']:,}",
        "",
        "[ recent_return_30s Stats ]",
        f"  min: {ret_stats['min']:.4f}, max: {ret_stats['max']:.4f}",
        f"  p10: {ret_stats['p10']:.4f}, p50: {ret_stats['p50']:.4f}, p90: {ret_stats['p90']:.4f}",
        f"  Pass Count (<= {COND_RET_30S}): {DEBUG_STATS['return_condition_pass']:,}",
        "",
        "[ sell_pressure_ratio_10s Stats ]",
        f"  min: {spr_stats['min']:.4f}, max: {spr_stats['max']:.4f}",
        f"  p10: {spr_stats['p10']:.4f}, p50: {spr_stats['p50']:.4f}, p90: {spr_stats['p90']:.4f}",
        f"  Pass Count (>= {COND_SELL_10S}): {DEBUG_STATS['pressure_condition_pass']:,}",
        "",
        f"Both Conditions Pass Count: {DEBUG_STATS['both_condition_pass']:,}",
        "",
        "[ Per-Market Debug Summary ]"
    ]
    for m, st in DEBUG_STATS["per_market"].items():
        lines.append(f"  {m}:")
        for k, v in st.items():
            lines.append(f"    {k}: {v}")

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[Done] Debug JSON : {JSON_REPORT}")
    print(f"[Done] Debug TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
