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
JSON_REPORT = os.path.join(OUT_DIR, "cost_aware_signal_search_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "cost_aware_signal_search_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
SLIPPAGE_CANDS = [0.03, 0.05, 0.10]

TP_CANDS = [0.20, 0.25, 0.30, 0.40, 0.50, 0.70]
SL_CANDS = [-0.08, -0.10, -0.15, -0.20, -0.30]
TO_CANDS = [120, 180, 300, 450, 600, 900]

N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
ENTRY_COOLDOWN_SEC = 60.0
MAX_ENTRIES_PER_MARKET_PER_CONDITION = 1000

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
            except Exception:
                continue

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
                    except Exception:
                        pass
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
        "o_asz": np.array(o_asz_list, dtype=float)[o_sort] if len(o_asz_list) > 0 else np.array([]),
        "o_spread": np.array(o_spread_list, dtype=float)[o_sort] if len(o_spread_list) > 0 else np.array([])
    }

def _evaluate_future(entry_pr, entry_ts, f_ts, f_pr):
    results = {}
    if len(f_pr) == 0:
        for tp in TP_CANDS:
            for sl in SL_CANDS:
                for to in TO_CANDS:
                    results[(tp, sl, to)] = {"res": "TIMEOUT", "pnl": 0.0}
        return results

    returns = (f_pr - entry_pr) / entry_pr * 100.0

    tp_hits = {}
    for tp in TP_CANDS:
        mask = returns >= tp
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        tp_hits[tp] = f_ts[idx] if idx >= 0 else np.inf

    sl_hits = {}
    for sl in SL_CANDS:
        mask = returns <= sl
        idx = int(np.argmax(mask)) if np.any(mask) else -1
        sl_hits[sl] = f_ts[idx] if idx >= 0 else np.inf

    for tp in TP_CANDS:
        for sl in SL_CANDS:
            for to in TO_CANDS:
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

def get_condition_grids():
    grids = []
    # A. strict_reversal
    for r30 in [3, 5, 10]:
        for s10 in [85, 90, 95]:
            for oi in [55, 60, 65]:
                grids.append({
                    "family": "strict_reversal",
                    "params": {"ret_30s_p": r30, "spr_10s_p": s10, "ob_imb_p": oi},
                    "train_entries": [], "test_entries": [],
                    "last_ts": {"train": {}, "test": {}}
                })
    # B. absorption_quality
    for s30 in [85, 90]:
        for r30 in [25, 35]:
            for oi in [60, 70]:
                for sp in [60]:
                    grids.append({
                        "family": "absorption_quality",
                        "params": {"spr_30s_p": s30, "ret_30s_p": r30, "ob_imb_p": oi, "spread_pct_p": sp},
                        "train_entries": [], "test_entries": [],
                        "last_ts": {"train": {}, "test": {}}
                    })
    # C. sweep_recovery_quality
    for r60 in [5, 10, 15]:
        for r10 in [55, 60, 65]:
            for bdc in [60, 70]:
                grids.append({
                    "family": "sweep_recovery_quality",
                    "params": {"ret_60s_p": r60, "ret_10s_p": r10, "bid_depth_change_30s_p": bdc, "ob_imb_p": 60},
                    "train_entries": [], "test_entries": [],
                    "last_ts": {"train": {}, "test": {}}
                })
    # D. continuation_quality
    for r30 in [85, 90]:
        for b10 in [75, 85]:
            for oi in [60, 70]:
                grids.append({
                    "family": "continuation_quality",
                    "params": {"ret_30s_p": r30, "bpr_10s_p": b10, "ob_imb_p": oi, "spread_pct_p": 60},
                    "train_entries": [], "test_entries": [],
                    "last_ts": {"train": {}, "test": {}}
                })
    # E. failed_breakdown_quality
    for r60 in [10, 15]:
        for r10 in [50, 60]:
            for s10 in [70]:
                for idel in [55]:
                    grids.append({
                        "family": "failed_breakdown_quality",
                        "params": {"ret_60s_p": r60, "ret_10s_p": r10, "spr_10s_p": s10, "imbalance_delta_30s_p": idel},
                        "train_entries": [], "test_entries": [],
                        "last_ts": {"train": {}, "test": {}}
                    })
    return grids

