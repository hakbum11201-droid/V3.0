import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict

# Config
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "forward_label_candidate_robustness_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "forward_label_candidate_robustness_latest.txt")

TARGET_MARKETS = [
    "KRW-BTC", "KRW-DOGE", "KRW-ETH", "KRW-HP", "KRW-ONDO",
    "KRW-PIEVERSE", "KRW-SAHARA", "KRW-SOL", "KRW-UP2", "KRW-XRP"
]

UPBIT_FEE_PCT = 0.05
N_BANDS = 20
WINDOW_MIN = 120
STEP_SEC = 10.0
MAX_SNAPSHOTS_PER_MARKET = 5000
EMBARGO_SEC = 600

# Base exit combo
BASE_TP = 0.7
BASE_SL = -0.3
BASE_TO = 300

# Sensitivities
SENSITIVITIES = [
    (0.7, -0.3, 300),
    (0.5, -0.3, 300),
    (1.0, -0.3, 300),
    (0.7, -0.2, 300),
    (0.7, -0.3, 600)
]

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
    results = {}
    if len(f_pr) == 0:
        for tp, sl, to in SENSITIVITIES:
            results[(tp, sl, to)] = {"res": "TIMEOUT", "pnl": 0.0}
        return results

    returns = (f_pr - entry_pr) / entry_pr * 100.0
    
    tp_hits = {}
    for tp, _, _ in SENSITIVITIES:
        if tp not in tp_hits:
            mask = returns >= tp
            idx = int(np.argmax(mask)) if np.any(mask) else -1
            tp_hits[tp] = f_ts[idx] if idx >= 0 else np.inf

    sl_hits = {}
    for _, sl, _ in SENSITIVITIES:
        if sl not in sl_hits:
            mask = returns <= sl
            idx = int(np.argmax(mask)) if np.any(mask) else -1
            sl_hits[sl] = f_ts[idx] if idx >= 0 else np.inf

    for tp, sl, to in SENSITIVITIES:
        limit_ts = entry_ts + to
        t_tp = tp_hits[tp]
        t_sl = sl_hits[sl]

        hit_tp = t_tp <= limit_ts
        hit_sl = t_sl <= limit_ts

        if hit_tp and hit_sl:
            if t_tp < t_sl: pnl, res = tp, "WIN"
            else: pnl, res = sl, "LOSS"
        elif hit_tp:
            pnl, res = tp, "WIN"
        elif hit_sl:
            pnl, res = sl, "LOSS"
        else:
            idx_f = np.searchsorted(f_ts, limit_ts, side='right') - 1
            if idx_f < 0: idx_f = 0
            pnl = returns[idx_f] if idx_f < len(returns) else 0.0
            res = "TIMEOUT"

        results[(tp, sl, to)] = {"res": res, "pnl": float(pnl)}
        
    return results

