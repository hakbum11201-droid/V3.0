import json
import os
import numpy as np
import itertools
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_short_term_trend_weight_optimizer(ws_path: str, candidate_path: str, output_json: str, output_txt: str):
    """
    Short-Term Trend 가중치 및 임계값 조합을 탐색하여 최적의 설정을 찾습니다.
    """
    print(f"[TrendOpt] Starting optimization. WS: {ws_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"WS log not found: {ws_path}"}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # 1. Load Data and Calculate Features (Sampling 1s)
    market_data: Dict[str, Dict[str, Any]] = {}
    samples_list: List[Dict[str, Any]] = []

    print("[TrendOpt] Loading logs and calculating features...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    event = json.loads(line)
                except Exception: continue
                
                raw = event.get("raw", {})
                is_trade = (event.get("event_type") == "trade") or (raw.get("type") == "trade")
                is_ob = (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook")
                
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                
                if symbol not in market_data:
                    market_data[symbol] = {"trades": [], "ob": None, "last_sample_ts": 0}

                if is_trade:
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    price = float(raw.get("trade_price") or event.get("trade_price"))
                    vol = float(raw.get("trade_volume") or event.get("trade_volume"))
                    side = raw.get("ask_bid")
                    market_data[symbol]["trades"].append({"ts": ts, "price": price, "vol": vol, "side": side})
                elif is_ob:
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
        print(f"[TrendOpt] Error loading: {e}")
        return

    if not samples_list:
        print("[TrendOpt] No valid samples found.")
        return

    # 2. Calculate Future Results for each sample
    print("[TrendOpt] Calculating future outcomes for each sample...")
    windows = [300, 600]
    for symbol, data in market_data.items():
        all_trades = data["trades"]
        ts_arr = np.array([t["ts"] for t in all_trades])
        pr_arr = np.array([t["price"] for t in all_trades])
        
        symbol_samples = [s for s in samples_list if s["symbol"] == symbol]
        for s in symbol_samples:
            s["outcomes"] = {}
            for w in windows:
                idx_s = np.searchsorted(ts_arr, s["ts"], side='right')
                idx_e = np.searchsorted(ts_arr, s["ts"] + w, side='right')
                if idx_e > idx_s:
                    w_prices = pr_arr[idx_s:idx_e]
                    max_p = np.max(w_prices)
                    final_p = w_prices[-1]
                    s["outcomes"][str(w)] = {
                        "mfe": (max_p - s["price"]) / s["price"] * 100.0,
                        "ret": (final_p - s["price"]) / s["price"] * 100.0
                    }
                else:
                    s["outcomes"][str(w)] = {"mfe": 0, "ret": 0}

    # 3. Vectorize Sub-scores
    print("[TrendOpt] Vectorizing scores for grid search...")
    # Define sub-score mapping
    def scale(val, min_v, max_v): return np.clip((val - min_v) / (max_v - min_v) * 100, 0, 100)
    
    score_matrix = [] # (N_samples, 8_metrics)
    for s in samples_list:
        score_matrix.append([
            scale(s["imbalance_10s"], -0.5, 0.5),
            scale(s["price_chg_10s"], -0.05, 0.05),
            scale(s["buy_trade_value_10s"], 0, 10000000),
            scale(s["spread_pct"], 0.2, 0.02),
            scale(s["depth_ratio"], 0.5, 2.0),
            50, # absorption placeholder
            50, # continuation placeholder
            0   # sweep placeholder
        ])
    score_matrix = np.array(score_matrix)

    # Pre-calculate outcomes matrix for each window
    ret_matrices = {str(w): np.array([s["outcomes"][str(w)]["ret"] for s in samples_list]) for w in windows}
    mfe_matrices = {str(w): np.array([s["outcomes"][str(w)]["mfe"] for s in samples_list]) for w in windows}

    # 4. Grid Search
    weight_ranges = [
        [25, 30, 35, 40], # imbalance
        [20, 25, 30, 35], # price_chg
        [10, 15, 20, 25], # volume
        [10, 15, 20],      # spread
        [5, 10, 15],       # depth
        [5, 10, 15],       # absorption
        [15, 20, 25, 30], # continuation
        [0, 5]             # sweep
    ]
    thresholds = [75, 85, 95, 105]
    cost_floor = 0.20 # Default

    all_weight_combinations = list(itertools.product(*weight_ranges))
    print(f"[TrendOpt] Total weight combinations: {len(all_weight_combinations)}")
    
    top_results = []

    # Iterate through weight combinations
    # Since 110k * 30k samples is too much for pure python loop, we use matrix multiplication
    # BUT we only have ~20k-30k samples. Matrix mult is okay.
    
    # Actually, let's sample the weight combinations if they are too many, or just run them.
    # 13,824 combinations * 8 metrics dot product is fast in numpy.
    
    weights_arr = np.array(all_weight_combinations) # (C, 8)
    sum_weights = np.sum(weights_arr, axis=1) # (C,)
    
    # Total scores matrix (N_samples, C_combinations)
    # total_scores = (score_matrix @ weights_arr.T) / sum_weights
    # To avoid memory error (30000 * 13824 is 414M floats ~ 3.3GB), we process in chunks if needed.
    
    total_scores = (score_matrix @ weights_arr.T) / sum_weights
    
    print("[TrendOpt] Evaluating combinations across thresholds and windows...")
    for c_idx in range(len(all_weight_combinations)):
        scores = total_scores[:, c_idx]
        w_comb = all_weight_combinations[c_idx]
        
        for th in thresholds:
            mask = scores >= th
            count = np.sum(mask)
            if count < 20: continue # Skip if too few trades
            
            for w in windows:
                w_str = str(w)
                rets = ret_matrices[w_str][mask]
                mfes = mfe_matrices[w_str][mask]
                
                net_rets = rets - cost_floor
                avg_net = np.mean(net_rets)
                pass_020 = np.sum(mfes >= 0.20)
                
                # Simple balanced score: avg_net + (pass_rate * constant)
                balanced = avg_net + (pass_020 / count * 0.5)
                
                top_results.append({
                    "weights": {
                        "imbalance_10s_score": w_comb[0],
                        "price_chg_10s_score": w_comb[1],
                        "volume_10s_score": w_comb[2],
                        "spread_score": w_comb[3],
                        "depth_score": w_comb[4],
                        "absorption_score": w_comb[5],
                        "continuation_score": w_comb[6],
                        "sweep_score": w_comb[7]
                    },
                    "threshold": th,
                    "window": w,
                    "count": int(count),
                    "avg_net_pnl": float(avg_net),
                    "win_rate": float(np.sum(net_rets > 0) / count * 100),
                    "mfe_020_pass_rate": float(pass_020 / count * 100),
                    "balanced_score": float(balanced)
                })

        if c_idx % 2000 == 0:
            print(f"[TrendOpt] Processed {c_idx}/{len(all_weight_combinations)} combinations...")

    # Sort and filter
    top_results.sort(key=lambda x: x["balanced_score"], reverse=True)
    top_20 = top_results[:20]

    # Output
    final = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "total_combinations_explored": len(all_weight_combinations) * len(thresholds) * len(windows),
        "top_combinations": top_20
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(final, f, indent=2)

    generate_summary_txt(final, output_txt)
    print(f"[TrendOpt] Optimization complete. Reports: {output_json}, {output_txt}")

def calculate_features(data: Dict[str, Any], ts: float) -> Optional[Dict[str, Any]]:
    trades = data["trades"]
    ob = data["ob"]
    if not ob or not trades: return None
    current_price = trades[-1]["price"]
    
    # 10s Window Metrics
    cutoff_10 = ts - 10.0
    b10, s10 = 0.0, 0.0
    vols = []
    for i in range(len(trades)-1, -1, -1):
        t = trades[i]
        if t["ts"] < cutoff_10: break
        if t["side"] == 'ASK': b10 += t["price"] * t["vol"]
        else: s10 += t["price"] * t["vol"]
        vols.append(t["vol"])
    
    imbal_10 = (b10 - s10) / (b10 + s10) if (b10 + s10) > 0 else 0
    
    # Orderbook
    units = ob.get("orderbook_units", [])
    if not units: return None
    spread_pct = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
    depth_ratio = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0
    
    # Price Change
    past_p10 = trades[0]["price"]
    for i in range(len(trades)-1, -1, -1):
        if trades[i]["ts"] <= cutoff_10:
            past_p10 = trades[i]["price"]
            break
    price_chg_10 = (current_price - past_p10) / past_p10 * 100.0
    
    return {
        "ts": ts, "price": current_price,
        "buy_trade_value_10s": b10, "sell_trade_value_10s": s10, "imbalance_10s": imbal_10,
        "spread_pct": spread_pct, "depth_ratio": depth_ratio, "price_chg_10s": price_chg_10
    }

def generate_summary_txt(results, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("       Short-Term Trend Weight Optimizer Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {results['timestamp']}")
    lines.append(f"총 탐색 조합 수: {results['total_combinations_explored']}")
    lines.append("")
    lines.append("※ 이 도구는 설정값을 자동으로 적용하지 않습니다.")
    lines.append("※ 결과가 양수일지라도 장시간의 Paper Trading 검증이 필수입니다.")
    lines.append("")

    top = results["top_combinations"]
    if not top:
        lines.append("유효한 조합을 찾지 못했습니다. (진입 후보 부족)")
    else:
        lines.append("--- [Top 5 최적 가중치 조합] ---")
        for i, res in enumerate(top[:5]):
            lines.append(f"Rank {i+1}: Score({res['balanced_score']:.4f})")
            lines.append(f"  - Threshold: {res['threshold']}, Window: {res['window']}s")
            lines.append(f"  - Count: {res['count']}회, Avg Net PnL: {res['avg_net_pnl']:.4f}%")
            lines.append(f"  - 0.20% MFE Pass Rate: {res['mfe_020_pass_rate']:.2f}%")
            w = res["weights"]
            lines.append(f"  - Weights: Imb({w['imbalance_10s_score']}), Pchg({w['price_chg_10s_score']}), Vol({w['volume_10s_score']}), Cont({w['continuation_score']})")
            lines.append("")

    lines.append("--- 진단 결론 ---")
    has_positive = any(r["avg_net_pnl"] > 0 for r in top)
    if has_positive:
        lines.append("1. 성과 개선 여부: 예 (Net PnL 양수 조합 발견)")
        lines.append("2. 판단: 최적화된 가중치를 사용하면 단기추세 전략의 수익성 확보 가능성이 있음.")
    else:
        lines.append("1. 성과 개선 여부: 아니오 (전체 조합 Net PnL 음수 유지)")
        lines.append("2. 판단: 전략 반영 금지. 주문흐름 외에 마켓 팩터(변동성, 시장 단계) 추가 고려 필요.")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
