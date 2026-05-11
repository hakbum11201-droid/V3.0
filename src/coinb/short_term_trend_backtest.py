import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_short_term_trend_backtest(ws_path: str, candidate_path: str, output_json: str, output_txt: str):
    """
    Short-Term Trend v1 후보 설정을 기반으로 3시간 로그 백테스트를 수행합니다.
    """
    print(f"[TrendBT] Starting backtest. WS: {ws_path}, Candidate: {candidate_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"WS log not found: {ws_path}"}
        report_io.write_json_report(output_json, result)
        return

    if not os.path.exists(candidate_path):
        result = {"ok": False, "reason": f"Candidate file not found: {candidate_path}"}
        report_io.write_json_report(output_json, result)
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
            for line in f:
                if not line.strip(): continue
                try: event = json.loads(line)
                except: continue
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
                    market_data[symbol]["trades"].append({
                        "ts": ts, "price": float(raw.get("trade_price") or event.get("trade_price")),
                        "vol": float(raw.get("trade_volume") or event.get("trade_volume")),
                        "side": raw.get("ask_bid")
                    })
                elif is_ob: market_data[symbol]["ob"] = raw

                current_ts = event.get("received_at")
                if current_ts - market_data[symbol]["last_sample_ts"] >= 1.0:
                    if market_data[symbol]["ob"] and market_data[symbol]["trades"]:
                        sample = calculate_features(market_data[symbol], current_ts)
                        if sample:
                            sample["trend_score"] = calculate_trend_score(sample, weights)
                            samples[symbol].append(sample)
                            market_data[symbol]["last_sample_ts"] = current_ts
    except Exception as e:
        print(f"[TrendBT] Error: {e}"); return

    # 3. Simulate Results
    results = {
        "ok": True, "timestamp": datetime.now().isoformat(), "candidate": candidate["name"],
        "cost_floor": cost_floor, "by_threshold_window": {}
    }

    for th in thresholds:
        for window in windows:
            key = f"th{th}_w{window}"
            trade_stats = {"count": 0, "net_return_avg": 0, "win_rate": 0, "mfe_avg": 0, "ge_020": 0}
            returns, mfes = [], []
            for symbol, s_list in samples.items():
                trades = market_data[symbol]["trades"]
                trade_ts = np.array([t["ts"] for t in trades])
                trade_prices = np.array([t["price"] for t in trades])
                for s in s_list:
                    if s["trend_score"] >= th:
                        start_ts = s["ts"]; start_price = s["price"]; end_ts = start_ts + window
                        idx_s = np.searchsorted(trade_ts, start_ts, side='right')
                        idx_e = np.searchsorted(trade_ts, end_ts, side='right')
                        if idx_e > idx_s:
                            w_prices = trade_prices[idx_s:idx_e]
                            gross_ret = (w_prices[-1] - start_price) / start_price * 100.0
                            mfe = (np.max(w_prices) - start_price) / start_price * 100.0
                            returns.append(gross_ret); mfes.append(mfe)
                            trade_stats["count"] += 1
                            if mfe >= 0.20: trade_stats["ge_020"] += 1

            if trade_stats["count"] > 0:
                ret_arr = np.array(returns); mfe_arr = np.array(mfes)
                trade_stats["net_return_avg"] = float(np.mean(ret_arr - cost_floor))
                trade_stats["win_rate"] = float(np.sum(ret_arr > cost_floor) / len(ret_arr) * 100.0)
                trade_stats["mfe_avg"] = float(np.mean(mfe_arr))
            results["by_threshold_window"][key] = trade_stats

    report_io.write_json_report(output_json, results)
    generate_summary_txt(results, output_txt, thresholds, windows)
    print(f"[TrendBT] Done. Reports: {output_json}, {output_txt}")

def calculate_trend_score(s, weights):
    def scale(v, min_v, max_v): return np.clip((v - min_v) / (max_v - min_v) * 100, 0, 100)
    scores = {
        "imbalance_10s_score": scale(s["imbalance_10s"], -0.5, 0.5),
        "price_chg_10s_score": scale(s["price_chg_10s"], -0.05, 0.05),
        "volume_10s_score": scale(s["buy_trade_value_10s"], 0, 10000000),
        "spread_score": scale(s["spread_pct"], 0.2, 0.02),
        "depth_score": scale(s["depth_ratio"], 0.5, 2.0),
        "absorption_score": 50, "continuation_score": 50, "sweep_score": 0
    }
    tw = sum(weights.values())
    return sum(scores[k] * weights.get(k, 0) for k in scores) / tw if tw > 0 else 0

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
    return {
        "ts": ts, "price": curr_p, "buy_trade_value_10s": b10, "imbalance_10s": (b10-s10)/(b10+s10) if (b10+s10)>0 else 0,
        "spread_pct": spread, "depth_ratio": depth, "price_chg_10s": (curr_p-past_p)/past_p*100
    }

def generate_summary_txt(res, output_txt, thresholds, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("        Short-Term Trend v1 Backtest Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {res['timestamp']}")
    lines.append(f"사용 후보: {res['candidate']}")
    lines.append(f"비용 기준: {res['cost_floor']:.2f}% (수수료+슬리피지)\n")
    for th in thresholds:
        for w in windows:
            key = f"th{th}_w{w}"
            s = res["by_threshold_window"].get(key, {})
            if not s or s.get("count", 0) == 0: continue
            lines.append(f"--- [Threshold: {th} / Window: {w}s] ---")
            lines.append(f"후보 수: {s['count']}회 | 승률: {s['win_rate']:.2f}% | 평균 Net PnL: {s['net_return_avg']:.4f}%")
            lines.append(f"MFE 평균: {s['mfe_avg']:.4f}% | 0.20% MFE 통과: {s['ge_020']}회\n")
    lines.append("--- 진단 결론 ---")
    lines.append("1. 결과가 양호할 경우 configs/experiments/config_*.json 에 반영하여 Paper Trading 시작.")
    report_io.write_text_report(output_txt, "\n".join(lines))