def process_market(conn, market, mode):
    print(f"  [{market}] Extracting snapshots...")
    row = conn.execute("SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)).fetchone()
    if not row or row[0] is None: return None

    min_ts, max_ts = float(row[0]), float(row[1])
    win_sec = WINDOW_MIN * 60
    max_to = max(s[2] for s in SENSITIVITIES)

    if max_ts - min_ts < win_sec + max_to: return None

    bands = np.linspace(min_ts, max(min_ts, max_ts - win_sec - max_to), N_BANDS)
    
    snaps = []
    count = 0
    
    for band_idx, w_start in enumerate(bands):
        w_end = min(w_start + win_sec, max_ts)
        rows = _load_window(conn, market, w_start, w_end + max_to + 10, mode)
        arrs = _parse_rows(rows, mode)
        if not arrs: continue

        t_ts, t_pr, t_qty, t_is_buy = arrs["t_ts"], arrs["t_pr"], arrs["t_qty"], arrs["t_is_buy"]
        o_ts, o_pr, o_bsz, o_asz, o_spread = arrs["o_ts"], arrs["o_pr"], arrs["o_bsz"], arrs["o_asz"], arrs["o_spread"]
        
        def gidx(v): return np.searchsorted(t_ts, v, side="right")
        def ogidx(v): return np.searchsorted(o_ts, v, side="right") if len(o_ts) > 0 else 0

        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - max_to, STEP_SEC):
            if count >= MAX_SNAPSHOTS_PER_MARKET: break

            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            if i_curr == gidx(snap_ts - 5): continue
            pr_curr = t_pr[i_curr - 1]

            def get_ret(sec):
                idx = gidx(snap_ts - sec)
                pr = t_pr[idx] if idx < len(t_pr) else pr_curr
                return float((pr_curr - pr) / pr * 100.0) if pr > 0 else 0.0

            ret_5s = get_ret(5)
            ret_30s = get_ret(30)
            ret_60s = get_ret(60)

            ob_imb = 0.5
            if len(o_ts) > 0:
                oi_curr = ogidx(snap_ts) - 1
                if oi_curr >= 0:
                    bc, ac = o_bsz[oi_curr], o_asz[oi_curr]
                    ob_imb = float(bc / (bc + ac + 1e-8))

            mms = ret_5s * ob_imb

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

            res_dict = _evaluate_future(pr_curr, snap_ts, f_ts, f_pr)
            
            snaps.append({
                "market": market,
                "ts": snap_ts,
                "band_idx": band_idx,
                "feats": {
                    "mms": mms,
                    "ret_30s": ret_30s,
                    "ret_60s": ret_60s
                },
                "eval": res_dict
            })
            count += 1
            
        if count >= MAX_SNAPSHOTS_PER_MARKET: break
            
    return snaps

def analyze_entries(entries, tp, sl, to, slip_pct=0.05):
    if not entries:
        return {
            "trades": 0, "win_rate": 0.0, "net": 0.0, 
            "pf": 0.0, "max_cons_losses": 0, "timeout_ratio": 0.0,
            "markets": {}
        }
        
    trades = len(entries)
    win_cnt = 0
    to_cnt = 0
    pnls = []
    markets = defaultdict(list)
    
    for e in entries:
        res = e["eval"][(tp, sl, to)]
        pnls.append(res["pnl"])
        if res["res"] == "WIN": win_cnt += 1
        elif res["res"] == "TIMEOUT": to_cnt += 1
        markets[e["market"]].append(res["pnl"])
        
    cost = (UPBIT_FEE_PCT + slip_pct) * 2
    net_pnls = np.array(pnls) - cost
    
    gains = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]
    pf = np.sum(gains) / abs(np.sum(losses)) if np.sum(losses) != 0 else 999.0
    
    m_res = {}
    for m, m_pnls in markets.items():
        m_net = np.array(m_pnls) - cost
        m_res[m] = {"trades": len(m_pnls), "net": float(np.mean(m_net))}
        
    max_cons_losses = 0
    cur_cons = 0
    for pnl in net_pnls:
        if pnl < 0:
            cur_cons += 1
            max_cons_losses = max(max_cons_losses, cur_cons)
        else:
            cur_cons = 0
            
    return {
        "trades": trades,
        "win_rate": float(win_cnt / trades),
        "timeout_ratio": float(to_cnt / trades),
        "net": float(np.mean(net_pnls)),
        "pf": float(pf),
        "max_cons_losses": int(max_cons_losses),
        "markets": m_res,
        "raw_net_pnls": net_pnls.tolist(),
        "raw_markets": [e["market"] for e in entries]
    }

