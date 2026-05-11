import json
import os
import numpy as np
import itertools
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_short_term_trend_weight_optimizer(ws_path: str, candidate_path: str, output_json: str, output_txt: str):
    """
    Short-Term Trend 가중치 및 임계값 조합을 탐색하여 최적의 설정을 찾습니다.
    """
    print(f"[TrendOpt] Starting optimization. WS: {ws_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"WS log not found: {ws_path}"}
        report_io.write_json_report(output_json, result)
        return

    # 1. Load Data and Calculate Features
    market_data: Dict[str, Dict[str, Any]] = {}
    samples_list: List[Dict[str, Any]] = []

    print("[TrendOpt] Loading logs and calculating features...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try: event = json.loads(line)
                except: continue
                raw = event.get("raw", {})
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                if symbol not in market_data:
                    market_data[symbol] = {"trades": [], "ob": None, "last_sample_ts": 0}

                if (event.get("event_type") == "trade") or (raw.get("type") == "trade"):
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    market_data[symbol]["trades"].append({"ts": ts, "price": float(raw.get("trade_price") or event.get("trade_price")), "vol": float(raw.get("trade_volume") or event.get("trade_volume")), "side": raw.get("ask_bid")})
                elif (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook"):
                    market_data[symbol]["ob"] = raw

                current_ts = event.get("received_at")
                if current_ts - market_data[symbol]["last_sample_ts"] >= 1.0:
                    if market_data[symbol]["ob"] and market_data[symbol]["trades"]:
                        sample = calculate_features(market_data[symbol], current_ts)
                        if sample:
                            sample["symbol"] = symbol
                            samples_list.append(sample)
                            market_data[symbol]["last_sample_ts"] = current_ts
    except Exception as e:
        print(f"[TrendOpt] Error loading: {e}"); return

    if not samples_list: return

    # 2. Future Results
    windows = [300, 600]
    for symbol, data in market_data.items():
        ts_arr = np.array([t["ts"] for t in data["trades"]])
        pr_arr = np.array([t["price"] for t in data["trades"]])
        for s in [sm for sm in samples_list if sm["symbol"] == symbol]:
            s["outcomes"] = {}
            for w in windows:
                idx_s = np.searchsorted(ts_arr, s["ts"], side='right')
                idx_e = np.searchsorted(ts_arr, s["ts"] + w, side='right')
                if idx_e > idx_s:
                    w_pr = pr_arr[idx_s:idx_e]
                    s["outcomes"][str(w)] = {"mfe": (np.max(w_pr) - s["price"]) / s["price"] * 100.0, "ret": (w_pr[-1] - s["price"]) / s["price"] * 100.0}
                else: s["outcomes"][str(w)] = {"mfe": 0, "ret": 0}

    # 3. Vectorized Scoring
    def scale(v, min_v, max_v): return np.clip((v - min_v) / (max_v - min_v) * 100, 0, 100)
    score_matrix = np.array([[scale(s["imbalance_10s"], -0.5, 0.5), scale(s["price_chg_10s"], -0.05, 0.05), scale(s["buy_trade_value_10s"], 0, 10000000), scale(s["spread_pct"], 0.2, 0.02), scale(s["depth_ratio"], 0.5, 2.0), 50, 50, 0] for s in samples_list])
    ret_matrices = {str(w): np.array([s["outcomes"][str(w)]["ret"] for s in samples_list]) for w in windows}
    mfe_matrices = {str(w): np.array([s["outcomes"][str(w)]["mfe"] for s in samples_list]) for w in windows}

    # 4. Grid Search
    w_ranges = [[25, 40], [20, 35], [10, 25], [10, 20], [5, 15], [5, 15], [15, 30], [0, 5]]
    thresholds = [75, 85, 95]
    all_w = list(itertools.product(*w_ranges))
    w_arr = np.array(all_w); s_w = np.sum(w_arr, axis=1)
    total_scores = (score_matrix @ w_arr.T) / s_w
    
    top_results = []
    for c_idx in range(len(all_w)):
        sc = total_scores[:, c_idx]
        for th in thresholds:
            mask = sc >= th
            if np.sum(mask) < 20: continue
            for w in windows:
                w_str = str(w)
                rets = ret_matrices[w_str][mask]; mfes = mfe_matrices[w_str][mask]
                avg_net = np.mean(rets - 0.20); p020 = np.sum(mfes >= 0.20)
                top_results.append({
                    "weights": dict(zip(["imbalance_10s_score", "price_chg_10s_score", "volume_10s_score", "spread_score", "depth_score", "absorption_score", "continuation_score", "sweep_score"], all_w[c_idx])),
                    "threshold": th, "window": w, "count": int(np.sum(mask)), "avg_net_pnl": float(avg_net), "win_rate": float(np.sum(rets > 0.20)/len(rets)*100), "mfe_020_pass_rate": float(p020/len(rets)*100), "balanced_score": float(avg_net + (p020/len(rets)*0.5))
                })

    top_results.sort(key=lambda x: x["balanced_score"], reverse=True)
    final = {"ok": True, "timestamp": datetime.now().isoformat(), "total_combinations_explored": len(all_w) * len(thresholds) * len(windows), "top_combinations": top_results[:20]}
    report_io.write_json_report(output_json, final)
    generate_summary_txt(final, output_txt)
    print(f"[TrendOpt] Done. Reports: {output_json}, {output_txt}")

def calculate_features(data, ts):
    trades = data["trades"]; ob = data["ob"]
    if not ob or not trades: return None
    curr_p = trades[-1]["price"]
    cutoff = ts - 10.0; b10, s10 = 0.0, 0.0
    for i in range(len(trades)-1, -1, -1):
        t = trades[i]
        if t["ts"] < cutoff: break
        if t["side"] == 'ASK': b10 += t["price"] * t["vol"]
        else: s10 += t["price"] * t["vol"]
    units = ob.get("orderbook_units", [])
    if not units: return None
    spread = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
    depth = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0
    past_p = trades[0]["price"]
    for i in range(len(trades)-1, -1, -1):
        if trades[i]["ts"] <= cutoff: past_p = trades[i]["price"]; break
    return {"ts": ts, "price": curr_p, "buy_trade_value_10s": b10, "sell_trade_value_10s": s10, "imbalance_10s": (b10-s10)/(b10+s10) if (b10+s10)>0 else 0, "spread_pct": spread, "depth_ratio": depth, "price_chg_10s": (curr_p-past_p)/past_p*100}

def generate_summary_txt(res, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("       Short-Term Trend Weight Optimizer Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"총 탐색 조합 수: {res['total_combinations_explored']}\n")
    top = res["top_combinations"]
    if not top: lines.append("유효한 조합을 찾지 못했습니다.")
    else:
        for i, r in enumerate(top[:5]):
            lines.append(f"Rank {i+1}: Score({r['balanced_score']:.4f}) | Net PnL: {r['avg_net_pnl']:.4f}% | Win: {r['win_rate']:.2f}%")
            lines.append(f"  - Threshold: {r['threshold']}, Window: {r['window']}s, Count: {r['count']}")
            lines.append(f"  - Weights: {r['weights']}\n")
    lines.append("--- 진단 결론 ---")
    lines.append("1. 성과 개선 여부: " + ("예" if any(r['avg_net_pnl'] > 0 for r in top) else "아니오"))
    report_io.write_text_report(output_txt, "\n".join(lines))
