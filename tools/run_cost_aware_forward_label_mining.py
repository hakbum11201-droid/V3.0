import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import combinations

# Config
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "cost_aware_forward_label_mining_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "cost_aware_forward_label_mining_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
SLIP_PCT = 0.05
COST = (UPBIT_FEE_PCT + SLIP_PCT) * 2

TP_CANDS = [0.20, 0.30, 0.40, 0.50, 0.70, 1.00]
SL_CANDS = [-0.08, -0.10, -0.15, -0.20, -0.30]
TO_CANDS = [120, 180, 300, 450, 600, 900]

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_SNAPSHOTS_PER_MARKET = 5000
EMBARGO_SEC = 600

FEAT_NAMES = [
    "recent_return_5s", "recent_return_10s", "recent_return_30s", "recent_return_60s", "recent_return_120s",
    "sell_pressure_ratio_10s", "sell_pressure_ratio_30s", "buy_pressure_ratio_10s", "buy_pressure_ratio_30s",
    "pressure_delta_30s", "trade_volume_10s", "trade_volume_30s", "volume_spike_30s",
    "orderbook_imbalance", "bid_ask_spread_pct", "bid_depth_change_10s", "bid_depth_change_30s",
    "ask_depth_change_10s", "ask_depth_change_30s", "imbalance_delta_30s", "spread_delta_30s",
    "depth_recovery_score", "liquidity_vacuum_score", "micro_momentum_score"
]

PCT_CANDS = [1, 3, 5, 10, 15, 20, 25, 50, 75, 80, 85, 90, 95, 97, 99]

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

def _parse_rows(rows, mode):
    if not rows: return None
    t_ts_list, t_pr_list, t_qty_list, t_is_buy_list = [], [], [], []
    o_ts_list, o_pr_list, o_bsz_list, o_asz_list, o_spread_list = [], [], [], [], []

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
            except Exception: continue

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
                        pr = (ap + bp) / 2.0
                        spread_pct = (ap - bp) / pr * 100.0 if pr > 0 else 0.0
                        o_ts_list.append(ts)
                        o_pr_list.append(pr)
                        o_bsz_list.append(b_sz)
                        o_asz_list.append(a_sz)
                        o_spread_list.append(spread_pct)
                    except Exception: pass
            else:
                pr = None
                tp_val = payload.get("trade_price", payload.get("price"))
                if tp_val is not None:
                    try: pr = float(tp_val)
                    except Exception: pass

                if pr is not None:
                    q_val = payload.get("trade_volume", payload.get("volume", payload.get("qty")))
                    try: qty = float(q_val) if q_val is not None else 0.0
                    except Exception: qty = 0.0

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
        "o_pr": np.array(o_pr_list, dtype=float)[o_sort] if len(o_pr_list) > 0 else np.array([]),
        "o_bsz": np.array(o_bsz_list, dtype=float)[o_sort] if len(o_bsz_list) > 0 else np.array([]),
        "o_asz": np.array(o_asz_list, dtype=float)[o_sort] if len(o_asz_list) > 0 else np.array([]),
        "o_spread": np.array(o_spread_list, dtype=float)[o_sort] if len(o_spread_list) > 0 else np.array([])
    }

def _evaluate_future(entry_pr, entry_ts, f_ts, f_pr):
    results = np.zeros(len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS), dtype=np.float32)
    win_flags = np.zeros(len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS), dtype=np.int32)
    
    if len(f_pr) == 0:
        return results, win_flags

    returns = (f_pr - entry_pr) / entry_pr * 100.0
    tp_hits = {tp: np.inf for tp in TP_CANDS}
    for tp in TP_CANDS:
        mask = returns >= tp
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        if idx >= 0: tp_hits[tp] = f_ts[idx]

    sl_hits = {sl: np.inf for sl in SL_CANDS}
    for sl in SL_CANDS:
        mask = returns <= sl
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        if idx >= 0: sl_hits[sl] = f_ts[idx]

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
                    if t_tp < t_sl:
                        pnl, win = tp, 1
                    else:
                        pnl, win = sl, 0
                elif hit_tp:
                    pnl, win = tp, 1
                elif hit_sl:
                    pnl, win = sl, 0
                else:
                    idx_f = np.searchsorted(f_ts, limit_ts, side='right') - 1
                    if idx_f < 0: idx_f = 0
                    pnl = returns[idx_f] if idx_f < len(returns) else 0.0
                    win = 0

                results[idx_comb] = float(pnl) - COST
                win_flags[idx_comb] = win
                idx_comb += 1
    return results, win_flags