def main():
    print("=" * 72)
    print(" Forward Label Candidate Robustness Retest")
    print("=" * 72)

    conn = sqlite3.connect(SQLITE_CACHE)
    mode = _get_schema_mode(conn)
    
    all_snaps = []
    for market in TARGET_MARKETS:
        s = process_market(conn, market, mode)
        if s: all_snaps.extend(s)
    conn.close()
    
    if not all_snaps: return
    print(f"\nTotal extracted snapshots: {len(all_snaps)}")
    
    # Base Split: Train=0~13, Test=14~19
    train_snaps_base = [s for s in all_snaps if s["band_idx"] <= 13]
    test_snaps_base = [s for s in all_snaps if s["band_idx"] >= 14]
    
    mms_train = [s["feats"]["mms"] for s in train_snaps_base]
    r30_train = [s["feats"]["ret_30s"] for s in train_snaps_base]
    r60_train = [s["feats"]["ret_60s"] for s in train_snaps_base]
    
    p1_mms = np.percentile(mms_train, 1)
    p3_r30 = np.percentile(r30_train, 3)
    p3_r60 = np.percentile(r60_train, 3)
    
    def apply_rule(snaps, p_mms, p_r30, p_r60):
        return [s for s in snaps if s["feats"]["mms"] <= p_mms and 
                s["feats"]["ret_30s"] <= p_r30 and s["feats"]["ret_60s"] <= p_r60]
                
    base_train_entries = apply_rule(train_snaps_base, p1_mms, p3_r30, p3_r60)
    base_test_entries = apply_rule(test_snaps_base, p1_mms, p3_r30, p3_r60)
    
    print(f"Base Test Entries: {len(base_test_entries)}")
    
    results = {}
    
    # A. raw_unconstrained
    res_raw = analyze_entries(base_test_entries, BASE_TP, BASE_SL, BASE_TO)
    results["raw_unconstrained"] = res_raw
    
    # B. equal_market_cap
    res_cap = {}
    for cap in [5, 10, 20]:
        capped_entries = []
        m_counts = defaultdict(int)
        for e in base_test_entries: # Assuming sorted by ts already due to extraction
            if m_counts[e["market"]] < cap:
                capped_entries.append(e)
                m_counts[e["market"]] += 1
        res_cap[f"cap_{cap}"] = analyze_entries(capped_entries, BASE_TP, BASE_SL, BASE_TO)
    results["equal_market_cap"] = res_cap
    
    # C. top1_market_removed
    top1_market = None
    if res_raw["trades"] > 0:
        sorted_m = sorted(res_raw["markets"].items(), key=lambda x: x[1]["trades"], reverse=True)
        top1_market = sorted_m[0][0] if sorted_m else None
        
    if top1_market:
        c_entries = [e for e in base_test_entries if e["market"] != top1_market]
        results["top1_market_removed"] = analyze_entries(c_entries, BASE_TP, BASE_SL, BASE_TO)
    else:
        results["top1_market_removed"] = res_raw
        
    # D. weak_market_removed
    train_res = analyze_entries(base_train_entries, BASE_TP, BASE_SL, BASE_TO)
    weak_markets = [m for m, stat in train_res["markets"].items() if stat["net"] < 0]
    d_entries = [e for e in base_test_entries if e["market"] not in weak_markets]
    results["weak_market_removed"] = analyze_entries(d_entries, BASE_TP, BASE_SL, BASE_TO)
    
    # 4. Walk-Forward Folds
    folds = [
        {"train": (0, 9), "test": (10, 14)},
        {"train": (2, 11), "test": (12, 16)},
        {"train": (4, 13), "test": (14, 19)}
    ]
    
    fold_results = []
    for f in folds:
        tr_snaps = [s for s in all_snaps if f["train"][0] <= s["band_idx"] <= f["train"][1]]
        te_snaps = [s for s in all_snaps if f["test"][0] <= s["band_idx"] <= f["test"][1]]
        
        mms_t = [s["feats"]["mms"] for s in tr_snaps]
        r30_t = [s["feats"]["ret_30s"] for s in tr_snaps]
        r60_t = [s["feats"]["ret_60s"] for s in tr_snaps]
        
        if not mms_t: continue
        
        p1 = np.percentile(mms_t, 1)
        p3_30 = np.percentile(r30_t, 3)
        p3_60 = np.percentile(r60_t, 3)
        
        te_entries = apply_rule(te_snaps, p1, p3_30, p3_60)
        f_res = analyze_entries(te_entries, BASE_TP, BASE_SL, BASE_TO)
        fold_results.append({
            "fold": f"{f['train'][0]}~{f['train'][1]} -> {f['test'][0]}~{f['test'][1]}",
            "net": f_res["net"],
            "trades": f_res["trades"]
        })
    results["walk_forward_folds"] = fold_results
    
    # Exit Sensitivities
    sens_res = {}
    for tp, sl, to in SENSITIVITIES:
        sens_res[f"TP_{tp}_SL_{sl}_TO_{to}"] = analyze_entries(base_test_entries, tp, sl, to)["net"]
    results["exit_sensitivities"] = sens_res
    
    # Judgement Logic
    raw_net = res_raw["net"]
    raw_pf = res_raw["pf"]
    raw_trades = res_raw["trades"]
    
    top1_share = 0.0
    if raw_trades > 0:
        sorted_m = sorted(res_raw["markets"].items(), key=lambda x: x[1]["trades"], reverse=True)
        top1_share = sorted_m[0][1]["trades"] / raw_trades
        
    viable_markets = sum(1 for m, st in res_raw["markets"].items() if st["net"] > 0)
    pos_folds = sum(1 for f in fold_results if f["net"] > 0)
    
    # Extract cap 10 net
    cap10_net = results["equal_market_cap"]["cap_10"]["net"]
    top1_rm_net = results["top1_market_removed"]["net"]
    
    if raw_net > 0.03 and raw_pf >= 1.3 and raw_trades >= 50 and viable_markets >= 3 and pos_folds >= 2 and top1_share < 0.4 and cap10_net > 0 and top1_rm_net > 0:
        judgement = "ROBUST_EDGE_CONFIRMED"
    elif raw_net > 0 and raw_pf >= 1.15 and raw_trades >= 30 and viable_markets >= 2 and pos_folds >= 2 and cap10_net > 0 and top1_rm_net > 0:
        judgement = "WEAK_EDGE_NEEDS_MORE_DATA"
    elif cap10_net <= 0 or top1_rm_net <= 0:
        judgement = "MARKET_BIAS_ONLY"
    elif pos_folds < 2:
        judgement = "FOLD_UNSTABLE"
    else:
        judgement = "OVERFIT_REJECTED"
        
    results["judgement"] = judgement
    
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        "  FORWARD LABEL CANDIDATE ROBUSTNESS RETEST",
        "  STATUS: NOT PRODUCTION READY",
        "  NOTE: NO CANDIDATE CREATED, NO CONFIG MODIFIED.",
        "  Robustness retest of mined forward-label candidate.",
        "  Market bias must be resolved before any candidate promotion.",
        "  Test/fold result is more important than raw result.",
        "=" * 72,
        f"Generated : {datetime.now().isoformat()}",
        f"Judgement : {judgement}",
        ""
    ]
    
    lines.append("[ 1. Raw Unconstrained ]")
    lines.append(f"  Test Trades : {res_raw['trades']}")
    lines.append(f"  Win Rate    : {res_raw['win_rate']:.2%}")
    lines.append(f"  Net 0.05%   : {res_raw['net']:.4f}%")
    lines.append(f"  PF          : {res_raw['pf']:.2f}")
    lines.append(f"  Top1 Share  : {top1_share:.2%}")
    lines.append(f"  Viable Mkts : {viable_markets}/10")
    lines.append("")
    
    lines.append("[ 2. Equal Market Cap ]")
    for cap in [5, 10, 20]:
        cr = res_cap[f"cap_{cap}"]
        lines.append(f"  Cap {cap:<3} : Trades {cr['trades']:<3} | Net {cr['net']:.4f}% | PF {cr['pf']:.2f}")
    lines.append("")
    
    lines.append("[ 3. Market Removed ]")
    t1r = results["top1_market_removed"]
    lines.append(f"  Top1 Removed: Trades {t1r['trades']:<3} | Net {t1r['net']:.4f}% | PF {t1r['pf']:.2f}")
    wmr = results["weak_market_removed"]
    lines.append(f"  Weak Removed: Trades {wmr['trades']:<3} | Net {wmr['net']:.4f}% | PF {wmr['pf']:.2f}")
    lines.append("")
    
    lines.append("[ 4. Walk-Forward Folds ]")
    for fr in fold_results:
        lines.append(f"  Fold {fr['fold']:<15} : Trades {fr['trades']:<3} | Net {fr['net']:.4f}%")
    lines.append("")
    
    lines.append("[ 5. Exit Sensitivities (Test Net) ]")
    for k, v in sens_res.items():
        lines.append(f"  {k:<18} : {v:.4f}%")
    lines.append("")
    
    lines.append("=" * 72)
    
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"\n[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")

if __name__ == "__main__":
    main()
