import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_short_term_trend_backtest(ws_path: str, candidate_path: str, output_json: str, output_txt: str):
    """
    Short-Term Trend v1 후보 설정을 기반으로 3시간 로그 백테스트를 수행합니다.
    """
    print(f"[TrendBT] Starting backtest. WS: {ws_path}, Candidate: {candidate_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"WS log not found: {ws_path}"}
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return

    if not os.path.exists(candidate_path):
        result = {"ok": False, "reason": f"Candidate file not found: {candidate_path}"}
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return

    # 1. Load Candidate
    with open(candidate_path, 'r', encoding='utf-8') as f:
        candidate = json.load(f)

    weights = candidate.get("weights", {})
    thresholds = candidate.get("threshold_candidates", [75, 85, 95])
    windows = candidate.get("holding_windows_sec", [300, 600])
    cost_floor = candidate.get("cost_floor_pct", 0.20)

    # 2. Process WS Log
    market_data: Dict[str, Dict[str, Any]] = {}
    samples: Dict[str, List[Dict[str, Any]]] = {}

    print("[TrendBT] Processing events and calculating scores...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line_idx, line in enumerate(f):
                if not line.strip(): continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                
                raw = event.get("raw", {})
                is_trade = (event.get("event_type") == "trade") or (raw.get("type") == "trade")
                is_ob = (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook")
                
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                
                if symbol not in market_data:
                    market_data[symbol] = {"trades": [], "ob": None, "last_sample_ts": 0}
                    samples[symbol] = []

                if is_trade:
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    price = float(raw.get("trade_price") or event.get("trade_price"))
                    vol = float(raw.get("trade_volume") or event.get("trade_volume"))
                    side = raw.get("ask_bid")
                    market_data[symbol]["trades"].append({"ts": ts, "price": price, "vol": vol, "side": side})
                elif is_ob:
                    market_data[symbol]["ob"] = raw

                # Sampling
                current_ts = event.get("received_at")
                if current_ts - market_data[symbol]["last_sample_ts"] >= 1.0:
                    if market_data[symbol]["ob"] and market_data[symbol]["trades"]:
                        sample = calculate_features(market_data[symbol], current_ts)
                        if sample:
                            score = calculate_trend_score(sample, weights)
                            sample["trend_score"] = score
                            samples[symbol].append(sample)
                            market_data[symbol]["last_sample_ts"] = current_ts
    except Exception as e:
        print(f"[TrendBT] Error: {e}")
        return

    # 3. Simulate Results
    print("[TrendBT] Simulating returns for candidates...")
    results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "candidate": candidate["name"],
        "cost_floor": cost_floor,
        "by_threshold_window": {},
        "by_market": {}
    }

    for th in thresholds:
        for window in windows:
            key = f"th{th}_w{window}"
            trade_stats = {
                "count": 0, "gross_return_avg": 0, "net_return_avg": 0,
                "win_rate": 0, "mfe_avg": 0, "mae_avg": 0,
                "mfe_p50": 0, "mfe_p75": 0, "mfe_p90": 0, "mfe_max": 0,
                "ge_020": 0, "ge_025": 0, "ge_030": 0
            }
            returns = []
            mfes = []
            maes = []
            
            for symbol, s_list in samples.items():
                trades = market_data[symbol]["trades"]
                trade_ts = np.array([t["ts"] for t in trades])
                trade_prices = np.array([t["price"] for t in trades])
                
                for s in s_list:
                    if s["trend_score"] >= th:
                        # Entry
                        start_ts = s["ts"]
                        start_price = s["price"]
                        end_ts = start_ts + window
                        
                        idx_s = np.searchsorted(trade_ts, start_ts, side='right')
                        idx_e = np.searchsorted(trade_ts, end_ts, side='right')
                        
                        if idx_e > idx_s:
                            w_prices = trade_prices[idx_s:idx_e]
                            max_p = np.max(w_prices)
                            min_p = np.min(w_prices)
                            final_p = w_prices[-1]
                            
                            gross_ret = (final_p - start_price) / start_price * 100.0
                            mfe = (max_p - start_price) / start_price * 100.0
                            mae = (min_p - start_price) / start_price * 100.0
                            
                            returns.append(gross_ret)
                            mfes.append(mfe)
                            maes.append(mae)
                            trade_stats["count"] += 1
                            if mfe >= 0.20: trade_stats["ge_020"] += 1
                            if mfe >= 0.25: trade_stats["ge_025"] += 1
                            if mfe >= 0.30: trade_stats["ge_030"] += 1

            if trade_stats["count"] > 0:
                ret_arr = np.array(returns)
                mfe_arr = np.array(mfes)
                mae_arr = np.array(maes)
                
                trade_stats["gross_return_avg"] = float(np.mean(ret_arr))
                trade_stats["net_return_avg"] = float(np.mean(ret_arr - cost_floor))
                trade_stats["win_rate"] = float(np.sum(ret_arr > cost_floor) / len(ret_arr) * 100.0)
                trade_stats["mfe_avg"] = float(np.mean(mfe_arr))
                trade_stats["mae_avg"] = float(np.mean(mae_arr))
                trade_stats["mfe_p50"] = float(np.percentile(mfe_arr, 50))
                trade_stats["mfe_p75"] = float(np.percentile(mfe_arr, 75))
                trade_stats["mfe_p90"] = float(np.percentile(mfe_arr, 90))
                trade_stats["mfe_max"] = float(np.max(mfe_arr))
                trade_stats["mae_max"] = float(np.min(mae_arr))
            
            results["by_threshold_window"][key] = trade_stats

    # Write JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    generate_summary_txt(results, output_txt, thresholds, windows)
    print(f"[TrendBT] Done. Reports: {output_json}, {output_txt}")

def calculate_trend_score(s: Dict[str, Any], weights: Dict[str, float]) -> float:
    # 0-100 scaling for each metric
    def scale(val, min_val, max_val):
        if max_val == min_val: return 0
        return np.clip((val - min_val) / (max_val - min_val) * 100, 0, 100)

    # Simplified Score Mapping
    scores = {
        "imbalance_10s_score": scale(s["imbalance_10s"], -0.5, 0.5),
        "price_chg_10s_score": scale(s["price_chg_10s"], -0.05, 0.05),
        "volume_10s_score": scale(s["buy_trade_value_10s"], 0, 10000000), # 10M KRW
        "spread_score": scale(s["spread_pct"], 0.2, 0.02), # Reverse
        "depth_score": scale(s["depth_ratio"], 0.5, 2.0),
        "absorption_score": 50, # Placeholder (needs detailed logic if required)
        "continuation_score": 50, # Placeholder
        "sweep_score": 0
    }
    
    total_score = 0
    total_weight = 0
    for k, w in weights.items():
        if k in scores:
            total_score += scores[k] * w
            total_weight += w
            
    return total_score / total_weight if total_weight > 0 else 0

def calculate_features(data: Dict[str, Any], ts: float) -> Optional[Dict[str, Any]]:
    trades = data["trades"]
    ob = data["ob"]
    if not ob or not trades: return None
    
    current_price = trades[-1]["price"]
    
    # Trade Metrics (Optimized)
    cutoff_10 = ts - 10.0
    b10, s10 = 0.0, 0.0
    for i in range(len(trades)-1, -1, -1):
        t = trades[i]
        if t["ts"] < cutoff_10: break
        if t["side"] == 'ASK': b10 += t["price"] * t["vol"]
        else: s10 += t["price"] * t["vol"]
    
    imbal_10 = (b10 - s10) / (b10 + s10) if (b10 + s10) > 0 else 0
    
    # Orderbook
    units = ob.get("orderbook_units", [])
    if not units: return None
    best_ask, best_bid = float(units[0]["ask_price"]), float(units[0]["bid_price"])
    spread_pct = (best_ask - best_bid) / best_bid * 100.0
    ask_depth = sum(float(u["ask_size"]) for u in units[:5])
    bid_depth = sum(float(u["bid_size"]) for u in units[:5])
    depth_ratio = bid_depth / ask_depth if ask_depth > 0 else 1.0
    
    # Price Change
    cutoff_p10 = ts - 10.0
    past_p10 = trades[0]["price"]
    for i in range(len(trades)-1, -1, -1):
        if trades[i]["ts"] <= cutoff_p10:
            past_p10 = trades[i]["price"]
            break
    price_chg_10 = (current_price - past_p10) / past_p10 * 100.0
    
    return {
        "ts": ts, "price": current_price,
        "buy_trade_value_10s": b10, "sell_trade_value_10s": s10, "imbalance_10s": imbal_10,
        "spread_pct": spread_pct, "depth_ratio": depth_ratio, "price_chg_10s": price_chg_10
    }

def generate_summary_txt(results, output_txt, thresholds, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("        Short-Term Trend v1 Backtest Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {results['timestamp']}")
    lines.append(f"사용 후보: {results['candidate']}")
    lines.append(f"비용 기준: {results['cost_floor']:.2f}% (수수료+슬리피지)")
    lines.append("")
    lines.append("※ 이 도구는 설정값을 자동으로 적용하지 않습니다.")
    lines.append("※ 실거래 반영 전 추가적인 Paper Trading 실험이 반드시 필요합니다.")
    lines.append("")

    best_key = None
    max_net_pnl = -999

    for th in thresholds:
        for window in windows:
            key = f"th{th}_w{window}"
            stats = results["by_threshold_window"].get(key, {})
            if not stats or stats.get("count", 0) == 0: continue
            
            lines.append(f"--- [Threshold: {th} / Window: {window}s] ---")
            lines.append(f"후보 수: {stats['count']}회")
            lines.append(f"승률(Net PnL > 0): {stats['win_rate']:.2f}%")
            lines.append(f"평균 Gross PnL: {stats['gross_return_avg']:.4f}%")
            lines.append(f"평균 Net PnL: {stats['net_return_avg']:.4f}%")
            lines.append(f"MFE 평균: {stats['mfe_avg']:.4f}% / Max: {stats['mfe_max']:.4f}%")
            lines.append(f"MAE 평균: {stats['mae_avg']:.4f}% / Max: {stats['mae_max']:.4f}%")
            lines.append(f"0.20% MFE 통과 수: {stats['ge_020']}회")
            lines.append("")
            
            if stats['net_return_avg'] > max_net_pnl:
                max_net_pnl = stats['net_return_avg']
                best_key = key

    lines.append("--- 진단 결론 ---")
    if best_key:
        lines.append(f"1. 가장 유리한 설정: {best_key}")
        if max_net_pnl > 0:
            lines.append(f"2. Net PnL 양수 여부: 예 ({max_net_pnl:.4f}%)")
            lines.append("3. 판단: Short-Term Trend v1은 Paper 전략 실험으로 전환 가능성이 높음.")
        else:
            lines.append(f"2. Net PnL 양수 여부: 아니오 ({max_net_pnl:.4f}%)")
            lines.append("3. 판단: 현재 가중치로는 비용 극복이 어려움. 가중치 재조정 필요.")
    else:
        lines.append("1. 분석 결과: 진입 후보가 발생하지 않았거나 유효한 데이터가 부족함.")

    lines.append("")
    lines.append("4. 다음 단계:")
    lines.append("   - 결과가 양호할 경우 configs/experiments/config_*.json 에 반영하여 Paper Trading 시작.")
    lines.append("   - orderflow_paper.py 수정 전, DDM 및 하드 블록 조건을 포함한 정밀 시뮬레이션 권장.")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
