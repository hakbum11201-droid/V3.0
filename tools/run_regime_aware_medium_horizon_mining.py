import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# Config
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "regime_aware_medium_horizon_mining_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "regime_aware_medium_horizon_mining_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
SLIP_PCT = 0.05
COST = (UPBIT_FEE_PCT + SLIP_PCT) * 2

TP_CANDS = [1.0, 1.5, 2.0, 3.0]
SL_CANDS = [-0.5, -0.8, -1.0, -1.5]
TO_CANDS = [300, 600, 900, 1200, 1800]  # 5m, 10m, 15m, 20m, 30m

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 30.0
MAX_SNAPSHOTS_PER_MARKET = 3000
EMBARGO_SEC = 900

FEAT_NAMES = [
    "return_1m", "return_3m", "return_5m", "return_10m", "return_15m",
    "volatility_3m", "volatility_5m", "volatility_10m", "volatility_15m",
    "volume_sum_1m", "volume_sum_3m", "volume_sum_5m", "volume_sum_15m",
    "volume_spike_5m", "buy_pressure_1m", "buy_pressure_3m",
    "sell_pressure_1m", "sell_pressure_3m", "pressure_delta_3m",
    "orderbook_imbalance", "spread_pct", "spread_median_3m",
    "trend_strength_5m", "pullback_score", "regime_momentum_score",
    "volatility_breakout_score", "liquidity_quality_score"
]

FAMILIES = {
    "regime_momentum": ["return_5m", "trend_strength_5m", "buy_pressure_3m", "spread_pct"],
    "pullback_in_uptrend": ["return_10m", "return_1m", "pullback_score", "orderbook_imbalance"],
    "volatility_breakout": ["volatility_5m", "volume_spike_5m", "return_3m", "spread_pct"],
    "liquidity_quality_momentum": ["liquidity_quality_score", "spread_pct", "buy_pressure_3m", "return_5m"]
}

PCT_CANDS = [10, 20, 30, 40, 50, 60, 70, 80, 90]

