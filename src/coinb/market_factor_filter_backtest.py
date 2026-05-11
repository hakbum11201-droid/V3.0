import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_factor_filter_backtest(ws_path: str, market_filter_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    """
    Market Factor Filter를 통과한 시점의 Short-Term Trend 성과를 백테스트합니다.
    """
    print(f"[FactorFilterBT] Starting backtest. WS: {ws_path}")

    if not all(os.path.exists(p) for p in [ws_path, market_filter_path, trend_candidate_path]):
        result = {"ok": False, "reason": "Candidate files not found."}
        report_io.write_json_report(output_json, result)
        return

    # 1. Load Candidates
    with open(market_filter_path, 'r', encoding='utf-8') as f: m_factor = json.load(f)
    with open(trend_candidate_path, 'r', encoding='utf-8') as f: trend_c = json.load(f)

    # 2. Extract Configs
    mf_cfg = m_factor["market_factor_filter"]
    weights = trend_c["weights"]
    cost_floor = trend_c.get("cost_floor_pct", 0.20)

    # 3. Data Processing (Trades/Orderbooks)
    market_data: Dict[str, Dict[str, Any]] = {}
    print("[FactorFilterBT] Loading and pre-calculating arrays...")
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
        print(f"[FactorFilterBT] Load Error: {e}"); return

    # Convert to arrays for speed
    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    # 4. Strategy Evaluation
    print("[FactorFilterBT] Evaluating candidates with filter...")
    windows = [300, 600]
    thresholds = [75, 85]
    
    results = {f"th{th}_w{win}": [] for th in thresholds for win in windows}
    all_samples = []

    # Point-by-point eval (1s step)
    all_ts = []
    for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    for ts in np.arange(min_ts + 600, max_ts - 600, 1.0):
        for symbol in market_data:
            # Check Filter
            factors = calculate_factors_v3(market_data[symbol], symbol_arrays.get(symbol), ts)
            if not factors: continue
            
            if not pass_market_factor_filter(factors, mf_cfg): continue
            
            # Score
            score = calculate_trend_score_v3(factors, weights)
            
            for win in windows:
                for th in thresholds:
                    if score >= th:
                        ret, mfe = calculate_outcome_v3(symbol_arrays[symbol], ts, win, factors["price"])
                        if ret is not None:
                            results[f"th{th}_w{win}"].append({"ret": ret, "mfe": mfe})
                            if th == 75 and win == 600: # Store samples for winner profile
                                all_samples.append({
                                    "ts": float(ts), "symbol": symbol, "factors": factors,
                                    "score": float(score), "net_pnl": float(ret - cost_floor), "mfe": float(mfe)
                                })

    # 5. Output
    final_stats = {}
    for key, data in results.items():
        if data:
            rets = np.array([d["ret"] for d in data])
            mfes = np.array([d["mfe"] for d in data])
            net_rets = rets - cost_floor
            final_stats[key] = {
                "count": len(rets),
                "avg_net_pnl": float(np.mean(net_rets)),
                "win_rate": float(np.sum(rets > cost_floor) / len(rets) * 100),
                "hits_020": int(np.sum(mfes >= 0.20))
            }

    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "stats": final_stats,
        "samples": all_samples
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[FactorFilterBT] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v3(data, arr, ts):
    if arr is None: return None
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
        "price": price, "volatility_300s": volat, "imbalance_300s": imb300, "depth_ratio": depth,
        "spread_pct": spread, "price_chg_10s": p10, "buy_trade_value_10s": v_buy10
    }

def pass_market_factor_filter(f, cfg):
    if f["volatility_300s"] < cfg.get("min_volatility_300s_pct", 0.05): return False
    if f["imbalance_300s"] < cfg.get("min_imbalance_300s", 0.10): return False
    if f["depth_ratio"] < cfg.get("min_bid_ask_depth_ratio_5", 1.50): return False
    if f["spread_pct"] > cfg.get("max_spread_pct", 0.12): return False
    return True

def calculate_trend_score_v3(f, weights):
    def scale(v, min_v, max_v): return np.clip((v - min_v) / (max_v - min_v) * 100, 0, 100)
    scores = {
        "imbalance_10s_score": scale(f["imbalance_300s"], -0.5, 0.5),
        "price_chg_10s_score": scale(f["price_chg_10s"], -0.05, 0.05),
        "volume_10s_score": scale(f["buy_trade_value_10s"], 0, 10000000),
        "spread_score": scale(f["spread_pct"], 0.2, 0.02),
        "depth_score": scale(f["depth_ratio"], 0.5, 2.0),
        "absorption_score": 50, "continuation_score": 50, "sweep_score": 0
    }
    return sum(scores[k] * weights.get(k, 0) for k in scores) / sum(weights.values())

def calculate_outcome_v3(arr, ts, window, entry_price):
    idx_s = np.searchsorted(arr["ts"], ts, side='right')
    idx_e = np.searchsorted(arr["ts"], ts + window, side='right')
    if idx_e > idx_s:
        prices = arr["pr"][idx_s:idx_e]
        return (prices[-1] - entry_price) / entry_price * 100, (np.max(prices) - entry_price) / entry_price * 100
    return None, None

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("      Market Factor Filter Backtest Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append("")
    for key in sorted(out["stats"].keys()):
        s = out["stats"][key]
        lines.append(f"- [{key:9}] Count: {s['count']:4} | Avg Net: {s['avg_net_pnl']:.4f}% | Win: {s['win_rate']:5.2f}% | 0.2% Hits: {s['hits_020']}")
    lines.append("")
    lines.append("--- 진단 결론 ---")
    lines.append("1. 필터 적용 시 이전보다 승률(Win Rate)이 개선되었는지 확인하십시오.")
    lines.append("2. 하지만 평균 Net PnL이 음수라면 비용 구조를 이기지 못한 것입니다.")
    lines.append("3. 주의: 본 결과는 특정 샘플에 국한됩니다.")
    report_io.write_text_report(output_txt, "\n".join(lines))
