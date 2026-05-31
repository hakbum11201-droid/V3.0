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
JSON_REPORT = os.path.join(OUT_DIR, "execution_aware_forward_label_mining_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "execution_aware_forward_label_mining_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
SLIP_PCT = 0.05
COST = (UPBIT_FEE_PCT + SLIP_PCT) * 2

TP_CANDS = [0.30, 0.40, 0.50, 0.70, 1.00, 1.20]
SL_CANDS = [-0.10, -0.15, -0.20, -0.30, -0.40]
TO_CANDS = [180, 300, 450, 600, 900]

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_SNAPSHOTS_PER_MARKET = 5000
EMBARGO_SEC = 600

FEAT_NAMES = [
    "recent_return_5s", "recent_return_10s", "recent_return_30s", "recent_return_60s", "recent_return_120s",
    "sell_pressure_ratio_10s", "sell_pressure_ratio_30s", "buy_pressure_ratio_10s", "buy_pressure_ratio_30s",
    "pressure_delta_30s", "trade_volume_10s", "trade_volume_30s", "volume_spike_30s",
    "orderbook_imbalance", "spread_pct", "bid_size", "ask_size", 
    "bid_depth_change_10s", "bid_depth_change_30s", "ask_depth_change_10s", "ask_depth_change_30s", 
    "imbalance_delta_30s", "spread_delta_30s", "depth_recovery_score", "liquidity_vacuum_score", "micro_momentum_score"
]

EXEC_FEATS = {"spread_pct", "ask_size", "bid_size", "orderbook_imbalance"}

PCT_CANDS = [1, 3, 5, 10, 15, 20, 25, 50, 60, 70, 75, 80, 85, 90, 95, 97, 99]

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
                        o_ts_list.append(ts)
                        o_bp_list.append(bp)
                        o_ap_list.append(ap)
                        o_bsz_list.append(b_sz)
                        o_asz_list.append(a_sz)
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
        "o_bp": np.array(o_bp_list, dtype=float)[o_sort] if len(o_bp_list) > 0 else np.array([]),
        "o_ap": np.array(o_ap_list, dtype=float)[o_sort] if len(o_ap_list) > 0 else np.array([]),
        "o_bsz": np.array(o_bsz_list, dtype=float)[o_sort] if len(o_bsz_list) > 0 else np.array([]),
        "o_asz": np.array(o_asz_list, dtype=float)[o_sort] if len(o_asz_list) > 0 else np.array([])
    }

def _evaluate_future(entry_pr, entry_ts, f_ts, f_pr):
    results = np.zeros(len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS), dtype=np.float32)
    win_flags = np.zeros(len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS), dtype=np.int32)
    to_flags = np.zeros(len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS), dtype=np.int32)
    
    if len(f_pr) == 0:
        for i in range(len(results)):
            to_flags[i] = 1
            results[i] = -COST
        return results, win_flags, to_flags

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
                        pnl, win, timeout = tp, 1, 0
                    else:
                        pnl, win, timeout = sl, 0, 0
                elif hit_tp:
                    pnl, win, timeout = tp, 1, 0
                elif hit_sl:
                    pnl, win, timeout = sl, 0, 0
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
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None: return None, None, None, None, None, None

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to: return None, None, None, None, None, None

    bands = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    train_end = bands[int(N_BANDS * 0.7) - 1] + win_sec
    test_start = bands[int(N_BANDS * 0.7)]
    
    if test_start - train_end < EMBARGO_SEC:
        test_start = train_end + EMBARGO_SEC

    snaps_f = []
    snaps_eval = []
    snaps_win = []
    snaps_to = []
    snaps_fb = []
    snaps_market = []
    snaps_split = []

    count = 0
    for w_start in bands:
        w_end = min(w_start + win_sec, max_ts)
        rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
        arrs = _parse_rows(rows, mode)
        if not arrs: continue

        t_ts, t_pr, t_qty, t_is_buy = arrs["t_ts"], arrs["t_pr"], arrs["t_qty"], arrs["t_is_buy"]
        o_ts, o_bp, o_ap, o_bsz, o_asz = arrs["o_ts"], arrs["o_bp"], arrs["o_ap"], arrs["o_bsz"], arrs["o_asz"]
        
        def gidx(v): return np.searchsorted(t_ts, v, side="right")
        def ogidx(v): return np.searchsorted(o_ts, v, side="right") if len(o_ts) > 0 else 0

        for snap_ts in np.arange(float(t_ts[0]) + 120, float(t_ts[-1]) - max_to, STEP_SEC):
            if count >= MAX_SNAPSHOTS_PER_MARKET: break
            
            if snap_ts <= train_end: split = 0
            elif snap_ts >= test_start: split = 1
            else: continue

            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            if i_curr == gidx(snap_ts - 5): continue
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
            bc, ac = 0.0, 0.0
            
            fallback = False
            entry_price = pr_curr
            
            if len(o_ts) > 0:
                oi_curr = ogidx(snap_ts) - 1
                if oi_curr >= 0:
                    bc, ac = o_bsz[oi_curr], o_asz[oi_curr]
                    bp, ap = o_bp[oi_curr], o_ap[oi_curr]
                    mid = (bp + ap) / 2.0
                    ob_imb = float(bc / (bc + ac + 1e-8))
                    spread_pct = float((ap - bp) / mid * 100.0) if mid > 0 else 0.0
                    lvs = 1.0 / (bc + ac + 1e-8)
                    if ap > 0:
                        entry_price = ap
                    else:
                        fallback = True
                        
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
                        mid30 = (o_bp[oi_30] + o_ap[oi_30]) / 2.0
                        spread_30 = float((o_ap[oi_30] - o_bp[oi_30]) / mid30 * 100.0) if mid30 > 0 else 0.0
                else:
                    fallback = True
            else:
                fallback = True

            imb_delta_30s = ob_imb - ob_imb_30
            spread_delta_30s = spread_pct - spread_30
            drs = float(bd_change_30 / (ad_change_30 + 1e-8))
            mms = ret_5s * ob_imb

            feats = [
                ret_5s, ret_10s, ret_30s, ret_60s, ret_120s,
                spr_10s, spr_30s, bpr_10s, bpr_30s, p_delta_30s,
                vol_10s, vol_30s, vol_spike_30s, ob_imb, spread_pct,
                bc, ac,
                bd_change_10, bd_change_30, ad_change_10, ad_change_30,
                imb_delta_30s, spread_delta_30s, drs, lvs, mms
            ]

            # Future eval using bid price if available
            f_fb = False
            if len(o_ts) > 0:
                f_mask = (o_ts > snap_ts) & (o_ts <= snap_ts + max_to + 10)
                f_ts_eval = o_ts[f_mask]
                f_pr_eval = o_bp[f_mask] # best bid
            else:
                f_mask = (t_ts > snap_ts) & (t_ts <= snap_ts + max_to + 10)
                f_ts_eval = t_ts[f_mask]
                f_pr_eval = t_pr[f_mask]
                f_fb = True
                
            if len(f_ts_eval) == 0:
                f_mask = (t_ts > snap_ts) & (t_ts <= snap_ts + max_to + 10)
                f_ts_eval = t_ts[f_mask]
                f_pr_eval = t_pr[f_mask]
                f_fb = True

            res_arr, win_arr, to_arr = _evaluate_future(entry_price, snap_ts, f_ts_eval, f_pr_eval)
            
            snaps_f.append(feats)
            snaps_eval.append(res_arr)
            snaps_win.append(win_arr)
            snaps_to.append(to_arr)
            snaps_fb.append(1 if fallback or f_fb else 0)
            snaps_market.append(TARGET_MARKETS.index(market))
            snaps_split.append(split)
            count += 1
            
        if count >= MAX_SNAPSHOTS_PER_MARKET: break
            
    return snaps_f, snaps_eval, snaps_win, snaps_to, snaps_fb, snaps_market, snaps_split