def _get_schema_mode(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(events)")
    cols = [row[1] for row in cur.fetchall()]
    return "direct_columns" if "price" in cols else "raw_json"

def _load_window(conn, market, t_start, t_end, mode):
    cur = conn.cursor()
    if mode == "direct_columns":
        cur.execute("SELECT ts, price, qty, is_buy FROM events WHERE market=? AND ts >= ? AND ts <= ? ORDER BY ts ASC", (market, t_start, t_end))
    else:
        cur.execute("SELECT ts, raw_json FROM events WHERE market=? AND ts >= ? AND ts <= ? ORDER BY ts ASC", (market, t_start, t_end))
    return cur.fetchall()

def _parse_rows(rows, mode):
    if not rows: return None
    t_ts_list, t_pr_list, t_qty_list, t_is_buy_list = [], [], [], []
    o_ts_list, o_bp_list, o_ap_list, o_bsz_list, o_asz_list = [], [], [], [], []

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
                if isinstance(obj, str): obj = json.loads(obj)
            except: continue
            payload = obj.get("raw", obj)
            if not isinstance(payload, dict): payload = obj
            et = obj.get("event_type") or payload.get("type")

            if et == "orderbook":
                units = payload.get("orderbook_units", [])
                if units and len(units) > 0:
                    try:
                        ap = float(units[0]["ask_price"])
                        bp = float(units[0]["bid_price"])
                        a_sz = float(units[0]["ask_size"])
                        b_sz = float(units[0]["bid_size"])
                        o_ts_list.append(ts)
                        o_bp_list.append(bp)
                        o_ap_list.append(ap)
                        o_bsz_list.append(b_sz)
                        o_asz_list.append(a_sz)
                    except: pass
            else:
                pr = None
                tp_val = payload.get("trade_price", payload.get("price"))
                if tp_val is not None:
                    try: pr = float(tp_val)
                    except: pass
                if pr is not None:
                    q_val = payload.get("trade_volume", payload.get("volume", payload.get("qty")))
                    try: qty = float(q_val) if q_val is not None else 0.0
                    except: qty = 0.0
                    side_val = payload.get("ask_bid", payload.get("trade_side", payload.get("side")))
                    side_str = str(side_val).upper() if side_val is not None else ""
                    if side_str in ("BID", "1", "BUY", "TRUE"): is_buy = 1
                    elif side_str in ("ASK", "0", "SELL", "FALSE", "-1"): is_buy = 0
                    else: is_buy = -1
                    t_ts_list.append(ts)
                    t_pr_list.append(pr)
                    t_qty_list.append(qty)
                    t_is_buy_list.append(is_buy)

    if not t_ts_list: return None
    t_sort = np.argsort(t_ts_list)
    o_sort = np.argsort(o_ts_list) if o_ts_list else []
    return {
        "t_ts": np.array(t_ts_list, dtype=float)[t_sort],
        "t_pr": np.array(t_pr_list, dtype=float)[t_sort],
        "t_qty": np.array(t_qty_list, dtype=float)[t_sort],
        "t_is_buy": np.array(t_is_buy_list, dtype=int)[t_sort],
        "o_ts": np.array(o_ts_list, dtype=float)[o_sort] if len(o_ts_list) > 0 else np.array([]),
        "o_bp": np.array(o_bp_list, dtype=float)[o_sort] if len(o_bp_list) > 0 else np.array([]),
        "o_ap": np.array(o_ap_list, dtype=float)[o_sort] if len(o_ap_list) > 0 else np.array([]),
        "o_bsz": np.array(o_bsz_list, dtype=float)[o_sort] if len(o_bsz_list) > 0 else np.array([]),
        "o_asz": np.array(o_asz_list, dtype=float)[o_sort] if len(o_asz_list) > 0 else np.array([])
    }

def _evaluate_future(entry_pr, entry_ts, f_ts, f_pr):
    num_cands = len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS)
    results = np.zeros(num_cands, dtype=np.float32)
    win_flags = np.zeros(num_cands, dtype=np.int32)
    to_flags = np.zeros(num_cands, dtype=np.int32)
    
    if len(f_pr) == 0:
        results[:] = -COST
        to_flags[:] = 1
        return results, win_flags, to_flags

    returns = (f_pr - entry_pr) / entry_pr * 100.0
    tp_hits = {tp: np.inf for tp in TP_CANDS}
    for tp in TP_CANDS:
        mask = returns >= tp
        if np.any(mask): tp_hits[tp] = f_ts[np.argmax(mask)]

    sl_hits = {sl: np.inf for sl in SL_CANDS}
    for sl in SL_CANDS:
        mask = returns <= sl
        if np.any(mask): sl_hits[sl] = f_ts[np.argmax(mask)]

    idx_comb = 0
    for tp in TP_CANDS:
        for sl in SL_CANDS:
            for to in TO_CANDS:
                limit_ts = entry_ts + to
                t_tp = tp_hits[tp]
                t_sl = sl_hits[sl]

                hit_tp = t_tp <= limit_ts
                hit_sl = t_sl <= limit_ts

                if hit_tp and hit_sl:
                    if t_tp < t_sl: pnl, win, timeout = tp, 1, 0
                    else: pnl, win, timeout = sl, 0, 0
                elif hit_tp: pnl, win, timeout = tp, 1, 0
                elif hit_sl: pnl, win, timeout = sl, 0, 0
                else:
                    idx_f = np.searchsorted(f_ts, limit_ts, side='right') - 1
                    if idx_f < 0: idx_f = 0
                    pnl = returns[idx_f] if idx_f < len(returns) else 0.0
                    win, timeout = 0, 1

                results[idx_comb] = float(pnl) - COST
                win_flags[idx_comb] = win
                to_flags[idx_comb] = timeout
                idx_comb += 1
    return results, win_flags, to_flags