def process_market(conn, market, mode):
    print(f"  [{market}] Extracting snapshots...")
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None: return None, None, None

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to: return None, None, None

    bands = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    train_end = bands[int(N_BANDS * 0.7) - 1] + win_sec
    test_start = bands[int(N_BANDS * 0.7)]
    
    # Enforce embargo
    if test_start - train_end < EMBARGO_SEC:
        test_start = train_end + EMBARGO_SEC

    snaps_f = []
    snaps_eval = []
    snaps_win = []
    snaps_market = []
    snaps_split = []

    count = 0
    for w_start in bands:
        w_end = min(w_start + win_sec, max_ts)
        rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
        arrs = _parse_rows(rows, mode)
        if not arrs: continue

        t_ts, t_pr, t_qty, t_is_buy = arrs["t_ts"], arrs["t_pr"], arrs["t_qty"], arrs["t_is_buy"]
        o_ts, o_pr, o_bsz, o_asz, o_spread = arrs["o_ts"], arrs["o_pr"], arrs["o_bsz"], arrs["o_asz"], arrs["o_spread"]
        
        def gidx(v): return np.searchsorted(t_ts, v, side="right")
        def ogidx(v): return np.searchsorted(o_ts, v, side="right") if len(o_ts) > 0 else 0

        for snap_ts in np.arange(float(t_ts[0]) + 120, float(t_ts[-1]) - max_to, STEP_SEC):
            if count >= MAX_SNAPSHOTS_PER_MARKET: break
            
            # Determine split
            if snap_ts <= train_end: split = 0 # Train
            elif snap_ts >= test_start: split = 1 # Test
            else: continue # Embargo

            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            if i_curr == gidx(snap_ts - 5): continue # stale
            pr_curr = t_pr[i_curr - 1]

            def get_ret(sec):
                idx = gidx(snap_ts - sec)
                pr = t_pr[idx] if idx < len(t_pr) else pr_curr
                return float((pr_curr - pr) / pr * 100.0) if pr > 0 else 0.0

            ret_5s = get_ret(5)
            ret_10s = get_ret(10)
            ret_30s = get_ret(30)
            ret_60s = get_ret(60)
            ret_120s = get_ret(120)

            def get_pressure(idx_start):
                qty_win = t_qty[idx_start:i_curr]
                buy_win = t_is_buy[idx_start:i_curr]
                b_vol = np.sum(qty_win[buy_win == 1])
                s_vol = np.sum(qty_win[buy_win == 0])
                return b_vol, s_vol
                
            b_10, s_10 = get_pressure(gidx(snap_ts - 10))
            b_30, s_30 = get_pressure(gidx(snap_ts - 30))
            
            spr_10s = float(s_10 / (b_10 + s_10 + 1e-8))
            spr_30s = float(s_30 / (b_30 + s_30 + 1e-8))
            bpr_10s = float(b_10 / (b_10 + s_10 + 1e-8))
            bpr_30s = float(b_30 / (b_30 + s_30 + 1e-8))
            p_delta_30s = bpr_10s - bpr_30s
            vol_10s = b_10 + s_10
            vol_30s = b_30 + s_30
            vol_spike_30s = float(vol_10s / (vol_30s / 3.0 + 1e-8))
            
            ob_imb, ob_imb_10, ob_imb_30 = 0.5, 0.5, 0.5
            bd_change_10, bd_change_30 = 1.0, 1.0
            ad_change_10, ad_change_30 = 1.0, 1.0
            spread_pct, spread_30 = 0.0, 0.0
            lvs = 0.0
            
            if len(o_ts) > 0:
                oi_curr = ogidx(snap_ts) - 1
                if oi_curr >= 0:
                    bc, ac = o_bsz[oi_curr], o_asz[oi_curr]
                    ob_imb = float(bc / (bc + ac + 1e-8))
                    spread_pct = o_spread[oi_curr]
                    lvs = 1.0 / (bc + ac + 1e-8)
                    
                    oi_10 = ogidx(snap_ts - 10) - 1
                    if oi_10 >= 0:
                        b10, a10 = o_bsz[oi_10], o_asz[oi_10]
                        ob_imb_10 = float(b10 / (b10 + a10 + 1e-8))
                        bd_change_10 = float(bc / (b10 + 1e-8))
                        ad_change_10 = float(ac / (a10 + 1e-8))
                        
                    oi_30 = ogidx(snap_ts - 30) - 1
                    if oi_30 >= 0:
                        b30, a30 = o_bsz[oi_30], o_asz[oi_30]
                        ob_imb_30 = float(b30 / (b30 + a30 + 1e-8))
                        bd_change_30 = float(bc / (b30 + 1e-8))
                        ad_change_30 = float(ac / (a30 + 1e-8))
                        spread_30 = o_spread[oi_30]

            imb_delta_30s = ob_imb - ob_imb_30
            spread_delta_30s = spread_pct - spread_30
            drs = float(bd_change_30 / (ad_change_30 + 1e-8))
            mms = ret_5s * ob_imb

            feats = [
                ret_5s, ret_10s, ret_30s, ret_60s, ret_120s,
                spr_10s, spr_30s, bpr_10s, bpr_30s, p_delta_30s,
                vol_10s, vol_30s, vol_spike_30s, ob_imb, spread_pct,
                bd_change_10, bd_change_30, ad_change_10, ad_change_30,
                imb_delta_30s, spread_delta_30s, drs, lvs, mms
            ]

            # Forward Eval
            if len(o_ts) > 0:
                f_mask = (o_ts > snap_ts) & (o_ts <= snap_ts + max_to + 10)
                f_ts = o_ts[f_mask]
                f_pr = o_pr[f_mask]
            else:
                f_mask = (t_ts > snap_ts) & (t_ts <= snap_ts + max_to + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]
                
            if len(f_ts) == 0:
                f_mask = (t_ts > snap_ts) & (t_ts <= snap_ts + max_to + 10)
                f_ts = t_ts[f_mask]
                f_pr = t_pr[f_mask]

            res_arr, win_arr = _evaluate_future(pr_curr, snap_ts, f_ts, f_pr)
            
            snaps_f.append(feats)
            snaps_eval.append(res_arr)
            snaps_win.append(win_arr)
            snaps_market.append(TARGET_MARKETS.index(market))
            snaps_split.append(split)
            count += 1
            
        if count >= MAX_SNAPSHOTS_PER_MARKET: break
            
    return snaps_f, snaps_eval, snaps_win, snaps_market, snaps_split

