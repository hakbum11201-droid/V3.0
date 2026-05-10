import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_combined_filter_backtest(ws_path: str, market_factor_path: str, market_focus_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    """
    Market Factor + Market Focus + Short-Term Trend 3단계 결합 백테스트를 수행합니다.
    """
    print(f"[CombinedBT] Starting combined backtest. WS: {ws_path}")

    if not all(os.path.exists(p) for p in [ws_path, market_factor_path, market_focus_path, trend_candidate_path]):
        result = {"ok": False, "reason": "Required candidate files not found."}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # 1. Load Candidates
    with open(market_factor_path, 'r', encoding='utf-8') as f: factor_c = json.load(f)["market_factor_filter"]
    with open(market_focus_path, 'r', encoding='utf-8') as f: focus_c = json.load(f)["market_focus_filter"]
    with open(trend_candidate_path, 'r', encoding='utf-8') as f: trend_c = json.load(f)

    thresholds = trend_c.get("threshold_candidates", [75, 85, 95])
    windows = trend_c.get("holding_windows_sec", [300, 600])
    cost_floor = trend_c.get("cost_floor_pct", 0.20)
    weights = trend_c["weights"]

    # 2. Load Data
    market_data: Dict[str, Dict[str, Any]] = {}
    print("[CombinedBT] Loading and pre-calculating arrays...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try: event = json.loads(line)
                except: continue
                raw = event.get("raw", {})
                is_trade = (event.get("event_type") == "trade") or (raw.get("type") == "trade")
                is_ob = (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook")
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                if symbol not in market_data: market_data[symbol] = {"trades": [], "ob": None}
                if is_trade:
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    market_data[symbol]["trades"].append({
                        "ts": ts, "price": float(raw.get("trade_price") or event.get("trade_price")),
                        "vol": float(raw.get("trade_volume") or event.get("trade_volume")),
                        "side": raw.get("ask_bid")
                    })
                elif is_ob: market_data[symbol]["ob"] = raw
    except Exception as e:
        print(f"[CombinedBT] Load Error: {e}"); return

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

    # 3. Sampling and 3-Stage Filtering
    print("[CombinedBT] Processing 3-stage filters...")
    sampling_ts = np.arange(min_ts + 600, max_ts - 600, 1.0)
    all_symbols = sorted(list(market_data.keys()))
    
    samples_list = []
    
    for ts in sampling_ts:
        # Step 1: Calculate Factors for all markets
        market_factors = {}
        for s in all_symbols:
            arr = symbol_arrays.get(s)
            if not arr: continue
            f = calculate_factors_v3(market_data[s], arr, ts)
            if f: market_factors[s] = f
        
        if not market_factors: continue
        
        # Leadership for Dynamic Focus
        total_buy_val = sum(f["buy_trade_value_10s"] for f in market_factors.values())
        leader_symbol = max(market_factors.keys(), key=lambda x: market_factors[x]["buy_trade_value_10s"])
        leader_val = market_factors[leader_symbol]["buy_trade_value_10s"]
        rel_share = leader_val / total_buy_val if total_buy_val > 0 else 0
        
        for s, f in market_factors.items():
            # Stage 1: Market Factor Filter
            factor_pass = (
                f["volatility_300s"] >= factor_c["min_volatility_300s_pct"] and
                f["imbalance_300s"] >= factor_c["min_imbalance_300s"] and
                f["depth_ratio"] >= factor_c["min_bid_ask_depth_ratio_5"] and
                f["spread_pct"] <= factor_c["max_spread_pct"]
            )
            
            # Stage 2: Market Focus Filter
            focus_pass_dynamic = (
                s == leader_symbol and 
                f["buy_trade_value_10s"] >= focus_c["min_buy_trade_value_10s"] and
                rel_share >= focus_c["min_relative_volume_share"]
            )
            focus_pass_static = (s in focus_c["static_focus_markets"])
            
            # Stage 3: Trend Score
            score = calculate_trend_score_v3(f, weights)
            
            # Future Outcome
            arr = symbol_arrays[s]
            idx_s = np.searchsorted(arr["ts"], ts, side='right')
            outcome = {}
            for w in windows:
                idx_e = np.searchsorted(arr["ts"], ts + w, side='right')
                if idx_e > idx_s:
                    w_pr = arr["pr"][idx_s:idx_e]
                    outcome[str(w)] = {
                        "ret": (w_pr[-1] - f["price"]) / f["price"] * 100.0,
                        "mfe": (np.max(w_pr) - f["price"]) / f["price"] * 100.0
                    }
            
            if outcome:
                samples_list.append({
                    "symbol": s, "ts": ts, "score": score,
                    "factor_pass": factor_pass,
                    "focus_pass_dynamic": focus_pass_dynamic,
                    "focus_pass_static": focus_pass_static,
                    "outcome": outcome
                })

    # 4. Aggregate Results
    results = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(samples_list),
        "modes": {}
    }

    modes = ["ALL_MARKETS", "STATIC_SOL_ONLY", "DYNAMIC_LEADER"]
    
    for mode in modes:
        results["modes"][mode] = {}
        for th in thresholds:
            for w in windows:
                w_str = str(w)
                key = f"th{th}_w{w}"
                
                # Selection Logic
                def is_selected(s):
                    if s["score"] < th: return False
                    if mode == "ALL_MARKETS": return s["factor_pass"]
                    if mode == "STATIC_SOL_ONLY": return s["factor_pass"] and s["focus_pass_static"]
                    if mode == "DYNAMIC_LEADER": return s["factor_pass"] and s["focus_pass_dynamic"]
                    return False
                
                group = [s for s in samples_list if is_selected(s)]
                if not group: 
                    results["modes"][mode][key] = None
                    continue
                
                rets = np.array([s["outcome"][w_str]["ret"] for s in group if w_str in s["outcome"]])
                mfes = np.array([s["outcome"][w_str]["mfe"] for s in group if w_str in s["outcome"]])
                if len(rets) == 0:
                    results["modes"][mode][key] = None
                    continue

                results["modes"][mode][key] = {
                    "count": len(rets),
                    "avg_net_pnl": float(np.mean(rets - cost_floor)),
                    "median_net_pnl": float(np.median(rets - cost_floor)),
                    "win_rate": float(np.sum(rets > cost_floor) / len(rets) * 100),
                    "avg_mfe": float(np.mean(mfes)),
                    "mfe_020": int(np.sum(mfes >= 0.20))
                }

    # Final Output
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(to_json_ready_v3(results), f, indent=2)

    generate_summary_txt_v3(results, output_txt, thresholds, windows)
    print(f"[CombinedBT] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v3(data, arr, ts):
    idx_end = np.searchsorted(arr["ts"], ts, side='right')
    if idx_end == 0: return None
    price = arr["pr"][idx_end-1]
    idx_s300 = np.searchsorted(arr["ts"], ts - 300, side='left')
    idx_s10 = np.searchsorted(arr["ts"], ts - 10, side='left')
    if idx_end <= idx_s300: return None
    p300 = arr["pr"][idx_s300:idx_end]
    volat = np.std(p300) / np.mean(p300) * 100.0
    rel_t300 = data["trades"][idx_s300:idx_end]
    v_tot = sum(t["price"] * t["vol"] for t in rel_t300)
    v_buy = sum(t["price"] * t["vol"] for t in rel_t300 if t["side"] == 'ASK')
    imb300 = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
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
        "price": price, "volatility_300s": volat, "imbalance_300s": imb300, "imbalance_10s": imb300, # Approx
        "depth_ratio": depth, "spread_pct": spread, "price_chg_10s": p10, "buy_trade_value_10s": v_buy10
    }

def calculate_trend_score_v3(f, weights):
    def scale(v, min_v, max_v): return np.clip((v - min_v) / (max_v - min_v) * 100, 0, 100)
    scores = {
        "imbalance_10s_score": scale(f["imbalance_10s"], -0.5, 0.5),
        "price_chg_10s_score": scale(f["price_chg_10s"], -0.05, 0.05),
        "volume_10s_score": scale(f["buy_trade_value_10s"], 0, 10000000),
        "spread_score": scale(f["spread_pct"], 0.2, 0.02),
        "depth_score": scale(f["depth_ratio"], 0.5, 2.0),
        "absorption_score": 50, "continuation_score": 50, "sweep_score": 0
    }
    total = sum(scores[k] * weights.get(k, 0) for k in scores)
    w_sum = sum(weights.values())
    return total / w_sum if w_sum > 0 else 0

def to_json_ready_v3(obj):
    if isinstance(obj, dict): return {k: to_json_ready_v3(v) for k, v in obj.items()}
    elif isinstance(obj, list): return [to_json_ready_v3(v) for v in obj]
    elif isinstance(obj, (np.float64, np.float32)): return float(obj)
    elif isinstance(obj, (np.int64, np.int32)): return int(obj)
    elif isinstance(obj, (np.bool_, bool)): return bool(obj)
    return obj

def generate_summary_txt_v3(res, output_txt, thresholds, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("      Combined 3-Stage Filter Backtest Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"전체 샘플 수: {res['total_samples']}")
    lines.append("")

    for mode in ["ALL_MARKETS", "STATIC_SOL_ONLY", "DYNAMIC_LEADER"]:
        lines.append(f"--- [Mode: {mode}] ---")
        for th in thresholds:
            for w in windows:
                key = f"th{th}_w{w}"
                s = res["modes"][mode].get(key)
                if s:
                    lines.append(f"  [{key}] Count: {s['count']:4} | Net PnL: {s['avg_net_pnl']:7.4f}% | Win: {s['win_rate']:5.2f}% | 0.2% Hits: {s['mfe_020']}")
        lines.append("")

    lines.append("--- 진단 결론 ---")
    best_mode = None; best_pnl = -999; best_key = None
    for mode, data in res["modes"].items():
        for key, s in data.items():
            if s and s["avg_net_pnl"] > best_pnl:
                best_pnl = s["avg_net_pnl"]; best_mode = mode; best_key = key

    if best_mode:
        lines.append(f"1. 가장 우수한 성과 조합: {best_mode} / {best_key} (Net PnL: {best_pnl:.4f}%)")
        if best_pnl > 0:
            lines.append("2. 판단: 3단계 필터 결합 시 Net PnL이 양수로 전환되었습니다. Paper 실험 권장.")
        elif best_pnl > -0.10:
            lines.append("2. 판단: 손실폭이 대폭 감소했으나 여전히 비용 장벽이 높습니다. 추가 가중치 최적화 필요.")
        else:
            lines.append("2. 판단: 필터 효과는 있으나 여전히 수익성이 낮습니다.")
    
    lines.append("3. 주의사항: 본 결과는 3시간 샘플에 국한됩니다. 자동 config 반영 금지.")
    with open(output_txt, 'w', encoding='utf-8') as f: f.write("\n".join(lines))