def process_market(conn, market, mode):
    print(f"  [{market}] Extracting snapshots...")
    cur = conn.cursor()
    cur.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,))
    row = cur.fetchone()
    if not row or row[0] is None: return [], [], [], [], []

    min_ts, max_ts = float(row[0]), float(row[1])
    total_span = max_ts - min_ts
    if total_span < WINDOW_MIN * 60: return [], [], [], [], []

    band_length = total_span / N_BANDS
    if band_length < WINDOW_MIN * 60: band_length = WINDOW_MIN * 60

    X_list, Y_net_list, Y_win_list, Y_to_list, fallback_list = [], [], [], [], []
    for b in range(N_BANDS):
        t_start = min_ts + b * band_length
        t_end = t_start + band_length
        if t_start > max_ts: break

        t_end_query = min(t_end + 1800, max_ts) # +30m for future
        rows = _load_window(conn, market, t_start, t_end_query, mode)
        parsed = _parse_rows(rows, mode)
        if not parsed: continue

        t_ts, t_pr, t_qty, t_is_buy = parsed["t_ts"], parsed["t_pr"], parsed["t_qty"], parsed["t_is_buy"]
        o_ts, o_ap, o_bp, o_asz, o_bsz = parsed["o_ts"], parsed["o_ap"], parsed["o_bp"], parsed["o_asz"], parsed["o_bsz"]

        if len(t_ts) < 100: continue

        base_time = t_start + 900 # past 15m buffer
        while base_time <= t_end:
            if len(X_list) >= MAX_SNAPSHOTS_PER_MARKET: break
            
            t_idx = np.searchsorted(t_ts, base_time, side='right') - 1
            if t_idx < 0: 
                base_time += STEP_SEC
                continue

            current_pr = t_pr[t_idx]
            
            idx_1m = min(np.searchsorted(t_ts, base_time - 60, side='left'), t_idx)
            idx_3m = min(np.searchsorted(t_ts, base_time - 180, side='left'), t_idx)
            idx_5m = min(np.searchsorted(t_ts, base_time - 300, side='left'), t_idx)
            idx_10m = min(np.searchsorted(t_ts, base_time - 600, side='left'), t_idx)
            idx_15m = min(np.searchsorted(t_ts, base_time - 900, side='left'), t_idx)

            def calc_ret(idx):
                return (current_pr - t_pr[idx]) / t_pr[idx] * 100.0 if t_pr[idx] > 0 else 0.0

            r_1m = calc_ret(idx_1m)
            r_3m = calc_ret(idx_3m)
            r_5m = calc_ret(idx_5m)
            r_10m = calc_ret(idx_10m)
            r_15m = calc_ret(idx_15m)

            def calc_vol(idx):
                prs = t_pr[idx:t_idx+1]
                return float(np.std(prs) / current_pr * 100.0) if len(prs) > 1 else 0.0

            vol_3m = calc_vol(idx_3m)
            vol_5m = calc_vol(idx_5m)
            vol_10m = calc_vol(idx_10m)
            vol_15m = calc_vol(idx_15m)

            def calc_vsum(idx): return float(np.sum(t_qty[idx:t_idx+1]))
            vsum_1m = calc_vsum(idx_1m)
            vsum_3m = calc_vsum(idx_3m)
            vsum_5m = calc_vsum(idx_5m)
            vsum_15m = calc_vsum(idx_15m)

            vspike_5m = vsum_5m / (vsum_15m / 3.0 + 1e-8)

            def calc_pressure(idx):
                buy_mask = t_is_buy[idx:t_idx+1] == 1
                sell_mask = t_is_buy[idx:t_idx+1] == 0
                qtys = t_qty[idx:t_idx+1]
                buy_v = np.sum(qtys[buy_mask])
                sell_v = np.sum(qtys[sell_mask])
                tot = buy_v + sell_v + 1e-8
                return buy_v / tot, sell_v / tot

            bp_1m, sp_1m = calc_pressure(idx_1m)
            bp_3m, sp_3m = calc_pressure(idx_3m)
            p_delta_3m = bp_1m - bp_3m

            o_idx = np.searchsorted(o_ts, base_time, side='right') - 1
            has_ob = (o_idx >= 0 and (base_time - o_ts[o_idx]) < 60.0)
            
            best_ask = o_ap[o_idx] if has_ob else current_pr
            best_bid = o_bp[o_idx] if has_ob else current_pr
            a_sz = o_asz[o_idx] if has_ob else 0.0
            b_sz = o_bsz[o_idx] if has_ob else 0.0
            
            ob_imb = (b_sz - a_sz) / (b_sz + a_sz + 1e-8) if has_ob else 0.0
            spread = (best_ask - best_bid) / best_bid * 100.0 if best_bid > 0 and best_ask >= best_bid else 0.0

            spread_med_3m = spread
            if has_ob:
                o_idx_3m = np.searchsorted(o_ts, base_time - 180, side='left')
                if o_idx > o_idx_3m:
                    sp_arr = (o_ap[o_idx_3m:o_idx+1] - o_bp[o_idx_3m:o_idx+1]) / o_bp[o_idx_3m:o_idx+1] * 100.0
                    sp_arr = sp_arr[sp_arr > 0]
                    if len(sp_arr) > 0: spread_med_3m = float(np.median(sp_arr))

            trend_5m = abs(r_5m) / (abs(r_1m) + abs(r_3m - r_1m) + 1e-8)
            pullback = r_10m * abs(r_1m) if (r_10m > 0 and r_1m < 0) else 0.0
            regime_mom = r_5m / (vol_5m + 1e-8)
            vol_brk = vol_5m / (vol_15m + 1e-8)
            liq_qual = (a_sz + b_sz) / (spread + 1e-8)

            feats = [
                r_1m, r_3m, r_5m, r_10m, r_15m,
                vol_3m, vol_5m, vol_10m, vol_15m,
                vsum_1m, vsum_3m, vsum_5m, vsum_15m,
                vspike_5m, bp_1m, bp_3m, sp_1m, sp_3m, p_delta_3m,
                ob_imb, spread, spread_med_3m,
                trend_5m, pullback, regime_mom, vol_brk, liq_qual
            ]
            X_list.append(feats)

            f_mask = (t_ts > base_time) & (t_ts <= base_time + 1800)
            f_ts_arr = t_ts[f_mask]
            
            if has_ob and len(o_ts) > 0:
                o_f_idx = np.searchsorted(o_ts, f_ts_arr) - 1
                o_f_idx = np.clip(o_f_idx, 0, len(o_ts)-1)
                f_pr_arr = o_bp[o_f_idx]
                invalid = (f_ts_arr - o_ts[o_f_idx]) > 60.0
                f_pr_arr[invalid] = t_pr[f_mask][invalid]
            else:
                f_pr_arr = t_pr[f_mask]

            entry_p = best_ask
            fallback_list.append(0 if has_ob else 1)

            res, w_f, t_f = _evaluate_future(entry_p, base_time, f_ts_arr, f_pr_arr)
            Y_net_list.append(res)
            Y_win_list.append(w_f)
            Y_to_list.append(t_f)

            base_time += STEP_SEC

    return X_list, Y_net_list, Y_win_list, Y_to_list, fallback_list