def _format_cond(c_idx, c_dir, p_idx):
    fname = FEAT_NAMES[c_idx]
    pct = PCT_CANDS[p_idx]
    op = "<=" if c_dir == 0 else ">="
    return f"{fname} {op} p{pct}"

def main():
    print("=" * 72)
    print(" Execution-Aware Forward Label Mining")
    print("=" * 72)

    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    X, Y_net, Y_win, Y_to, Y_fb, M, S = [], [], [], [], [], [], []
    for market in TARGET_MARKETS:
        f, ev, w, to_arr, fb, m, spl = process_market(conn, market, mode)
        if f:
            X.extend(f)
            Y_net.extend(ev)
            Y_win.extend(w)
            Y_to.extend(to_arr)
            Y_fb.extend(fb)
            M.extend(m)
            S.extend(spl)
    conn.close()
    
    if not X: return
    
    X = np.array(X, dtype=np.float32)
    Y_net = np.array(Y_net, dtype=np.float32)
    Y_win = np.array(Y_win, dtype=np.int32)
    Y_to = np.array(Y_to, dtype=np.int32)
    Y_fb = np.array(Y_fb, dtype=np.int32)
    M = np.array(M, dtype=np.int32)
    S = np.array(S, dtype=np.int32)
    
    train_mask = (S == 0)
    test_mask = (S == 1)
    
    print(f"\nTotal Snapshots: {len(X)} (Train: {train_mask.sum()}, Test: {test_mask.sum()})")
    
    X_train = X[train_mask]
    pct_vals = np.zeros((len(FEAT_NAMES), len(PCT_CANDS)), dtype=np.float32)
    for i in range(len(FEAT_NAMES)):
        pct_vals[i] = np.percentile(X_train[:, i], PCT_CANDS)
        
    # ── Feature separation analysis ────────────────────────────────────
    # Moved up to generate seed features for combos
    best_col = len(TP_CANDS) * len(SL_CANDS) * len(TO_CANDS) // 2  # use median combo as proxy
    Y_net_best = Y_net[:, best_col]
    pos_mask = Y_net_best > 0
    neg_mask = ~pos_mask
    feat_separation = []
    for i, fname in enumerate(FEAT_NAMES):
        col = X[:, i]
        if pos_mask.sum() == 0 or neg_mask.sum() == 0:
            continue
        pos_vals = col[pos_mask]
        neg_vals = col[neg_mask]
        pos_mean = float(np.mean(pos_vals))
        neg_mean = float(np.mean(neg_vals))
        pooled_std = float(np.std(np.concatenate([pos_vals, neg_vals])) + 1e-10)
        effect = (pos_mean - neg_mean) / pooled_std
        direction = "<=" if pos_mean < neg_mean else ">="
        feat_separation.append({
            "feature": fname,
            "f_idx": i,
            "pos_mean": round(pos_mean, 6),
            "neg_mean": round(neg_mean, 6),
            "pos_p10": round(float(np.percentile(pos_vals, 10)), 6),
            "pos_p50": round(float(np.percentile(pos_vals, 50)), 6),
            "pos_p90": round(float(np.percentile(pos_vals, 90)), 6),
            "neg_p10": round(float(np.percentile(neg_vals, 10)), 6),
            "neg_p50": round(float(np.percentile(neg_vals, 50)), 6),
            "neg_p90": round(float(np.percentile(neg_vals, 90)), 6),
            "effect_size": round(effect, 4),
            "direction": direction
        })
    feat_separation.sort(key=lambda x: abs(x["effect_size"]), reverse=True)
    feat_separation_top20 = feat_separation[:20]
    
    TOP_N_FEATURES_FOR_COMBO = 12
    seed_features = [f["f_idx"] for f in feat_separation_top20[:TOP_N_FEATURES_FOR_COMBO]]
    if len(seed_features) < TOP_N_FEATURES_FOR_COMBO:
        # Fallback to just first N features
        for idx in range(len(FEAT_NAMES)):
            if idx not in seed_features:
                seed_features.append(idx)
            if len(seed_features) >= TOP_N_FEATURES_FOR_COMBO:
                break
    seed_feature_names = [FEAT_NAMES[idx] for idx in seed_features]
    print(f"Seed Features for Combos ({len(seed_features)}): {seed_feature_names}")

    # ── Diagnostic counters ────────────────────────────────────────────
    skip_reasons = defaultdict(int)
    attempted_single_rules = 0
    attempted_pair_rules = 0
    attempted_triple_rules = 0

    # ── STRICT 1-feature pass (production gate) ────────────────────────
    print("Evaluating 1-feature candidates (strict)...")
    candidates = []

    N_snaps = len(X)
    train_indices = np.where(train_mask)[0]
    exec_idx_set = {FEAT_NAMES.index(n) for n in EXEC_FEATS}

    for i in range(len(FEAT_NAMES)):
        for j, pct in enumerate(PCT_CANDS):
            val = float(pct_vals[i, j])
            if np.isnan(val):
                skip_reasons["percentile_nan"] += 2  # both directions
                continue
            for c_dir in [0, 1]:
                attempted_single_rules += 1
                try:
                    mask = (X[:, i] <= val) if c_dir == 0 else (X[:, i] >= val)
                    c_mask = mask[train_indices]
                    n_train = int(c_mask.sum())
                    if n_train < 30:
                        skip_reasons["train_trades_below_min"] += 1
                        continue
                    mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                    best_c = int(np.argmax(mean_pnl))
                    if mean_pnl[best_c] <= 0:
                        skip_reasons["train_pf_below_min"] += 1
                        continue
                    tr_pnls = Y_net[train_indices[c_mask], best_c]
                    tr_gains = tr_pnls[tr_pnls > 0]
                    tr_losses = tr_pnls[tr_pnls < 0]
                    tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                    if tr_pf < 1.1:
                        skip_reasons["train_pf_below_min"] += 1
                        continue
                    candidates.append((mean_pnl[best_c], [(i, c_dir, j)], best_c, tr_pf))
                except Exception:
                    skip_reasons["invalid_rule_eval"] += 1

    candidates.sort(key=lambda x: x[0], reverse=True)
    top_1_feats = candidates[:100]
    print(f"Found {len(candidates)} 1-feat candidates. Kept Top {len(top_1_feats)}.")

    print("Evaluating 2-feature candidates (strict)...")
    c2_list = []
    # Test all pairs of seed features
    for f1, f2 in combinations(seed_features, 2):
        for j1 in range(len(PCT_CANDS)):
            val1 = float(pct_vals[f1, j1])
            if np.isnan(val1): continue
            for d1 in [0, 1]:
                m1 = (X[:, f1] <= val1) if d1 == 0 else (X[:, f1] >= val1)
                for j2 in range(len(PCT_CANDS)):
                    val2 = float(pct_vals[f2, j2])
                    if np.isnan(val2): continue
                    for d2 in [0, 1]:
                        attempted_pair_rules += 1
                        try:
                            m2 = (X[:, f2] <= val2) if d2 == 0 else (X[:, f2] >= val2)
                            m_full = m1 & m2
                            c_mask = m_full[train_indices]
                            if c_mask.sum() < 30:
                                skip_reasons["train_trades_below_min"] += 1
                                continue
                            mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                            best_c = int(np.argmax(mean_pnl))
                            if mean_pnl[best_c] <= 0:
                                skip_reasons["train_pf_below_min"] += 1
                                continue
                            tr_pnls = Y_net[train_indices[c_mask], best_c]
                            tr_gains = tr_pnls[tr_pnls > 0]
                            tr_losses = tr_pnls[tr_pnls < 0]
                            tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                            if tr_pf < 1.1:
                                skip_reasons["train_pf_below_min"] += 1
                                continue
                            c_desc = [(f1, d1, j1), (f2, d2, j2)]
                            c2_list.append((float(mean_pnl[best_c]), c_desc, best_c, tr_pf))
                        except Exception:
                            skip_reasons["invalid_rule_eval"] += 1

    c2_list.sort(key=lambda x: x[0], reverse=True)
    top_2_feats = c2_list[:100]
    print(f"Found {len(c2_list)} 2-feat candidates. Kept Top {len(top_2_feats)}.")

    print("Evaluating 3-feature candidates (strict)...")
    c3_list = []
    # Combine top 2-feat rules with seed features
    for c2 in top_2_feats:
        c_desc2 = c2[1]
        f_idx2 = {c[0] for c in c_desc2}
        
        for f3 in seed_features:
            if f3 in f_idx2: continue
            
            # Precompute mask for the 2-feat part
            m_c2 = np.ones(N_snaps, dtype=bool)
            for (f_i, f_d, p_j) in c_desc2:
                m_c2 &= (X[:, f_i] <= pct_vals[f_i, p_j]) if f_d == 0 else (X[:, f_i] >= pct_vals[f_i, p_j])
                
            for j3 in range(len(PCT_CANDS)):
                val3 = float(pct_vals[f3, j3])
                if np.isnan(val3): continue
                for d3 in [0, 1]:
                    attempted_triple_rules += 1
                    try:
                        m3 = (X[:, f3] <= val3) if d3 == 0 else (X[:, f3] >= val3)
                        m_full = m_c2 & m3
                        c_mask = m_full[train_indices]
                        if c_mask.sum() < 30:
                            skip_reasons["train_trades_below_min"] += 1
                            continue
                        mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                        best_c = int(np.argmax(mean_pnl))
                        if mean_pnl[best_c] <= 0:
                            skip_reasons["train_pf_below_min"] += 1
                            continue
                        tr_pnls = Y_net[train_indices[c_mask], best_c]
                        tr_gains = tr_pnls[tr_pnls > 0]
                        tr_losses = tr_pnls[tr_pnls < 0]
                        tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                        if tr_pf < 1.1:
                            skip_reasons["train_pf_below_min"] += 1
                            continue
                        c_desc = c_desc2 + [(f3, d3, j3)]
                        c3_list.append((float(mean_pnl[best_c]), c_desc, best_c, tr_pf))
                    except Exception:
                        skip_reasons["invalid_rule_eval"] += 1

    c3_list.sort(key=lambda x: x[0], reverse=True)
    top_3_feats = c3_list[:100]
    print(f"Found {len(c3_list)} 3-feat candidates. Kept Top {len(top_3_feats)}.")

    all_cands = top_1_feats + top_2_feats + top_3_feats

    # exec filter – track skips
    valid_cands = []
    for cand in all_cands:
        c_desc = cand[1]
        f_idx = {c[0] for c in c_desc}
        if f_idx.intersection(exec_idx_set):
            valid_cands.append(cand)
        else:
            skip_reasons["execution_filter_missing"] += 1

    print(f"Total Valid Combined Candidates (has execution feature): {len(valid_cands)}")

    # ── RELAXED DIAGNOSTIC 1-feature pass (non-production) ────────────
    print("Evaluating 1-feature candidates (relaxed diagnostic)...")
    RELAXED_MIN_TRAIN = 10
    RELAXED_MIN_TEST  = 5
    RELAXED_PF        = 1.0
    relaxed_skip = defaultdict(int)
    relaxed_attempted_single = 0
    relaxed_candidates = []

    for i in range(len(FEAT_NAMES)):
        for j in range(len(PCT_CANDS)):
            val = float(pct_vals[i, j])
            if np.isnan(val):
                relaxed_skip["percentile_nan"] += 2
                continue
            for c_dir in [0, 1]:
                relaxed_attempted_single += 1
                try:
                    mask = (X[:, i] <= val) if c_dir == 0 else (X[:, i] >= val)
                    c_mask = mask[train_indices]
                    if c_mask.sum() < RELAXED_MIN_TRAIN:
                        relaxed_skip["train_trades_below_min"] += 1
                        continue
                    mean_pnl = Y_net[train_indices[c_mask]].mean(axis=0)
                    best_c = int(np.argmax(mean_pnl))
                    if mean_pnl[best_c] <= 0:
                        relaxed_skip["train_pf_below_min"] += 1
                        continue
                    tr_pnls = Y_net[train_indices[c_mask], best_c]
                    tr_gains = tr_pnls[tr_pnls > 0]
                    tr_losses = tr_pnls[tr_pnls < 0]
                    tr_pf = float(np.sum(tr_gains) / abs(np.sum(tr_losses))) if np.sum(tr_losses) != 0 else 999.0
                    if tr_pf < RELAXED_PF:
                        relaxed_skip["train_pf_below_min"] += 1
                        continue
                    relaxed_candidates.append((float(mean_pnl[best_c]), [(i, c_dir, j)], best_c, tr_pf))
                except Exception:
                    relaxed_skip["invalid_rule_eval"] += 1

    relaxed_candidates.sort(key=lambda x: x[0], reverse=True)
    relaxed_top = relaxed_candidates[:20]
    print(f"Relaxed 1-feat candidates: {len(relaxed_candidates)}. Kept Top {len(relaxed_top)}.")

    final_results = []
    for train_net, c_desc, best_c, tr_pf in valid_cands:
        m_full = np.ones(N_snaps, dtype=bool)
        for (f_i, f_d, p_j) in c_desc:
            m_full &= (X[:, f_i] <= pct_vals[f_i, p_j]) if f_d == 0 else (X[:, f_i] >= pct_vals[f_i, p_j])
            
        m_tr = m_full & train_mask
        m_te = m_full & test_mask
        
        tr_pnls = Y_net[m_tr, best_c]
        te_pnls = Y_net[m_te, best_c]
        te_wins = Y_win[m_te, best_c]
        te_to = Y_to[m_te, best_c]
        te_fb = Y_fb[m_te]
        te_markets = M[m_te]
        
        if len(te_pnls) < 20: continue
        
        te_gains = te_pnls[te_pnls > 0]
        te_losses = te_pnls[te_pnls < 0]
        te_pf = np.sum(te_gains) / abs(np.sum(te_losses)) if np.sum(te_losses) != 0 else 999.0
        te_net = np.mean(te_pnls) if len(te_pnls) > 0 else 0.0
        te_win_rate = np.mean(te_wins) if len(te_wins) > 0 else 0.0
        te_to_rate = np.mean(te_to) if len(te_to) > 0 else 0.0
        te_fb_rate = np.mean(te_fb) if len(te_fb) > 0 else 0.0
        
        m_counts = defaultdict(int)
        for m_idx in te_markets: m_counts[m_idx] += 1
        viable_markets = sum(1 for k, v in m_counts.items() if v > 0)
        top1_share = 0.0
        top2_share = 0.0
        if m_counts:
            sorted_m = sorted(m_counts.values(), reverse=True)
            top1_share = sorted_m[0] / len(te_pnls)
            if len(sorted_m) > 1: top2_share = (sorted_m[0] + sorted_m[1]) / len(te_pnls)
            
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
        if top1_share >= 0.6: warnings.append("MARKET_BIAS_WARNING")
        if te_fb_rate >= 0.3: warnings.append("EXECUTION_QUALITY_WARNING")
        
        if te_net > 0.03 and te_pf >= 1.3 and len(te_pnls) >= 50 and viable_markets >= 3 and top1_share < 0.45 and te_fb_rate < 0.2 and te_to_rate <= 0.4:
            judgement = "EXECUTION_AWARE_EDGE_FOUND"
        elif te_net > 0 and te_pf >= 1.15 and len(te_pnls) >= 30 and viable_markets >= 2 and te_fb_rate < 0.3:
            judgement = "WEAK_EXECUTION_EDGE_FOUND"
        elif te_net <= 0:
            judgement = "COST_BARRIER_NOT_CLEARED"
        elif te_fb_rate >= 0.3:
            judgement = "EXECUTION_FILTER_NO_TRADES"
        elif top1_share >= 0.6:
            judgement = "MARKET_SPECIFIC_ONLY"
        else:
            judgement = "NEED_MORE_DATA"
            
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
            "test_timeout_ratio": float(te_to_rate),
            "fallback_rate": float(te_fb_rate),
            "max_cons_losses": max_cons_losses,
            "viable_markets": viable_markets,
            "top1_share": float(top1_share),
            "top2_share": float(top2_share),
            "warnings": warnings,
            "judgement": judgement
        })
        
    final_results.sort(key=lambda x: x["test_net"], reverse=True)

    if len(final_results) == 0:
        judgement_override = "REJECT_CURRENT_FEATURE_SPACE"
    else:
        judgement_override = final_results[0]["judgement"]

    # ── Relaxed diagnostic test-gate ──────────────────────────────────
    relaxed_final = []
    for train_net_r, c_desc_r, best_c_r, tr_pf_r in relaxed_top:
        try:
            m_full = np.ones(N_snaps, dtype=bool)
            for (f_i, f_d, p_j) in c_desc_r:
                m_full &= (X[:, f_i] <= pct_vals[f_i, p_j]) if f_d == 0 else (X[:, f_i] >= pct_vals[f_i, p_j])
            m_te = m_full & test_mask
            te_pnls = Y_net[m_te, best_c_r]
            if len(te_pnls) < RELAXED_MIN_TEST:
                continue
            te_net = float(np.mean(te_pnls))
            te_gains = te_pnls[te_pnls > 0]
            te_losses = te_pnls[te_pnls < 0]
            te_pf = float(np.sum(te_gains) / abs(np.sum(te_losses))) if np.sum(te_losses) != 0 else 999.0
            relaxed_final.append({
                "conditions": [_format_cond(*c) for c in c_desc_r],
                "train_net": round(float(train_net_r), 4),
                "test_net": round(te_net, 4),
                "train_pf": round(tr_pf_r, 2),
                "test_pf": round(te_pf, 2),
                "train_trades": int(np.sum(m_full & train_mask)),
                "test_trades": int(len(te_pnls)),
                "note": "RELAXED DIAGNOSTIC ONLY - NOT STRATEGY CANDIDATE"
            })
        except Exception:
            pass
    relaxed_final.sort(key=lambda x: x["test_net"], reverse=True)

    # -------------------------------------------------
    # Failure Funnel Diagnostics (Strict)
    # -------------------------------------------------
    total_snapshots = len(X)

    # Data funnel
    spread_idx = FEAT_NAMES.index("spread_pct")
    ask_idx = FEAT_NAMES.index("ask_size")
    bid_idx = FEAT_NAMES.index("bid_size")
    ob_imb_idx = FEAT_NAMES.index("orderbook_imbalance")
    snapshots_with_orderbook = int(np.count_nonzero(X[:, spread_idx] != 0))
    snapshots_with_trade_features = int(np.count_nonzero(np.any(X[:, 0:5] != 0, axis=1)))
    snapshots_with_valid_ask_bid = int(np.count_nonzero((X[:, ask_idx] > 0) & (X[:, bid_idx] > 0)))
    snapshots_with_valid_spread = int(np.count_nonzero(X[:, spread_idx] > 0))
    snapshots_with_future_path = total_snapshots
    spread_pcts_d = np.percentile(X[:, spread_idx], [50, 60, 70, 80])
    ask_pcts_d = np.percentile(X[:, ask_idx], [30, 40, 50])
    bid_pcts_d = np.percentile(X[:, bid_idx], [30, 40, 50])
    ob_imb_pcts_d = np.percentile(X[:, ob_imb_idx], [50, 60, 70])
    def count_filter(cond):
        return int(np.count_nonzero(cond))
    snapshots_after_execution_filters = {
        "spread_pct <= p50": count_filter(X[:, spread_idx] <= spread_pcts_d[0]),
        "spread_pct <= p60": count_filter(X[:, spread_idx] <= spread_pcts_d[1]),
        "spread_pct <= p70": count_filter(X[:, spread_idx] <= spread_pcts_d[2]),
        "spread_pct <= p80": count_filter(X[:, spread_idx] <= spread_pcts_d[3]),
        "ask_size >= p30": count_filter(X[:, ask_idx] >= ask_pcts_d[0]),
        "ask_size >= p40": count_filter(X[:, ask_idx] >= ask_pcts_d[1]),
        "ask_size >= p50": count_filter(X[:, ask_idx] >= ask_pcts_d[2]),
        "bid_size >= p30": count_filter(X[:, bid_idx] >= bid_pcts_d[0]),
        "bid_size >= p40": count_filter(X[:, bid_idx] >= bid_pcts_d[1]),
        "bid_size >= p50": count_filter(X[:, bid_idx] >= bid_pcts_d[2]),
        "orderbook_imbalance >= p50": count_filter(X[:, ob_imb_idx] >= ob_imb_pcts_d[0]),
        "orderbook_imbalance >= p60": count_filter(X[:, ob_imb_idx] >= ob_imb_pcts_d[1]),
        "orderbook_imbalance >= p70": count_filter(X[:, ob_imb_idx] >= ob_imb_pcts_d[2]),
    }

    # Label funnel – train split
    train_indices_set = train_mask
    Y_net_train = Y_net[train_indices_set]
    Y_net_test  = Y_net[test_mask]
    train_positive_005_count = int(np.sum(np.any(Y_net_train >= 0.05, axis=1)))
    test_positive_005_count  = int(np.sum(np.any(Y_net_test  >= 0.05, axis=1)))

    label_positive_003_count = int(np.sum(np.any(Y_net >= 0.03, axis=1)))
    label_positive_005_count = int(np.sum(np.any(Y_net >= 0.05, axis=1)))
    label_positive_010_count = int(np.sum(np.any(Y_net >= 0.10, axis=1)))
    positive_rate_003 = label_positive_003_count / total_snapshots if total_snapshots else 0
    positive_rate_005 = label_positive_005_count / total_snapshots if total_snapshots else 0
    positive_rate_010 = label_positive_010_count / total_snapshots if total_snapshots else 0
    timeout_count = int(np.sum(np.any(Y_to == 1, axis=1)))
    loss_count = int(np.sum(np.max(Y_net, axis=1) < 0))
    fallback_used_count = int(np.sum(Y_fb))
    fallback_rate = fallback_used_count / total_snapshots if total_snapshots else 0

    # Candidate search funnel (now using real counters)
    generated_single_feature_rules = len(candidates)
    generated_two_feature_rules = len(c2_list)
    generated_three_feature_rules = len(c3_list)
    rules_passing_min_train_trades = generated_single_feature_rules
    rules_passing_train_pf_1_1 = generated_single_feature_rules  # all in candidates already passed PF>=1.1
    rules_evaluated_on_test = len(valid_cands)
    rules_with_test_trades = 0
    rules_test_net_positive = 0
    rules_test_pf_1_15 = 0

    # -------------------------------------------------
    # Final result processing (existing logic)
    # -------------------------------------------------
    final_results.sort(key=lambda x: x["test_net"], reverse=True)

    if len(final_results) == 0:
        judgement_override = "REJECT_CURRENT_FEATURE_SPACE"
    else:
        judgement_override = final_results[0]["judgement"]

    # Update funnel metrics that depend on final_results
    rules_test_net_positive = sum(1 for r in final_results if r["test_net"] > 0)
    rules_test_pf_1_15 = sum(1 for r in final_results if r["test_pf"] >= 1.15)
    rules_with_test_trades = sum(1 for r in final_results if r["test_trades"] >= 20)
    final_valid_candidates = len(final_results)

    # ── Failure reason (revised with bug detection) ──────────────────
    if total_snapshots == 0:
        failure_reason = "NEED_MORE_DATA"
    elif label_positive_005_count == 0:
        failure_reason = "NO_EXECUTION_POSITIVE_LABELS"
    elif attempted_pair_rules == 0:
        failure_reason = "POSSIBLE_IMPLEMENTATION_BUG"
    elif all(v == 0 for v in snapshots_after_execution_filters.values()):
        failure_reason = "EXECUTION_FILTER_TOO_STRICT"
    elif final_valid_candidates == 0:
        if attempted_triple_rules > 0:
            failure_reason = "FEATURE_COMBO_NOT_STRONG_ENOUGH"
        else:
            failure_reason = "TRAIN_RULES_TOO_WEAK"
    else:
        failure_reason = "NEED_MORE_DATA"

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "EXECUTION_AWARE_FORWARD_LABEL_MINING",
        "judgement": judgement_override,
        "failure_reason": failure_reason,
        "funnel": {
            "total_snapshots": total_snapshots,
            "data_funnel": {
                "snapshots_with_orderbook": snapshots_with_orderbook,
                "snapshots_with_trade_features": snapshots_with_trade_features,
                "snapshots_with_valid_ask_bid": snapshots_with_valid_ask_bid,
                "snapshots_with_valid_spread": snapshots_with_valid_spread,
                "snapshots_with_future_path": snapshots_with_future_path,
                "snapshots_after_execution_filters": snapshots_after_execution_filters
            },
            "label_funnel": {
                "train_rows": int(train_mask.sum()),
                "test_rows": int(test_mask.sum()),
                "train_positive_005_count": train_positive_005_count,
                "train_positive_005_rate": round(train_positive_005_count / int(train_mask.sum()), 4) if train_mask.sum() else 0,
                "test_positive_005_count": test_positive_005_count,
                "label_positive_003_count": label_positive_003_count,
                "label_positive_005_count": label_positive_005_count,
                "label_positive_010_count": label_positive_010_count,
                "positive_rate_003": positive_rate_003,
                "positive_rate_005": positive_rate_005,
                "positive_rate_010": positive_rate_010,
                "timeout_count": timeout_count,
                "loss_count": loss_count,
                "fallback_used_count": fallback_used_count,
                "fallback_rate": fallback_rate
            },
            "execution_filter_funnel": snapshots_after_execution_filters,
            "candidate_search_funnel": {
                "feature_count": len(FEAT_NAMES),
                "feature_names_used": FEAT_NAMES,
                "seed_features_for_combo": seed_feature_names,
                "seed_feature_count": len(seed_features),
                "pair_search_enabled_even_without_single_candidates": True,
                "triple_search_enabled_even_without_single_candidates": True,
                "percentile_grid_count": len(PCT_CANDS),
                "attempted_single_rules": attempted_single_rules,
                "attempted_pair_rules": attempted_pair_rules,
                "attempted_triple_rules": attempted_triple_rules,
                "generated_single_feature_rules": generated_single_feature_rules,
                "generated_two_feature_rules": generated_two_feature_rules,
                "generated_three_feature_rules": generated_three_feature_rules,
                "rules_passing_min_train_trades": rules_passing_min_train_trades,
                "rules_passing_train_pf_1_1": rules_passing_train_pf_1_1,
                "rules_evaluated_on_test": rules_evaluated_on_test,
                "rules_with_test_trades": rules_with_test_trades,
                "rules_test_net_positive": rules_test_net_positive,
                "rules_test_pf_1_15": rules_test_pf_1_15,
                "final_valid_candidates": final_valid_candidates,
                "skip_reason_counts": dict(skip_reasons)
            },
            "relaxed_diagnostic": {
                "relaxed_attempted_single_rules": relaxed_attempted_single,
                "relaxed_candidates_train_pass": len(relaxed_candidates),
                "relaxed_candidates_test_pass": len(relaxed_final),
                "relaxed_skip_reasons": dict(relaxed_skip),
                "relaxed_top10": relaxed_final[:10]
            },
            "feature_separation_top20": feat_separation_top20
        },
        "results": final_results[:100]
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    lf = report_data["funnel"]
    lcs = lf["candidate_search_funnel"]
    llf = lf["label_funnel"]
    lrd = lf["relaxed_diagnostic"]
    lines = [
        "=" * 72,
        "  EXECUTION-AWARE FORWARD LABEL MINING REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  RELAXED DIAGNOSTIC ONLY - NOT STRATEGY CANDIDATE",
        "  entry uses best_ask and exit uses best_bid",
        "  mid_price profit is not accepted as production evidence",
        "  slip 0.05% survival is the key gate",
        "  test result decides survival",
        "=" * 72,
        f"Generated        : {report_data['generated_at']}",
        f"Total Snapshots  : {total_snapshots}  (Train: {llf['train_rows']}  Test: {llf['test_rows']})",
        f"Valid Candidates : {final_valid_candidates}",
        f"Failure Reason   : {failure_reason}",
        "",
        "[ Data Funnel ]",
        f"  snapshots_with_orderbook       : {lf['data_funnel']['snapshots_with_orderbook']}",
        f"  snapshots_with_trade_features  : {lf['data_funnel']['snapshots_with_trade_features']}",
        f"  snapshots_with_valid_ask_bid   : {lf['data_funnel']['snapshots_with_valid_ask_bid']}",
        f"  snapshots_with_valid_spread    : {lf['data_funnel']['snapshots_with_valid_spread']}",
        "",
        "[ Label Funnel ]",
        f"  train_positive_0.05%           : {llf['train_positive_005_count']}  ({llf['train_positive_005_rate']:.2%})",
        f"  test_positive_0.05%            : {llf['test_positive_005_count']}",
        f"  label_positive_0.03%           : {llf['label_positive_003_count']}  ({llf['positive_rate_003']:.2%})",
        f"  label_positive_0.05%           : {llf['label_positive_005_count']}  ({llf['positive_rate_005']:.2%})",
        f"  label_positive_0.10%           : {llf['label_positive_010_count']}  ({llf['positive_rate_010']:.2%})",
        f"  fallback_rate                  : {llf['fallback_rate']:.2%}",
        f"  timeout_count                  : {llf['timeout_count']}",
        f"  loss_count                     : {llf['loss_count']}",
        "",
        "[ Execution Filter Funnel ]",
    ]
    for k, v in snapshots_after_execution_filters.items():
        pct_pass = v / total_snapshots if total_snapshots else 0
        lines.append(f"  {k:<35}: {v:>6}  ({pct_pass:.1%})")
    lines += [
        "",
        "[ Candidate Search Funnel (STRICT) ]",
        f"  feature_count                  : {lcs['feature_count']}",
        f"  seed_features_for_combo        : {lcs['seed_feature_count']} (see JSON for names)",
        f"  pair_search_enabled_even_without_single: {lcs['pair_search_enabled_even_without_single_candidates']}",
        f"  triple_search_enabled_even_without_single: {lcs['triple_search_enabled_even_without_single_candidates']}",
        f"  percentile_grid_count          : {lcs['percentile_grid_count']}",
        f"  attempted_single_rules         : {lcs['attempted_single_rules']}",
        f"  attempted_pair_rules           : {lcs['attempted_pair_rules']}",
        f"  attempted_triple_rules         : {lcs['attempted_triple_rules']}",
        f"  generated_single_feat_rules    : {lcs['generated_single_feature_rules']}",
        f"  generated_two_feat_rules       : {lcs['generated_two_feature_rules']}",
        f"  generated_three_feat_rules     : {lcs['generated_three_feature_rules']}",
        f"  rules_passing_train_pf_1.1     : {lcs['rules_passing_train_pf_1_1']}",
        f"  rules_evaluated_on_test        : {lcs['rules_evaluated_on_test']}",
        f"  rules_with_test_trades (>=20)  : {lcs['rules_with_test_trades']}",
        f"  rules_test_net_positive        : {lcs['rules_test_net_positive']}",
        f"  rules_test_pf_>=1.15           : {lcs['rules_test_pf_1_15']}",
        f"  final_valid_candidates         : {lcs['final_valid_candidates']}",
        "",
        "[ Skip Reason Counts (STRICT) ]",
    ]
    for k, v in sorted(lcs['skip_reason_counts'].items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<40}: {v}")
    lines += [
        "",
        "[ Relaxed Diagnostic (NOT PRODUCTION CANDIDATE) ]",
        f"  relaxed_attempted_single_rules : {lrd['relaxed_attempted_single_rules']}",
        f"  relaxed_candidates_train_pass  : {lrd['relaxed_candidates_train_pass']}",
        f"  relaxed_candidates_test_pass   : {lrd['relaxed_candidates_test_pass']}",
        f"  relaxed_skip: {dict(lrd['relaxed_skip_reasons'])}",
        "",
        "[ Top 10 Relaxed Diagnostic Candidates (NOT STRATEGY CANDIDATE) ]",
    ]
    for i, r in enumerate(relaxed_final[:10]):
        lines.append(f"  {i+1}. {' AND '.join(r['conditions'])}  train_net={r['train_net']:+.4f}%  test_net={r['test_net']:+.4f}%  test_trades={r['test_trades']}")
    lines += [
        "",
        "[ Feature Separation Top 20 (effect size by best-combo net > 0 vs <= 0) ]",
    ]
    for f in feat_separation_top20[:20]:
        lines.append(f"  {f['feature']:<30} eff={f['effect_size']:+.3f}  dir={f['direction']}  pos_mean={f['pos_mean']:.5f}  neg_mean={f['neg_mean']:.5f}")
    lines.append("")

    survived = [r for r in final_results if r["judgement"] in ("EXECUTION_AWARE_EDGE_FOUND", "WEAK_EXECUTION_EDGE_FOUND")]
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
        lines.append(f"    Test Win%  : {res['test_win_rate']:.2%} | Fallback: {res['fallback_rate']:.2%}")
        lines.append(f"    Train Net  : {res['train_net']:+10.4f}%  | Train PF: {res['train_pf']:.2f}")
        lines.append(f"    Test Net   : {res['test_net']:+10.4f}%  | Test PF : {res['test_pf']:.2f}")
        lines.append(f"    Markets    : {res['viable_markets']}/10 viable | Top1: {res['top1_share']:.2%} | Top2: {res['top2_share']:.2%}")
        if res['warnings']:
            lines.append(f"    Warnings   : {', '.join(res['warnings'])}")

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
