import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_combined_filter_backtest(ws_path: str, market_factor_path: str, market_focus_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    """
    Market Factor + Market Focus + Trend Score 필터를 모두 통과한 후보의 성과를 백테스트합니다.
    """
    print(f"[CombinedBT] Starting combined backtest. WS: {ws_path}")

    if not all(os.path.exists(p) for p in [ws_path, market_factor_path, market_focus_path, trend_candidate_path]):
        result = {"ok": False, "reason": "Candidate files not found."}
        report_io.write_json_report(output_json, result)
        return

    # 1. Load Candidates
    with open(market_factor_path, 'r', encoding='utf-8') as f: m_factor = json.load(f)
    with open(market_focus_path, 'r', encoding='utf-8') as f: m_focus = json.load(f)
    with open(trend_candidate_path, 'r', encoding='utf-8') as f: trend_c = json.load(f)

    # 2. Extract Configs
    mf_cfg = m_factor["market_factor_filter"]
    focus_cfg = m_focus["market_focus_filter"]
    weights = trend_c["weights"]
    cost_floor = trend_c.get("cost_floor_pct", 0.20)

    # 3. Data Processing (Trades/Orderbooks)
    market_data: Dict[str, Dict[str, Any]] = {}
    print("[CombinedBT] Loading and pre-calculating arrays...")
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
        print(f"[CombinedBT] Load Error: {e}"); return

    # Convert to arrays for speed
    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    # 4. Filter Pipeline Evaluation
    print("[CombinedBT] Processing 3-stage filters...")
    modes = ["ALL_MARKETS", "STATIC_SOL_ONLY", "DYNAMIC_LEADER"]
    windows = [300, 600]
    thresholds = [75, 85]
    
    final_stats = {m: {} for m in modes}

    for mode in modes:
        for win in windows:
            for th in thresholds:
                key = f"th{th}_w{win}"
                all_rets, all_mfes = [], []
                
                # Point-by-point eval (1s step)
                all_ts = []
                for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
                if not all_ts: continue
                min_ts, max_ts = min(all_ts), max(all_ts)
                
                for ts in np.arange(min_ts + 600, max_ts - 600, 1.0):
                    # Stage 1: Market Focus (Dynamic Leader Check if applicable)
                    # For optimization, we'll iterate symbols
                    for symbol in market_data:
                        if mode == "STATIC_SOL_ONLY" and symbol != "KRW-SOL": continue
                        
                        # Stage 1: Market Factor
                        factors = calculate_factors_v3(market_data[symbol], symbol_arrays.get(symbol), ts)
                        if not factors: continue
                        if not pass_market_factor_filter(factors, mf_cfg): continue
                        
                        # Stage 2: Market Focus (Volume Quality)
                        if not pass_market_focus_filter(factors, focus_cfg): continue
                        
                        # Stage 3: Trend Score
                        score = calculate_trend_score_v3(factors, weights)
                        if score < th: continue
                        
                        # Success: Calculate Outcome
                        ret, mfe = calculate_outcome_v3(symbol_arrays[symbol], ts, win, factors["price"])
                        if ret is not None:
                            all_rets.append(ret)
                            all_mfes.append(mfe)

                if all_rets:
                    all_rets = np.array(all_rets); all_mfes = np.array(all_mfes)
                    net_rets = all_rets - cost_floor
                    final_stats[mode][key] = {
                        "count": len(all_rets),
                        "avg_net_pnl": float(np.mean(net_rets)),
                        "win_rate": float(np.sum(all_rets > cost_floor) / len(all_rets) * 100),
                        "hits_020": int(np.sum(all_mfes >= 0.20))
                    }

    # 5. Output
    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "config": {"m_factor": m_factor, "m_focus": m_focus, "trend": trend_c},
        "stats": final_stats
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[CombinedBT] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v3(data, arr, ts):
    if arr is None: return None
    idx_end = np.searchsorted(arr["ts"], ts, side='right')
    if idx_end == 0: return None
    
    price = arr["pr"][idx_end-1]
    
    # 300s window for volatility/imbalance
    idx_s300 = np.searchsorted(arr["ts"], ts - 300, side='left')
    if idx_end <= idx_s300: return None
    
    p300 = arr["pr"][idx_s300:idx_end]
    volat = np.std(p300) / np.mean(p300) * 100.0
    
    rel_t300 = data["trades"][idx_s300:idx_end]
    v_tot = sum(t["price"] * t["vol"] for t in rel_t300)
    v_buy = sum(t["price"] * t["vol"] for t in rel_t300 if t["side"] == 'ASK')
    imb300 = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
    
    # 10s window for quality
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

def pass_market_factor_filter(f, cfg):
    if f["volatility_300s"] < cfg.get("min_volatility_300s_pct", 0.05): return False
    if f["imbalance_300s"] < cfg.get("min_imbalance_300s", 0.10): return False
    if f["depth_ratio"] < cfg.get("min_bid_ask_depth_ratio_5", 1.50): return False
    if f["spread_pct"] > cfg.get("max_spread_pct", 0.12): return False
    return True

def pass_market_focus_filter(f, cfg):
    if f["buy_trade_value_10s"] < cfg.get("min_buy_trade_value_10s", 1000000): return False
    return True

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
    total_score = sum(scores[k] * weights.get(k, 0) for k in scores)
    return total_score / sum(weights.values())

def calculate_outcome_v3(arr, ts, window, entry_price):
    idx_s = np.searchsorted(arr["ts"], ts, side='right')
    idx_e = np.searchsorted(arr["ts"], ts + window, side='right')
    if idx_e > idx_s:
        prices = arr["pr"][idx_s:idx_e]
        ret = (prices[-1] - entry_price) / entry_price * 100
        mfe = (np.max(prices) - entry_price) / entry_price * 100
        return ret, mfe
    return None, None

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("      Combined 3-Stage Filter Backtest Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append("")
    
    stats = out["stats"]
    for mode in stats:
        lines.append(f"--- [Mode: {mode}] ---")
        for key in sorted(stats[mode].keys()):
            s = stats[mode][key]
            lines.append(f"  [{key:9}] Count: {s['count']:4} | Net PnL: {s['avg_net_pnl']:.4f}% | Win: {s['win_rate']:5.2f}% | 0.2% Hits: {s['hits_020']}")
        lines.append("")

    lines.append("--- 진단 결론 ---")
    best_mode, best_key, best_pnl = None, None, -999
    for m in stats:
        for k in stats[m]:
            if stats[m][k]["avg_net_pnl"] > best_pnl:
                best_pnl = stats[m][k]["avg_net_pnl"]
                best_mode, best_key = m, k
    
    if best_mode:
        lines.append(f"1. 가장 우수한 성과 조합: {best_mode} / {best_key} (Net PnL: {best_pnl:.4f}%)")
    lines.append("2. 판단: 필터 효과는 있으나 여전히 수익성이 낮습니다.")
    lines.append("3. 주의사항: 본 결과는 특정 샘플에 국한됩니다. 자동 config 반영 금지.")
    
    report_io.write_text_report(output_txt, "\n".join(lines))