def check_grid_condition(grid, f, p):
    fam = grid["family"]
    params = grid["params"]
    
    if fam == "strict_reversal":
        if f["ret_30s"] <= p[f"ret_30s_p{params['ret_30s_p']}"] and \
           f["spr_10s"] >= p[f"spr_10s_p{params['spr_10s_p']}"] and \
           f["ob_imb"] >= p[f"ob_imb_p{params['ob_imb_p']}"]:
            return True
            
    elif fam == "absorption_quality":
        if f["spr_30s"] >= p[f"spr_30s_p{params['spr_30s_p']}"] and \
           f["ret_30s"] >= p[f"ret_30s_p{params['ret_30s_p']}"] and \
           f["ob_imb"] >= p[f"ob_imb_p{params['ob_imb_p']}"] and \
           f["spread_pct"] <= p[f"spread_pct_p{params['spread_pct_p']}"]:
            return True
            
    elif fam == "sweep_recovery_quality":
        if f["ret_60s"] <= p[f"ret_60s_p{params['ret_60s_p']}"] and \
           f["ret_10s"] >= p[f"ret_10s_p{params['ret_10s_p']}"] and \
           f["bid_depth_change_30s"] >= p[f"bid_depth_change_30s_p{params['bid_depth_change_30s_p']}"] and \
           f["ob_imb"] >= p[f"ob_imb_p{params['ob_imb_p']}"]:
            return True
            
    elif fam == "continuation_quality":
        if f["ret_30s"] >= p[f"ret_30s_p{params['ret_30s_p']}"] and \
           f["bpr_10s"] >= p[f"bpr_10s_p{params['bpr_10s_p']}"] and \
           f["ob_imb"] >= p[f"ob_imb_p{params['ob_imb_p']}"] and \
           f["spread_pct"] <= p[f"spread_pct_p{params['spread_pct_p']}"]:
            return True
            
    elif fam == "failed_breakdown_quality":
        if f["ret_60s"] <= p[f"ret_60s_p{params['ret_60s_p']}"] and \
           f["ret_10s"] >= p[f"ret_10s_p{params['ret_10s_p']}"] and \
           f["spr_10s"] <= p[f"spr_10s_p{params['spr_10s_p']}"] and \
           f["imbalance_delta_30s"] >= p[f"imbalance_delta_30s_p{params['imbalance_delta_30s_p']}"]:
            return True
            
    return False

def process_market(conn, market, mode, grids):
    print(f"  [{market}] Extracting snapshots...")
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None:
        return

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(TO_CANDS)

    if max_ts - min_ts < win_sec + max_to:
        return

    bands = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    train_bands = bands[:int(N_BANDS * 0.7)]
    test_bands = bands[int(N_BANDS * 0.7):]
    
    snapshots = []
    
    for split, band_starts in [("train", train_bands), ("test", test_bands)]:
        for w_start in band_starts:
            w_end = min(w_start + win_sec, max_ts)
            rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
            arrs = _parse_rows(rows, mode, market)
            if not arrs: continue

            t_ts, t_pr, t_qty, t_is_buy = arrs["t_ts"], arrs["t_pr"], arrs["t_qty"], arrs["t_is_buy"]
            o_ts, o_pr, o_bsz, o_asz, o_spread = arrs["o_ts"], arrs["o_pr"], arrs["o_bsz"], arrs["o_asz"], arrs["o_spread"]
            
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
                bpr_30s = float(b_30 / (b_30 + s_30 + 1e-8))
                
                ob_imb = 0.5
                ob_imb_30s_ago = 0.5
                bid_depth_change_30s = 1.0
                spread_pct = 0.0
                if len(o_ts) > 0:
                    oi_curr = ogidx(snap_ts) - 1
                    if oi_curr >= 0:
                        bsz_curr = o_bsz[oi_curr]
                        asz_curr = o_asz[oi_curr]
                        ob_imb = float(bsz_curr / (bsz_curr + asz_curr + 1e-8))
                        spread_pct = o_spread[oi_curr]
                        
                        oi_30s = ogidx(snap_ts - 30) - 1
                        if oi_30s >= 0:
                            bsz_old = o_bsz[oi_30s]
                            asz_old = o_asz[oi_30s]
                            ob_imb_30s_ago = float(bsz_old / (bsz_old + asz_old + 1e-8))
                            if bsz_old > 0:
                                bid_depth_change_30s = float(bsz_curr / bsz_old)
                            else:
                                bid_depth_change_30s = 1.0

                imbalance_delta_30s = ob_imb - ob_imb_30s_ago

                snapshots.append({
                    "split": split,
                    "ts": ts_curr,
                    "pr": pr_curr,
                    "arrs": arrs,
                    "feats": {
                        "ret_10s": ret_10s, "ret_30s": ret_30s, "ret_60s": ret_60s,
                        "spr_10s": spr_10s, "spr_30s": spr_30s, "bpr_10s": bpr_10s,
                        "ob_imb": ob_imb, "bid_depth_change_30s": bid_depth_change_30s,
                        "spread_pct": spread_pct, "imbalance_delta_30s": imbalance_delta_30s
                    }
                })

    if not snapshots: return
    
    train_snaps = [s for s in snapshots if s["split"] == "train"]
    if not train_snaps: return

    # Percentiles only from train
    feats_dict = defaultdict(list)
    for s in train_snaps:
        for k, v in s["feats"].items():
            feats_dict[k].append(v)
            
    p = {}
    percentile_list = [3, 5, 10, 15, 25, 35, 50, 55, 60, 65, 70, 75, 85, 90, 95]
    for k, v in feats_dict.items():
        arr = np.array(v)
        for pct in percentile_list:
            p[f"{k}_p{pct}"] = np.percentile(arr, pct)

    # Cache evals
    eval_cache = {}

    for s in snapshots:
        split = s["split"]
        ts = s["ts"]
        pr = s["pr"]
        f = s["feats"]
        arrs = s["arrs"]

        matched_grids = []
        for i, grid in enumerate(grids):
            if ts >= grid["last_ts"][split].get(market, 0) + ENTRY_COOLDOWN_SEC:
                if check_grid_condition(grid, f, p):
                    matched_grids.append(i)
                    
        if not matched_grids: continue

        if ts not in eval_cache:
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

            eval_cache[ts] = _evaluate_future(pr, ts, f_ts, f_pr)

        ev = eval_cache[ts]
        for grid_idx in matched_grids:
            grid = grids[grid_idx]
            if len(grid[f"{split}_entries"]) < MAX_ENTRIES_PER_MARKET_PER_CONDITION * 10: # Global limit across markets
                grid[f"{split}_entries"].append({"market": market, "ts": ts, "pr": pr, "eval": ev})
                grid["last_ts"][split][market] = ts

