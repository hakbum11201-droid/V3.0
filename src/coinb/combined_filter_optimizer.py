import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
import itertools
from . import report_io

def run_combined_filter_optimizer(ws_path: str, market_factor_path: str, market_focus_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    """
    3단계 필터의 모든 파라미터 조합을 탐색하여 최적의 설정을 찾습니다.
    """
    print(f"[Optimizer] Starting grid search. WS: {ws_path}")

    if not all(os.path.exists(p) for p in [ws_path, market_factor_path, market_focus_path, trend_candidate_path]):
        result = {"ok": False, "reason": "Candidate files not found."}
        report_io.write_json_report(output_json, result)
        return

    # 1. Load Constants
    with open(trend_candidate_path, 'r', encoding='utf-8') as f: trend_c = json.load(f)
    weights = trend_c["weights"]
    cost_floor = trend_c.get("cost_floor_pct", 0.20)

    # 2. Search Space
    space = {
        "mode": ["ALL_MARKETS", "STATIC_SOL_ONLY", "DYNAMIC_LEADER"],
        "min_volatility_300s_pct": [0.04, 0.05, 0.06, 0.08],
        "min_imbalance_300s": [0.05, 0.10, 0.15, 0.20],
        "min_bid_ask_depth_ratio_5": [1.2, 1.5, 2.0],
        "max_spread_pct": [0.08, 0.10, 0.12],
        "min_buy_trade_value_10s": [500000, 1000000, 1500000, 2000000],
        "min_relative_volume_share": [0.2, 0.3, 0.4],
        "threshold": [75, 85, 95, 105],
        "window": [300, 600]
    }

    # 3. Data Processing
    market_data: Dict[str, Dict[str, Any]] = {}
    print("[Optimizer] Loading data...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try: event = json.loads(line)
                except: continue
                raw = event.get("raw", {})
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                if symbol not in market_data: market_data[symbol] = {"trades": [], "ob": None}
                if (event.get("event_type") == "trade") or (raw.get("type") == "trade"):
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    market_data[symbol]["trades"].append({
                        "ts": ts, "price": float(raw.get("trade_price") or event.get("trade_price")),
                        "vol": float(raw.get("trade_volume") or event.get("trade_volume")),
                        "side": raw.get("ask_bid")
                    })
                elif (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook"):
                    market_data[symbol]["ob"] = raw
    except Exception as e:
        print(f"[Optimizer] Load Error: {e}"); return

    symbol_arrays = {}
    all_ts = []
    for s in market_data:
        if market_data[s]["trades"]:
            ts_arr = np.array([t["ts"] for t in market_data[s]["trades"]])
            pr_arr = np.array([t["price"] for t in market_data[s]["trades"]])
            symbol_arrays[s] = {"ts": ts_arr, "pr": pr_arr}
            all_ts.append(ts_arr[0]); all_ts.append(ts_arr[-1])
    
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    sampling_ts = np.arange(min_ts + 600, max_ts - 600, 1.0)
    all_symbols = sorted(list(market_data.keys()))

    # 4. Pre-calculate Metrics
    print(f"[Optimizer] Pre-calculating metrics for {len(sampling_ts)} points...")
    metrics = {s: {
        "vol": [], "imb": [], "depth": [], "spread": [], "buy_val": [], "score": [],
        "ret300": [], "ret600": [], "mfe300": [], "mfe600": []
    } for s in all_symbols}

    for ts in sampling_ts:
        total_buy_all = 0
        point_vals = {}
        for s in all_symbols:
            arr = symbol_arrays.get(s)
            if not arr: continue
            f = calculate_factors_v4(market_data[s], arr, ts)
            if f:
                point_vals[s] = f
                total_buy_all += f["buy_trade_value_10s"]
        
        for s in all_symbols:
            f = point_vals.get(s)
            if not f:
                for k in metrics[s]: 
                    if k != "total_buy_all": metrics[s][k].append(np.nan)
                continue
            
            score = calculate_trend_score_v4(f, weights)
            arr = symbol_arrays[s]
            idx_s = np.searchsorted(arr["ts"], ts, side='right')
            
            def get_res(w):
                idx_e = np.searchsorted(arr["ts"], ts + w, side='right')
                if idx_e > idx_s:
                    w_pr = arr["pr"][idx_s:idx_e]
                    return (w_pr[-1] - f["price"]) / f["price"] * 100, (np.max(w_pr) - f["price"]) / f["price"] * 100
                return np.nan, np.nan

            r3, m3 = get_res(300); r6, m6 = get_res(600)
            
            metrics[s]["vol"].append(f["volatility_300s"])
            metrics[s]["imb"].append(f["imbalance_300s"])
            metrics[s]["depth"].append(f["depth_ratio"])
            metrics[s]["spread"].append(f["spread_pct"])
            metrics[s]["buy_val"].append(f["buy_trade_value_10s"])
            metrics[s]["score"].append(score)
            metrics[s]["ret300"].append(r3); metrics[s]["mfe300"].append(m3)
            metrics[s]["ret600"].append(r6); metrics[s]["mfe600"].append(m6)

    # Convert to Numpy
    for s in all_symbols:
        for k in metrics[s]: metrics[s][k] = np.array(metrics[s][k])

    # 5. Grid Search
    keys = list(space.keys())
    combinations = list(itertools.product(*[space[k] for k in keys]))
    print(f"[Optimizer] Searching {len(combinations)} combinations...")
    
    results_list = []
    for i, combo in enumerate(combinations):
        c = dict(zip(keys, combo))
        mode, v_th, i_th, d_th, s_th, b_th, r_th, th, win = combo
        
        all_rets, all_mfes = [], []
        for s in all_symbols:
            m = metrics[s]
            mask = (m["vol"] >= v_th) & (m["imb"] >= i_th) & (m["depth"] >= d_th) & (m["spread"] <= s_th)
            mask &= (m["score"] >= th)
            
            if mode == "STATIC_SOL_ONLY" and s != "KRW-SOL": mask[:] = False
            
            ret_k = f"ret{win}"; mfe_k = f"mfe{win}"
            final_mask = mask & (~np.isnan(m[ret_k]))
            if np.any(final_mask):
                all_rets.extend(m[ret_k][final_mask])
                all_mfes.extend(m[mfe_k][final_mask])

        if not all_rets: continue
        all_rets = np.array(all_rets); all_mfes = np.array(all_mfes)
        net_rets = all_rets - cost_floor
        avg_net = np.mean(net_rets)
        wr = np.sum(all_rets > cost_floor) / len(all_rets) * 100
        
        if avg_net > -0.20:
            results_list.append({
                "combo": c, "count": len(all_rets), "avg_net": float(avg_net), "win_rate": float(wr),
                "mfe020_rate": float(np.sum(all_mfes >= 0.20) / len(all_mfes) * 100)
            })

    # Sort and Report
    results_list.sort(key=lambda x: x["avg_net"], reverse=True)
    top_20 = results_list[:20]
    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_combinations": len(combinations),
        "positive_count": sum(1 for r in results_list if r["avg_net"] > 0),
        "top_20": top_20
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[Optimizer] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v4(data, arr, ts):
    idx_end = np.searchsorted(arr["ts"], ts, side='right')
    if idx_end == 0: return None
    price = arr["pr"][idx_end-1]
    idx_s300 = np.searchsorted(arr["ts"], ts - 300, side='left')
    if idx_end <= idx_s300: return None
    p300 = arr["pr"][idx_s300:idx_end]
    volat = np.std(p300) / np.mean(p300) * 100.0
    rel_t300 = data["trades"][idx_s300:idx_end]
    v_tot = sum(t["price"] * t["vol"] for t in rel_t300)
    v_buy = sum(t["price"] * t["vol"] for t in rel_t300 if t["side"] == 'ASK')
    imb300 = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
    idx_s10 = np.searchsorted(arr["ts"], ts - 10, side='left')
    rel_t10 = data["trades"][idx_s10:idx_end]
    v_buy10 = sum(t["price"] * t["vol"] for t in rel_t10 if t["side"] == 'ASK')
    p10 = (price - arr["pr"][idx_s10]) / arr["pr"][idx_s10] * 100.0 if idx_end > idx_s10 else 0
    spread = 0.1; depth = 1.0
    if data["ob"]:
        units = data["ob"].get("orderbook_units", []) or data["ob"].get("raw", {}).get("orderbook_units", [])
        if units:
            spread = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
            depth = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0
    return {
        "price": price, "volatility_300s": volat, "imbalance_300s": imb300, "imbalance_10s": imb300,
        "depth_ratio": depth, "spread_pct": spread, "price_chg_10s": p10, "buy_trade_value_10s": v_buy10
    }

def calculate_trend_score_v4(f, weights):
    def scale(v, min_v, max_v): return np.clip((v - min_v) / (max_v - min_v) * 100, 0, 100)
    scores = {
        "imbalance_10s_score": scale(f["imbalance_10s"], -0.5, 0.5),
        "price_chg_10s_score": scale(f["price_chg_10s"], -0.05, 0.05),
        "volume_10s_score": scale(f["buy_trade_value_10s"], 0, 10000000),
        "spread_score": scale(f["spread_pct"], 0.2, 0.02),
        "depth_score": scale(f["depth_ratio"], 0.5, 2.0),
        "absorption_score": 50, "continuation_score": 50, "sweep_score": 0
    }
    return sum(scores[k] * weights.get(k, 0) for k in scores) / sum(weights.values())

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Combined Filter Grid Search Optimizer (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append(f"전체 탐색 조합: {out['total_combinations']}")
    lines.append(f"Net PnL 양수 조합 수: {out['positive_count']}")
    lines.append("")
    if out["top_20"]:
        lines.append("--- [Top 5 Best Combinations] ---")
        for i, r in enumerate(out["top_20"][:5]):
            lines.append(f"{i+1}. Net PnL: {r['avg_net']:.4f}% | WR: {r['win_rate']:.2f}% | Count: {r['count']}")
            lines.append(f"   Config: {r['combo']}")
    else:
        lines.append("양수 수익을 기록한 조합이 없습니다.")
    lines.append("\n※ 자동 config 반영 금지. 실거래 반영 금지.")
    report_io.write_text_report(output_txt, "\n".join(lines))
