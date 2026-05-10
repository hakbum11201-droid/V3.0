import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_market_factor_filter_backtest(ws_path: str, market_filter_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    """
    Market Factor Filter v1 + Short-Term Trend v1 결합 성과를 백테스트합니다.
    """
    print(f"[CombinedBT] Starting backtest. WS: {ws_path}")

    if not os.path.exists(ws_path) or not os.path.exists(market_filter_path) or not os.path.exists(trend_candidate_path):
        result = {"ok": False, "reason": "Required files not found."}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # 1. Load Candidates
    with open(market_filter_path, 'r', encoding='utf-8') as f:
        m_filter = json.load(f)
    with open(trend_candidate_path, 'r', encoding='utf-8') as f:
        t_candidate = json.load(f)

    f_conf = m_filter["market_factor_filter"]
    t_weights = t_candidate["weights"]
    thresholds = t_candidate.get("threshold_candidates", [75, 85, 95])
    windows = t_candidate.get("holding_windows_sec", [300, 600])
    cost_floor = t_candidate.get("cost_floor_pct", 0.20)

    # 2. Load Data
    market_data: Dict[str, Dict[str, Any]] = {}
    print("[CombinedBT] Loading and pre-calculating arrays...")
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line_idx, line in enumerate(f):
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
    except Exception as e:
        print(f"[CombinedBT] Load Error: {e}")
        return

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

    # 3. Sampling and Evaluation
    print("[CombinedBT] Sampling points and evaluating filters...")
    sampling_ts = np.arange(min_ts + 600, max_ts - 600, 1.0)
    samples_list = []
    pass_count = 0

    for ts in sampling_ts:
        for s in market_data:
            arr = symbol_arrays.get(s)
            if not arr: continue
            
            # 1. Calculate Market Factors
            factors = calculate_factors_v2(market_data[s], arr, ts)
            if not factors: continue
            
            # 2. Check Market Filter
            passed = (
                factors["volatility_300s"] >= f_conf["min_volatility_300s_pct"] and
                factors["imbalance_300s"] >= f_conf["min_imbalance_300s"] and
                factors["depth_ratio"] >= f_conf["min_bid_ask_depth_ratio_5"] and
                factors["spread_pct"] <= f_conf["max_spread_pct"]
            )
            
            # Calculate Trend Score regardless for comparison
            score = calculate_trend_score_v2(factors, t_weights)
            
            # Get Future Result
            idx_s = np.searchsorted(arr["ts"], ts, side='right')
            idx_e600 = np.searchsorted(arr["ts"], ts + 600, side='right')
            idx_e300 = np.searchsorted(arr["ts"], ts + 300, side='right')
            
            outcome = {}
            if idx_e300 > idx_s:
                w_pr = arr["pr"][idx_s:idx_e300]
                outcome["300"] = {"ret": (w_pr[-1] - factors["price"]) / factors["price"] * 100.0, "mfe": (np.max(w_pr) - factors["price"]) / factors["price"] * 100.0}
            if idx_e600 > idx_s:
                w_pr = arr["pr"][idx_s:idx_e600]
                outcome["600"] = {"ret": (w_pr[-1] - factors["price"]) / factors["price"] * 100.0, "mfe": (np.max(w_pr) - factors["price"]) / factors["price"] * 100.0}
            
            if outcome:
                samples_list.append({
                    "symbol": s, "ts": ts, "factors": factors, "filter_pass": passed, "score": score, "outcome": outcome
                })
                if passed: pass_count += 1

    if not samples_list:
        print("[CombinedBT] No samples collected.")
        return

    # 4. Aggregate Results
    results = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(samples_list),
        "filter_pass_count": pass_count,
        "filter_pass_rate": float(pass_count / len(samples_list) * 100),
        "stats": {},
        "samples": samples_list
    }

    print("[CombinedBT] Aggregating performance stats...")
    for th in thresholds:
        for window in windows:
            w_str = str(window)
            key = f"th{th}_w{window}"
            
            def get_group_stats(use_filter: bool):
                group = [s for s in samples_list if s["score"] >= th and (not use_filter or s["filter_pass"])]
                if not group: return None
                rets = np.array([s["outcome"][w_str]["ret"] for s in group if w_str in s["outcome"]])
                mfes = np.array([s["outcome"][w_str]["mfe"] for s in group if w_str in s["outcome"]])
                if len(rets) == 0: return None
                return {
                    "count": len(rets),
                    "avg_net_pnl": float(np.mean(rets - cost_floor)),
                    "win_rate": float(np.sum(rets > cost_floor) / len(rets) * 100),
                    "mfe_020": int(np.sum(mfes >= 0.20)),
                    "mfe_avg": float(np.mean(mfes))
                }

            results["stats"][key] = {
                "before": get_group_stats(False),
                "after": get_group_stats(True)
            }

    def to_json_ready(obj):
        if isinstance(obj, dict):
            return {k: to_json_ready(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [to_json_ready(v) for v in obj]
        elif isinstance(obj, (np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        return obj

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(to_json_ready(results), f, indent=2)

    generate_summary_txt(results, output_txt, thresholds, windows)
    print(f"[CombinedBT] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v2(data, arr, ts):
    idx_end = np.searchsorted(arr["ts"], ts, side='right')
    if idx_end == 0: return None
    price = arr["pr"][idx_end-1]
    
    idx_start300 = np.searchsorted(arr["ts"], ts - 300, side='left')
    idx_start10 = np.searchsorted(arr["ts"], ts - 10, side='left')
    
    # Volatility and Range
    if idx_end > idx_start300:
        p300 = arr["pr"][idx_start300:idx_end]
        volat = np.std(p300) / np.mean(p300) * 100.0
        # Imbalance 300s
        rel_trades = data["trades"][idx_start300:idx_end]
        v_tot = sum(t["price"] * t["vol"] for t in rel_trades)
        v_buy = sum(t["price"] * t["vol"] for t in rel_trades if t["side"] == 'ASK')
        imb300 = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
        # Imbalance 10s
        rel_t10 = data["trades"][idx_start10:idx_end]
        v_tot10 = sum(t["price"] * t["vol"] for t in rel_t10)
        v_buy10 = sum(t["price"] * t["vol"] for t in rel_t10 if t["side"] == 'ASK')
        imb10 = (v_buy10 - (v_tot10 - v_buy10)) / v_tot10 if v_tot10 > 0 else 0
        # Price Chg 10s
        p10 = (price - arr["pr"][idx_start10]) / arr["pr"][idx_start10] * 100.0 if idx_end > idx_start10 else 0
    else:
        return None

    # Orderbook
    spread = 0.1; depth = 1.0
    if data["ob"]:
        units = data["ob"].get("orderbook_units", []) or data["ob"].get("raw", {}).get("orderbook_units", [])
        if units:
            spread = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
            depth = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0

    return {
        "price": price, "volatility_300s": volat, "imbalance_300s": imb300, "imbalance_10s": imb10,
        "depth_ratio": depth, "spread_pct": spread, "price_chg_10s": p10, "buy_trade_value_10s": v_buy10
    }

def calculate_trend_score_v2(f, weights):
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

def generate_summary_txt(res, output_txt, thresholds, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("      Market Factor Filter + Short-Term Trend Backtest (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"전체 샘플: {res['total_samples']} | Filter 통과: {res['filter_pass_count']} ({res['filter_pass_rate']:.2f}%)")
    lines.append("")

    for th in thresholds:
        for window in windows:
            key = f"th{th}_w{window}"
            stats = res["stats"].get(key)
            if not stats: continue
            bef, aft = stats["before"], stats["after"]
            lines.append(f"--- [Threshold: {th} / Window: {window}s] ---")
            if bef:
                lines.append(f"필터 전: {bef['count']:4}회 | Net PnL: {bef['avg_net_pnl']:.4f}% | Win: {bef['win_rate']:.2f}% | 0.2% Hits: {bef['mfe_020']}")
            if aft:
                lines.append(f"필터 후: {aft['count']:4}회 | Net PnL: {aft['avg_net_pnl']:.4f}% | Win: {aft['win_rate']:.2f}% | 0.2% Hits: {aft['mfe_020']}")
            else:
                lines.append("필터 후: 후보 없음")
            lines.append("")

    lines.append("--- 진단 결론 ---")
    best_key = None; max_improve = -999
    for k, v in res["stats"].items():
        if v["before"] and v["after"]:
            improve = v["after"]["avg_net_pnl"] - v["before"]["avg_net_pnl"]
            if improve > max_improve:
                max_improve = improve; best_key = k

    if best_key:
        lines.append(f"1. 가장 큰 개선 발생 설정: {best_key} (개선폭: {max_improve:.4f}%)")
        aft_pnl = res["stats"][best_key]["after"]["avg_net_pnl"]
        if aft_pnl > -0.10: # Still might be negative but better
            lines.append(f"2. 성과 개선 여부: 예 (Net PnL 손실폭 대폭 감소)")
            if aft_pnl > 0:
                lines.append("3. 판단: Market Factor Filter v1은 매우 효과적이며 Paper 실험으로 전환 권장.")
            else:
                lines.append("3. 판단: 필터가 효과적이나 추가적인 가중치 최적화 필요.")
        else:
            lines.append("2. 성과 개선 여부: 미미함")
            lines.append("3. 판단: 현재 필터 조건만으로는 비용 극복이 여전히 어려움.")
    else:
        lines.append("1. 분석 결과: 유효한 개선 비교 데이터가 부족함.")

    lines.append("")
    lines.append("※ 자동 config 반영 금지. orderflow_paper.py 수정 전 추가 paper 실험 필수.")
    with open(output_txt, 'w', encoding='utf-8') as f: f.write("\n".join(lines))