def analyze_combo(entries, key, fee_pct=UPBIT_FEE_PCT, slip_pct=0.05):
    if not entries: return {"net": 0.0, "trades": 0, "pf": 0.0, "win_rate": 0.0, "markets": {}}
    trades = len(entries)
    win = 0
    pnls = []
    markets = defaultdict(list)
    
    for e in entries:
        res = e["eval"][key]
        pnls.append(res["pnl"])
        if res["res"] == "WIN": win += 1
        markets[e["market"]].append(res["pnl"])
        
    net_pnls = np.array(pnls) - (fee_pct + slip_pct) * 2
    avg_net = np.mean(net_pnls)
    
    gains = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]
    pf = np.sum(gains) / abs(np.sum(losses)) if np.sum(losses) != 0 else 999.0
    
    m_res = {}
    for m, m_pnls in markets.items():
        m_net = np.array(m_pnls) - (fee_pct + slip_pct) * 2
        m_res[m] = {"trades": len(m_pnls), "net": np.mean(m_net)}
        
    return {
        "net": float(avg_net), "trades": trades, "pf": float(pf),
        "win_rate": win / trades, "markets": m_res
    }

def analyze_grid(grid):
    train = grid["train_entries"]
    test = grid["test_entries"]
    total = len(train) + len(test)
    
    if total < 20 or len(train) < 10:
        return None
        
    combos = list(product(TP_CANDS, SL_CANDS, TO_CANDS))
    
    best_train_net = -999.0
    best_combo = None
    
    # Optimize on Train
    for tp, sl, to in combos:
        key = (tp, sl, to)
        t_res = analyze_combo(train, key)
        if t_res["net"] > best_train_net:
            best_train_net = t_res["net"]
            best_combo = key
            
    if not best_combo: return None
    
    train_res = analyze_combo(train, best_combo)
    test_res = analyze_combo(test, best_combo)
    
    # Aggregated metrics for test
    top1_share, top2_share = 0, 0
    m_sorted = sorted(test_res["markets"].items(), key=lambda x: x[1]["trades"], reverse=True)
    if m_sorted and test_res["trades"] > 0:
        top1_share = m_sorted[0][1]["trades"] / test_res["trades"]
        if len(m_sorted) > 1:
            top2_share = (m_sorted[0][1]["trades"] + m_sorted[1][1]["trades"]) / test_res["trades"]
            
    viable_markets = sum(1 for m, st in test_res["markets"].items() if st["net"] > 0)
    
    warnings = []
    if train_res["net"] > 0 and test_res["net"] <= 0: warnings.append("OVERFIT_WARNING")
    if top1_share >= 0.4: warnings.append("MARKET_BIAS_WARNING")
    
    if test_res["net"] > 0 and test_res["pf"] >= 1.2 and total >= 50 and viable_markets >= 3 and top1_share < 0.4 and top2_share < 0.7:
        judgement = "COST_AWARE_EDGE_FOUND"
    elif train_res["net"] > 0 and test_res["net"] <= 0:
        judgement = "OVERFIT_ONLY"
    elif test_res["net"] > 0 and viable_markets < 3:
        judgement = "MARKET_SPECIFIC_ONLY"
    elif test_res["net"] <= 0:
        judgement = "COST_BARRIER_NOT_CLEARED"
    else:
        judgement = "NEED_MORE_DATA"

    return {
        "family": grid["family"],
        "params": grid["params"],
        "best_combo": {"tp": best_combo[0], "sl": best_combo[1], "to": best_combo[2]},
        "total_trades": total,
        "train_trades": train_res["trades"],
        "test_trades": test_res["trades"],
        "train_net_05": train_res["net"],
        "test_net_05": test_res["net"],
        "test_pf": test_res["pf"],
        "test_win_rate": test_res["win_rate"],
        "viable_markets": viable_markets,
        "top1_share": top1_share,
        "top2_share": top2_share,
        "warnings": warnings,
        "judgement": judgement
    }