def main():
    print("========================================================================")
    print(" Regime-Aware Medium Horizon Mining")
    print("========================================================================")
    
    if not os.path.exists(SQLITE_CACHE):
        print("Dataset not found!")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)

    all_X, all_Y_net, all_Y_win, all_Y_to, all_fallback, all_M = [], [], [], [], [], []
    for m in TARGET_MARKETS:
        x, y, w, t, f = process_market(conn, m, mode)
        all_X.extend(x)
        all_Y_net.extend(y)
        all_Y_win.extend(w)
        all_Y_to.extend(t)
        all_fallback.extend(f)
        all_M.extend([m]*len(x))

    if not all_X: return

    X = np.array(all_X, dtype=np.float32)
    Y_net = np.array(all_Y_net, dtype=np.float32)
    Y_win = np.array(all_Y_win, dtype=np.int32)
    Y_to = np.array(all_Y_to, dtype=np.int32)
    M = np.array(all_M)
    F = np.array(all_fallback)
    
    N_snaps = len(X)
    train_size = int(N_snaps * 0.7)
    train_indices = np.arange(train_size)
    test_indices = np.arange(train_size + int(EMBARGO_SEC / STEP_SEC), N_snaps)
    test_indices = test_indices[test_indices < N_snaps]

    train_mask = np.zeros(N_snaps, dtype=bool)
    test_mask = np.zeros(N_snaps, dtype=bool)
    train_mask[train_indices] = True
    test_mask[test_indices] = True

    print(f"\nTotal Snapshots: {N_snaps} (Train: {train_mask.sum()}, Test: {test_mask.sum()})")
    
    X_train = X[train_mask]
    pct_vals = np.zeros((len(FEAT_NAMES), len(PCT_CANDS)), dtype=np.float32)
    for i in range(len(FEAT_NAMES)):
        pct_vals[i] = np.percentile(X_train[:, i], PCT_CANDS)

    all_candidates = []
    
    for fam_name, fam_feats in FAMILIES.items():
        print(f"\nEvaluating Family: {fam_name}")
        seed_idx = [FEAT_NAMES.index(f) for f in fam_feats]
        
        c1_list = []
        for fi in seed_idx:
            for d in [0, 1]:
                for pj in range(len(PCT_CANDS)):
                    val = float(pct_vals[fi, pj])
                    if np.isnan(val): continue
                    m = (X[:, fi] <= val) if d == 0 else (X[:, fi] >= val)
                    c_mask = m[train_indices]
                    if c_mask.sum() < 30: continue
                    mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                    best_c = int(np.argmax(mean_pnl))
                    if mean_pnl[best_c] <= 0: continue
                    tr_pnls = Y_net[train_indices[c_mask], best_c]
                    tr_gains = tr_pnls[tr_pnls > 0]
                    tr_losses = tr_pnls[tr_pnls < 0]
                    tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                    if tr_pf >= 1.1:
                        c1_list.append((float(mean_pnl[best_c]), [(fi, d, pj)], best_c, tr_pf, fam_name))
        
        c1_list.sort(key=lambda x: x[0], reverse=True)
        all_candidates.extend(c1_list[:50])
        
        c2_list = []
        for f1, f2 in combinations(seed_idx, 2):
            for d1 in [0, 1]:
                for d2 in [0, 1]:
                    for j1 in range(len(PCT_CANDS)):
                        for j2 in range(len(PCT_CANDS)):
                            val1, val2 = pct_vals[f1, j1], pct_vals[f2, j2]
                            if np.isnan(val1) or np.isnan(val2): continue
                            m1 = (X[:, f1] <= val1) if d1 == 0 else (X[:, f1] >= val1)
                            m2 = (X[:, f2] <= val2) if d2 == 0 else (X[:, f2] >= val2)
                            m_full = m1 & m2
                            c_mask = m_full[train_indices]
                            if c_mask.sum() < 30: continue
                            mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                            best_c = int(np.argmax(mean_pnl))
                            if mean_pnl[best_c] <= 0: continue
                            tr_pnls = Y_net[train_indices[c_mask], best_c]
                            tr_gains = tr_pnls[tr_pnls > 0]
                            tr_losses = tr_pnls[tr_pnls < 0]
                            tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                            if tr_pf >= 1.1:
                                c2_list.append((float(mean_pnl[best_c]), [(f1, d1, j1), (f2, d2, j2)], best_c, tr_pf, fam_name))
        
        c2_list.sort(key=lambda x: x[0], reverse=True)
        all_candidates.extend(c2_list[:50])

        c3_list = []
        for c2 in c2_list[:20]:
            f_idx2 = {c[0] for c in c2[1]}
            for f3 in seed_idx:
                if f3 in f_idx2: continue
                
                m_c2 = np.ones(N_snaps, dtype=bool)
                for (f_i, f_d, p_j) in c2[1]:
                    m_c2 &= (X[:, f_i] <= pct_vals[f_i, p_j]) if f_d == 0 else (X[:, f_i] >= pct_vals[f_i, p_j])

                for d3 in [0, 1]:
                    for j3 in range(len(PCT_CANDS)):
                        val3 = pct_vals[f3, j3]
                        if np.isnan(val3): continue
                        m3 = (X[:, f3] <= val3) if d3 == 0 else (X[:, f3] >= val3)
                        m_full = m_c2 & m3
                        c_mask = m_full[train_indices]
                        if c_mask.sum() < 30: continue
                        mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                        best_c = int(np.argmax(mean_pnl))
                        if mean_pnl[best_c] <= 0: continue
                        tr_pnls = Y_net[train_indices[c_mask], best_c]
                        tr_gains = tr_pnls[tr_pnls > 0]
                        tr_losses = tr_pnls[tr_pnls < 0]
                        tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                        if tr_pf >= 1.1:
                            c_desc = c2[1] + [(f3, d3, j3)]
                            c3_list.append((float(mean_pnl[best_c]), c_desc, best_c, tr_pf, fam_name))
                            
        c3_list.sort(key=lambda x: x[0], reverse=True)
        all_candidates.extend(c3_list[:50])

    all_candidates.sort(key=lambda x: x[0], reverse=True)
    top_train = all_candidates[:200]

    final_results = []
    for cand in top_train:
        train_net, c_desc, best_c, tr_pf, fam_name = cand
        m_full = np.ones(N_snaps, dtype=bool)
        for (f_i, f_d, p_j) in c_desc:
            m_full &= (X[:, f_i] <= pct_vals[f_i, p_j]) if f_d == 0 else (X[:, f_i] >= pct_vals[f_i, p_j])
            
        m_tr = m_full & train_mask
        m_te = m_full & test_mask
        
        te_pnls = Y_net[m_te, best_c]
        te_wins = Y_win[m_te, best_c]
        te_fb = F[m_te]
        te_markets = M[m_te]
        
        if len(te_pnls) < 20: continue
        
        te_gains = te_pnls[te_pnls > 0]
        te_losses = te_pnls[te_pnls < 0]
        te_pf = float(np.sum(te_gains) / abs(np.sum(te_losses))) if np.sum(te_losses) != 0 else 999.0
        te_net = float(np.mean(te_pnls))
        
        fb_rate = float(np.mean(te_fb))
        unique_m = np.unique(te_markets, return_counts=True)
        viable = sum(1 for c in unique_m[1] if c >= 2)
        top1 = float(np.max(unique_m[1]) / len(te_markets)) if len(te_markets)>0 else 1.0
        
        if te_net <= 0: continue
        
        cond_strs = []
        for (f_i, f_d, p_j) in c_desc:
            op = "<=" if f_d == 0 else ">="
            cond_strs.append(f"{FEAT_NAMES[f_i]} {op} p{PCT_CANDS[p_j]}")
            
        idx_rem = best_c
        c_tp = TP_CANDS[idx_rem // (len(SL_CANDS)*len(TO_CANDS))]
        idx_rem %= (len(SL_CANDS)*len(TO_CANDS))
        c_sl = SL_CANDS[idx_rem // len(TO_CANDS)]
        c_to = TO_CANDS[idx_rem % len(TO_CANDS)]

        is_strong = (te_net > 0.10 and te_pf >= 1.3 and len(te_pnls) >= 30 and viable >= 2 and top1 < 0.60 and fb_rate < 0.30)
        is_weak = (te_net > 0 and te_pf >= 1.15 and len(te_pnls) >= 20 and viable >= 2)

        if is_strong: judge = "MEDIUM_HORIZON_EDGE_FOUND"
        elif is_weak: judge = "WEAK_EDGE_NEEDS_MORE_DATA"
        else: judge = "MARKET_SPECIFIC_ONLY"

        final_results.append({
            "family": fam_name,
            "conditions": cond_strs,
            "train_net": train_net,
            "train_pf": tr_pf,
            "train_trades": int(m_tr.sum()),
            "test_net": te_net,
            "test_pf": te_pf,
            "test_trades": int(len(te_pnls)),
            "fallback_rate": fb_rate,
            "viable_markets": viable,
            "top1_share": top1,
            "best_combo": {"tp": c_tp, "sl": c_sl, "to": c_to},
            "judgement": judge
        })

    final_results.sort(key=lambda x: x["test_net"], reverse=True)

    if len(final_results) == 0:
        failure_reason = "TRAIN_RULES_TOO_WEAK" if len(top_train) == 0 else "COST_BARRIER_NOT_CLEARED"
    else:
        failure_reason = "NONE"

    print(f"\nFinal Candidates: {len(final_results)}")
    
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "REGIME_AWARE_MEDIUM_HORIZON_MINING",
        "failure_reason": failure_reason,
        "total_snapshots": N_snaps,
        "candidates": final_results[:20]
    }

    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    lines = [
        "========================================================================",
        "  REGIME-AWARE MEDIUM HORIZON MINING REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  ask/bid execution basis",
        "  test result decides survival",
        "========================================================================",
        f"Generated        : {report_data['generated_at']}",
        f"Total Snapshots  : {N_snaps}",
        f"Valid Candidates : {len(final_results)}",
        f"Failure Reason   : {failure_reason}",
        "",
        "[ Best Candidates ]"
    ]
    
    for i, res in enumerate(final_results[:10]):
        lines.append("-" * 72)
        lines.append(f" {i+1}. Rule: {' AND '.join(res['conditions'])}")
        lines.append(f"    Family     : {res['family']}")
        bc = res['best_combo']
        lines.append(f"    Best Combo : TP +{bc['tp']}% / SL {bc['sl']}% / TO {bc['to']}s")
        lines.append(f"    Judgement  : {res['judgement']}")
        lines.append(f"    Trades     : {res['train_trades']} Train / {res['test_trades']} Test")
        lines.append(f"    Test Win%  : N/A | Fallback: {res['fallback_rate']:.2%}")
        lines.append(f"    Train Net  : {res['train_net']:+10.4f}%  | Train PF: {res['train_pf']:.2f}")
        lines.append(f"    Test Net   : {res['test_net']:+10.4f}%  | Test PF : {res['test_pf']:.2f}")
        lines.append(f"    Markets    : {res['viable_markets']}/10 viable | Top1: {res['top1_share']:.2%}")

    lines.extend([
        "",
        "=" * 72,
        "  CONCLUSION & NEXT STEPS",
        "  - If test net is <= 0 for all candidates, the feature space must be rejected.",
        "=" * 72
    ])

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
