import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_factor_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    시장 장세 요인(변동성, 불균형, 호가 등)과 수익 기회 사이의 상관관계를 분석합니다.
    """
    print(f"[MarketFactor] Starting diagnostics. WS: {ws_path}")

    # (Pre-calculation logic same as before, simplified for this refactor example)
    # I'll keep the full logic since I need to overwrite the file.
    
    market_data: Dict[str, Dict[str, Any]] = {}
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
        print(f"[MarketFactor] Load Error: {e}"); return

    # Convert to arrays
    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    # Sampling and Analysis
    all_ts = []
    for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    factors_winner = []
    factors_loser = []
    
    print("[MarketFactor] Sampling points...")
    for ts in np.arange(min_ts + 600, max_ts - 600, 1.0):
        for s in symbol_arrays:
            idx = np.searchsorted(symbol_arrays[s]["ts"], ts, side='right')
            if idx == 0: continue
            
            f = calculate_factors_v2(market_data[s], symbol_arrays[s], ts)
            if not f: continue
            
            # Outcome (300s)
            ret, mfe = calculate_outcome_v2(symbol_arrays[s], ts, 300, f["price"])
            if ret is None: continue
            
            if mfe >= 0.20: factors_winner.append(f)
            else: factors_loser.append(f)

    # Aggregation
    stats = {}
    if factors_winner:
        all_keys = factors_winner[0].keys()
        for k in all_keys:
            if k == "price": continue
            w_vals = [f[k] for f in factors_winner]
            l_vals = [f[k] for f in factors_loser]
            stats[k] = {
                "winner_avg": float(np.mean(w_vals)),
                "non_winner_avg": float(np.mean(l_vals)) if l_vals else 0,
                "diff": float(np.mean(w_vals) - np.mean(l_vals)) if l_vals else 0,
                "importance": float(abs(np.mean(w_vals) - np.mean(l_vals)) / (np.std(w_vals + l_vals) + 1e-9))
            }
            # For threshold calibration: store distribution
            stats[k]["distribution"] = {"winner": [float(v) for v in w_vals], "non_winner": [float(v) for v in l_vals]}

    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(factors_winner) + len(factors_loser),
        "winners_count": len(factors_winner),
        "stats": stats
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[MarketFactor] Done. Reports: {output_json}, {output_txt}")

def calculate_factors_v2(data, arr, ts):
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
    spread = 0.1; depth = 1.0
    if data["ob"]:
        units = data["ob"].get("orderbook_units", []) or data["ob"].get("raw", {}).get("orderbook_units", [])
        if units:
            spread = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
            depth = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0
    return {"price": price, "volatility_300s": volat, "imbalance_300s": imb300, "depth_ratio": depth, "spread_pct": spread}

def calculate_outcome_v2(arr, ts, window, entry_price):
    idx_s = np.searchsorted(arr["ts"], ts, side='right')
    idx_e = np.searchsorted(arr["ts"], ts + window, side='right')
    if idx_e > idx_s:
        prices = arr["pr"][idx_s:idx_e]
        return (prices[-1] - entry_price) / entry_price * 100, (np.max(prices) - entry_price) / entry_price * 100
    return None, None

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Market Factor Analysis Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append(f"전체 샘플: {out['total_samples']} | 수익 기회(Winner): {out['winners_count']}")
    lines.append("")
    lines.append(f"{'Factor':25} | {'Winner Avg':12} | {'Loser Avg':12} | {'Diff':10}")
    lines.append("-" * 70)
    for k, v in out["stats"].items():
        lines.append(f"{k:25} | {v['winner_avg']:12.4f} | {v['non_winner_avg']:12.4f} | {v['diff']:10.4f}")
    lines.append("")
    lines.append("--- 진단 결론 ---")
    lines.append("1. 특정 Factor의 Winner/Loser 차이가 클수록 필터로 활용하기 적합합니다.")
    lines.append("2. 주의: 본 결과는 특정 시점 로그에 국한됩니다.")
    report_io.write_text_report(output_txt, "\n".join(lines))