def main():
    print("=" * 72)
    print(" Cost-Aware Signal Search (Train/Test Split)")
    print("=" * 72)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite not found: {SQLITE_CACHE}")
        return
    
    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    grids = get_condition_grids()
    print(f"Initialized {len(grids)} condition combinations to evaluate.")
    
    for market in TARGET_MARKETS:
        process_market(conn, market, mode, grids)
                
    conn.close()

    print("\nAnalyzing Train/Test Results...")
    results = []
    for g in grids:
        res = analyze_grid(g)
        if res: results.append(res)
        
    results.sort(key=lambda x: x["test_net_05"], reverse=True)

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "status": "COST_AWARE_SIGNAL_SEARCH",
        "results": results[:50] # save top 50
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  COST-AWARE SIGNAL SEARCH REPORT",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  Test split result is more important than train result.",
        "  slip 0.05% survival is the key gate.",
        "  If no condition survives, current signal space should be rejected.",
        "=" * 72,
        f"Generated  : {report_data['generated_at']}",
        f"Evaluated Combinations : {len(grids)}",
        f"Valid Results          : {len(results)}",
        ""
    ]
    
    survived = [r for r in results if r["judgement"] == "COST_AWARE_EDGE_FOUND"]
    lines.append(f"[ Survival Check : {len(survived)} configurations passed the gate ]")
    lines.append("")
    
    lines.append("[ Top 10 Configurations (by Test Net PnL slip 0.05%) ]")
    for i, res in enumerate(results[:10]):
        lines.append("-" * 72)
        lines.append(f" {i+1}. {res['family']}")
        lines.append(f"    Params     : {res['params']}")
        bc = res['best_combo']
        lines.append(f"    Best Combo : TP +{bc['tp']}% / SL {bc['sl']}% / TO {bc['to']}s")
        lines.append(f"    Judgement  : {res['judgement']}")
        lines.append(f"    Total Trds : {res['total_trades']} (Train: {res['train_trades']}, Test: {res['test_trades']})")
        lines.append(f"    Test Win%  : {res['test_win_rate']:.2%} | Test PF: {res['test_pf']:.2f}")
        lines.append(f"    Train Net  : {res['train_net_05']:>10.4f}%")
        lines.append(f"    Test Net   : {res['test_net_05']:>10.4f}%")
        lines.append(f"    Markets    : {res['viable_markets']}/10 viable | Top1: {res['top1_share']:.2%} | Top2: {res['top2_share']:.2%}")
        if res['warnings']:
            lines.append(f"    Warnings   : {', '.join(res['warnings'])}")
    
    lines.extend([
        "",
        "=" * 72,
        "  CONCLUSION & NEXT STEPS",
        "  - If COST_AWARE_EDGE_FOUND exists, proceed to Candidate Creation for those exact parameters.",
        "  - If all fail (OVERFIT_ONLY or COST_BARRIER_NOT_CLEARED), stop optimizing current features.",
        "=" * 72
    ])
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