def _format_cond(c_idx, c_dir, p_idx):
    fname = FEAT_NAMES[c_idx]
    pct = PCT_CANDS[p_idx]
    op = "<=" if c_dir == 0 else ">="
    return f"{fname} {op} p{pct}"

def main():
    print("=" * 72)
    print(" Cost-Aware Forward Label Mining")
    print("=" * 72)

    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    X, Y_net, Y_win, M, S = [], [], [], [], []
    for market in TARGET_MARKETS:
        f, ev, w, m, spl = process_market(conn, market, mode)
        if f:
            X.extend(f)
            Y_net.extend(ev)
            Y_win.extend(w)
            M.extend(m)
            S.extend(spl)
    conn.close()
    
    if not X: return
    
    X = np.array(X, dtype=np.float32)
    Y_net = np.array(Y_net, dtype=np.float32)
    Y_win = np.array(Y_win, dtype=np.int32)
    M = np.array(M, dtype=np.int32)
    S = np.array(S, dtype=np.int32)
    
    train_mask = (S == 0)
    test_mask = (S == 1)
    
    print(f"\nTotal Snapshots: {len(X)} (Train: {train_mask.sum()}, Test: {test_mask.sum()})")
    
    # Calculate Percentiles on Train
    X_train = X[train_mask]
    pct_vals = np.zeros((24, len(PCT_CANDS)), dtype=np.float32)
    for i in range(24):
        pct_vals[i] = np.percentile(X_train[:, i], PCT_CANDS)
        
    print("Evaluating 1-feature candidates...")
    candidates = []
    
    N_snaps = len(X)
    train_indices = np.where(train_mask)[0]
    
    for i in range(24):
        for j, pct in enumerate(PCT_CANDS):
            val = pct_vals[i, j]
            # dir 0: <=
            mask_0 = X[:, i] <= val
            c_mask_0 = mask_0[train_indices]
            if c_mask_0.sum() >= 50:
                mean_pnl = Y_net[train_indices[c_mask_0]].mean(axis=0)
                best_c = np.argmax(mean_pnl)
                if mean_pnl[best_c] > 0:
                    candidates.append((mean_pnl[best_c], [(i, 0, j)], best_c))
            
            # dir 1: >=
            mask_1 = X[:, i] >= val
            c_mask_1 = mask_1[train_indices]
            if c_mask_1.sum() >= 50:
                mean_pnl = Y_net[train_indices[c_mask_1]].mean(axis=0)
                best_c = np.argmax(mean_pnl)
                if mean_pnl[best_c] > 0:
                    candidates.append((mean_pnl[best_c], [(i, 1, j)], best_c))
                    
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_1_feats = candidates[:50]
    print(f"Found {len(candidates)} 1-feat candidates. Kept Top {len(top_1_feats)}.")
    
    print("Evaluating 2-feature candidates...")
    c2_list = []
    for c1, c2 in combinations(top_1_feats, 2):
        c_desc = c1[1] + c2[1]
        # check if conflicting on same feature
        f_idx = [c[0] for c in c_desc]
        if len(set(f_idx)) < 2: continue
        
        # build mask
        m_full = np.ones(N_snaps, dtype=bool)
        for (f_i, f_d, p_j) in c_desc:
            if f_d == 0: m_full &= (X[:, f_i] <= pct_vals[f_i, p_j])
            else: m_full &= (X[:, f_i] >= pct_vals[f_i, p_j])
            
        c_mask = m_full[train_indices]
        if c_mask.sum() >= 50:
            mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
            best_c = np.argmax(mean_pnl)
            if mean_pnl[best_c] > 0:
                c2_list.append((mean_pnl[best_c], c_desc, best_c))
                
    c2_list.sort(key=lambda x: x[0], reverse=True)
    top_2_feats = c2_list[:50]
    print(f"Found {len(c2_list)} 2-feat candidates. Kept Top {len(top_2_feats)}.")
    
    print("Evaluating 3-feature candidates...")
    c3_list = []
    for c2 in top_2_feats:
        for c1 in top_1_feats[:20]:
            c_desc = c2[1] + c1[1]
            f_idx = [c[0] for c in c_desc]
            if len(set(f_idx)) < 3: continue
            
            m_full = np.ones(N_snaps, dtype=bool)
            for (f_i, f_d, p_j) in c_desc:
                if f_d == 0: m_full &= (X[:, f_i] <= pct_vals[f_i, p_j])
                else: m_full &= (X[:, f_i] >= pct_vals[f_i, p_j])
                
            c_mask = m_full[train_indices]
            if c_mask.sum() >= 50:
                mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                best_c = np.argmax(mean_pnl)
                if mean_pnl[best_c] > 0:
                    c3_list.append((mean_pnl[best_c], c_desc, best_c))
                    
    c3_list.sort(key=lambda x: x[0], reverse=True)
    top_3_feats = c3_list[:50]
    print(f"Found {len(c3_list)} 3-feat candidates. Kept Top {len(top_3_feats)}.")
    
    all_cands = top_1_feats + top_2_feats + top_3_feats
    print(f"Total Combined Candidates: {len(all_cands)}")
    
    final_results = []
    for train_net, c_desc, best_c in all_cands:
        m_full = np.ones(N_snaps, dtype=bool)
        for (f_i, f_d, p_j) in c_desc:
            if f_d == 0: m_full &= (X[:, f_i] <= pct_vals[f_i, p_j])
            else: m_full &= (X[:, f_i] >= pct_vals[f_i, p_j])
            
        m_tr = m_full & train_mask
        m_te = m_full & test_mask
        
        tr_pnls = Y_net[m_tr, best_c]
        te_pnls = Y_net[m_te, best_c]
        te_wins = Y_win[m_te, best_c]
        te_markets = M[m_te]
        
        if len(tr_pnls) < 50: continue
        
        tr_gains = tr_pnls[tr_pnls > 0]
        tr_losses = tr_pnls[tr_pnls < 0]
        tr_pf = np.sum(tr_gains) / abs(np.sum(tr_losses)) if np.sum(tr_losses) != 0 else 999.0
        
        if tr_pf < 1.1: continue
        
        te_gains = te_pnls[te_pnls > 0]
        te_losses = te_pnls[te_pnls < 0]
        te_pf = np.sum(te_gains) / abs(np.sum(te_losses)) if np.sum(te_losses) != 0 else 999.0
        te_net = np.mean(te_pnls) if len(te_pnls) > 0 else 0.0
        te_win_rate = np.mean(te_wins) if len(te_wins) > 0 else 0.0
        
        m_counts = defaultdict(int)
        for m_idx in te_markets: m_counts[m_idx] += 1
        viable_markets = sum(1 for k, v in m_counts.items() if v > 0) # simplified
        top1_share = 0.0
        top2_share = 0.0
        if m_counts:
            sorted_m = sorted(m_counts.values(), reverse=True)
            top1_share = sorted_m[0] / len(te_pnls)
            if len(sorted_m) > 1: top2_share = (sorted_m[0] + sorted_m[1]) / len(te_pnls)
            
        # compute consecutive losses
        max_cons_losses = 0
        cur_cons = 0
        for pnl in te_pnls:
            if pnl < 0:
                cur_cons += 1
                max_cons_losses = max(max_cons_losses, cur_cons)
            else:
                cur_cons = 0
                
        tp_idx = best_c // (len(SL_CANDS) * len(TO_CANDS))
        sl_idx = (best_c // len(TO_CANDS)) % len(SL_CANDS)
        to_idx = best_c % len(TO_CANDS)
        
        bc_dict = {
            "tp": TP_CANDS[tp_idx],
            "sl": SL_CANDS[sl_idx],
            "to": TO_CANDS[to_idx]
        }
        
        warnings = []
        if tr_pnls.mean() > 0 and te_net <= 0: warnings.append("OVERFIT_WARNING")
        if top1_share >= 0.5: warnings.append("MARKET_BIAS_WARNING")
        
        if te_net > 0.03 and te_pf >= 1.3 and len(te_pnls) >= 50 and viable_markets >= 3 and top1_share < 0.4:
            judgement = "FORWARD_LABEL_EDGE_FOUND"
        elif te_net > 0 and te_pf >= 1.2 and len(te_pnls) >= 30 and viable_markets >= 2 and top1_share < 0.5 and max_cons_losses <= 8:
            judgement = "WEAK_EDGE_FOUND"
        elif tr_pnls.mean() > 0 and te_net <= 0:
            judgement = "OVERFIT_ONLY"
        elif te_net > 0 and viable_markets < 2:
            judgement = "MARKET_SPECIFIC_ONLY"
        else:
            judgement = "COST_BARRIER_NOT_CLEARED"
            
        final_results.append({
            "conditions": [_format_cond(*c) for c in c_desc],
            "best_combo": bc_dict,
            "train_net": float(tr_pnls.mean()),
            "test_net": float(te_net),
            "train_pf": float(tr_pf),
            "test_pf": float(te_pf),
            "train_trades": len(tr_pnls),
            "test_trades": len(te_pnls),
            "test_win_rate": float(te_win_rate),
            "max_cons_losses": max_cons_losses,
            "viable_markets": viable_markets,
            "top1_share": float(top1_share),
            "top2_share": float(top2_share),
            "warnings": warnings,
            "judgement": judgement
        })
        
    final_results.sort(key=lambda x: x["test_net"], reverse=True)
    
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "COST_AWARE_FORWARD_LABEL_MINING",
        "results": final_results[:100]
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  COST-AWARE FORWARD LABEL MINING REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  Train finds candidates, Test decides survival",
        "  slip 0.05% survival is the key gate.",
        "  If no candidate survives test, current data does not support this signal space",
        "=" * 72,
        f"Generated        : {report_data['generated_at']}",
        f"Total Snapshots  : {len(X)}",
        f"Total Candidates : {len(final_results)}",
        ""
    ]
    
    survived = [r for r in final_results if r["judgement"] in ("FORWARD_LABEL_EDGE_FOUND", "WEAK_EDGE_FOUND")]
    lines.append(f"[ Survival Check : {len(survived)} configurations passed the test gate ]")
    lines.append("")
    
    lines.append("[ Top 10 Configurations (by Test Net PnL slip 0.05%) ]")
    for i, res in enumerate(final_results[:10]):
        lines.append("-" * 72)
        lines.append(f" {i+1}. Rule: {' AND '.join(res['conditions'])}")
        bc = res['best_combo']
        lines.append(f"    Best Combo : TP +{bc['tp']}% / SL {bc['sl']}% / TO {bc['to']}s")
        lines.append(f"    Judgement  : {res['judgement']}")
        lines.append(f"    Trades     : {res['train_trades']} Train / {res['test_trades']} Test")
        lines.append(f"    Test Win%  : {res['test_win_rate']:.2%} | Max Loss Streak: {res['max_cons_losses']}")
        lines.append(f"    Train Net  : {res['train_net']:>10.4f}%  | Train PF: {res['train_pf']:.2f}")
        lines.append(f"    Test Net   : {res['test_net']:>10.4f}%  | Test PF : {res['test_pf']:.2f}")
        lines.append(f"    Markets    : {res['viable_markets']}/10 viable | Top1: {res['top1_share']:.2%} | Top2: {res['top2_share']:.2%}")
        if res['warnings']:
            lines.append(f"    Warnings   : {', '.join(res['warnings'])}")
    
    lines.extend([
        "",
        "=" * 72,
        "  CONCLUSION & NEXT STEPS",
        "  - Review top surviving conditions carefully to avoid over-optimism.",
        "  - If OVERFIT_ONLY dominates, structural edge is lacking.",
        "=" * 72
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
