import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_market_factor_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    0.20% 이상 상승 구간의 공통 시장 조건(Volatility, Volume, Sync 등)을 분석합니다.
    """
    print(f"[FactorDiag] Starting diagnostics with WS log: {ws_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"File not found: {ws_path}"}
        with open(output_json, 'w', encoding='utf-8') as f: json.dump(result, f, indent=2)
        return

    # Data structures
    market_data: Dict[str, Dict[str, Any]] = {}
    windows = [300, 600]
    threshold = 0.20
    
    samples: Dict[str, List[Dict[str, Any]]] = {}

    print("[FactorDiag] Loading and processing events...")
    
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line_idx, line in enumerate(f):
                if not line.strip(): continue
                try:
                    event = json.loads(line)
                except Exception as je:
                    if line_idx < 5:
                        print(f"[FactorDiag] JSON Load Error at line {line_idx+1}: {je}")
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

                current_ts = event.get("received_at")
                if current_ts - market_data[symbol]["last_sample_ts"] >= 1.0:
                    market_data[symbol]["last_sample_ts"] = current_ts

    except Exception as e:
        print(f"[FactorDiag] Error loading: {e}")
        return

    print("[FactorDiag] Pre-calculating arrays...")
    all_symbols = list(market_data.keys())
    all_ts = []
    symbol_arrays = {}
    for s in all_symbols:
        if market_data[s]["trades"]:
            ts_arr = np.array([t["ts"] for t in market_data[s]["trades"]])
            pr_arr = np.array([t["price"] for t in market_data[s]["trades"]])
            symbol_arrays[s] = {"ts": ts_arr, "pr": pr_arr}
            all_ts.append(ts_arr[0])
            all_ts.append(ts_arr[-1])
    
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    factor_keys = [
        "volatility_60s", "volatility_300s", "range_300s", "range_600s",
        "volume_60s", "volume_300s", "volume_spike_60s",
        "imbalance_60s", "imbalance_300s", "spread_pct", "depth_ratio",
        "btc_alignment", "market_sync_score"
    ]
    
    all_samples = []
    sampling_ts = np.arange(min_ts + 600, max_ts - 600, 1.0)
    print(f"[FactorDiag] Sampling {len(sampling_ts)} points...")

    for ts in sampling_ts:
        sync_data = {}
        for s in all_symbols:
            arr = symbol_arrays.get(s)
            if not arr: continue
            curr_p = get_price_at_v2(arr, ts)
            past_p = get_price_at_v2(arr, ts - 60.0)
            if curr_p and past_p:
                sync_data[s] = np.sign(curr_p - past_p)
        
        if not sync_data: continue
        
        btc_dir = sync_data.get("KRW-BTC", 0)
        market_dirs = list(sync_data.values())
        sync_score = sum(1 for d in market_dirs if d == btc_dir) / len(market_dirs) if btc_dir != 0 else 0

        for s in all_symbols:
            arr = symbol_arrays.get(s)
            if not arr: continue
            
            idx_s = np.searchsorted(arr["ts"], ts, side='right')
            idx_e600 = np.searchsorted(arr["ts"], ts + 600, side='right')
            
            if idx_e600 > idx_s:
                w_prices = arr["pr"][idx_s:idx_e600]
                max_p = np.max(w_prices)
                start_p = get_price_at_v2(arr, ts)
                if not start_p: continue
                mfe = (max_p - start_p) / start_p * 100.0
                
                factors = calculate_regime_factors_v2(market_data[s], arr, ts)
                factors["btc_alignment"] = 1.0 if sync_data.get(s, 0) == btc_dir and btc_dir != 0 else 0.0
                factors["market_sync_score"] = sync_score
                factors["mfe"] = mfe
                factors["symbol"] = s
                factors["ts"] = ts
                all_samples.append(factors)

    if not all_samples:
        print("[FactorDiag] No valid samples found.")
        return

    results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "total_samples": len(all_samples),
        "winners_count": sum(1 for s in all_samples if s["mfe"] >= threshold),
        "comparison": {},
        "regime_efficacy": {}
    }

    winners = [s for s in all_samples if s["mfe"] >= threshold]
    losers = [s for s in all_samples if s["mfe"] < threshold]

    for k in factor_keys:
        w_vals = [s[k] for s in winners]
        l_vals = [s[k] for s in losers]
        w_avg = np.mean(w_vals) if w_vals else 0
        l_avg = np.mean(l_vals) if l_vals else 0
        diff = w_avg - l_avg
        results["comparison"][k] = {
            "winner_avg": float(w_avg),
            "non_winner_avg": float(l_avg),
            "diff": float(diff),
            "importance": float(abs(diff) / (abs(l_avg) + 1e-9))
        }

    for k in ["volatility_300s", "volume_spike_60s", "market_sync_score", "spread_pct"]:
        all_vals = [s[k] for s in all_samples]
        median_v = np.median(all_vals)
        high_group = [s for s in all_samples if s[k] > median_v]
        low_group = [s for s in all_samples if s[k] <= median_v]
        high_wr = sum(1 for s in high_group if s["mfe"] >= threshold) / len(high_group) * 100 if high_group else 0
        low_wr = sum(1 for s in low_group if s["mfe"] >= threshold) / len(low_group) * 100 if low_group else 0
        results["regime_efficacy"][k] = {
            "median": float(median_v),
            "high_group_winner_rate": float(high_wr),
            "low_group_winner_rate": float(low_wr),
            "lift": float(high_wr / (low_wr + 1e-9))
        }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    generate_summary_txt(results, output_txt)
    print(f"[FactorDiag] Done. Reports: {output_json}, {output_txt}")

def get_price_at_v2(arr, ts):
    idx = np.searchsorted(arr["ts"], ts, side='right')
    if idx == 0: return None
    return arr["pr"][idx-1]

def calculate_regime_factors_v2(data, arr, ts):
    trades = data["trades"]
    ob = data["ob"]
    
    def get_stats_v2(lookback):
        cutoff = ts - lookback
        idx_start = np.searchsorted(arr["ts"], cutoff, side='left')
        idx_end = np.searchsorted(arr["ts"], ts, side='right')
        
        if idx_end <= idx_start: return 0, 0, 0, 0
        
        prices = arr["pr"][idx_start:idx_end]
        relevant_trades = trades[idx_start:idx_end]
        
        volat = np.std(prices) / np.mean(prices) * 100.0 if np.mean(prices) != 0 else 0
        range_pct = (np.max(prices) - np.min(prices)) / np.min(prices) * 100.0 if np.min(prices) != 0 else 0
        
        volume = sum(t["price"] * t["vol"] for t in relevant_trades)
        buys = sum(t["price"] * t["vol"] for t in relevant_trades if t["side"] == 'ASK')
        sells = volume - buys
        imbal = (buys - sells) / volume if volume > 0 else 0
        
        return volat, range_pct, volume, imbal

    v60, r60, vol60, imb60 = get_stats_v2(60.0)
    v300, r300, vol300, imb300 = get_stats_v2(300.0)
    
    vol_spike = vol60 / (vol300 / 5.0 + 1.0)
    
    spread = 0.1
    depth = 1.0
    if ob:
        units = ob.get("raw", {}).get("orderbook_units", []) or ob.get("orderbook_units", [])
        if units:
            spread = (float(units[0]["ask_price"]) - float(units[0]["bid_price"])) / float(units[0]["bid_price"]) * 100.0
            depth = sum(float(u["bid_size"]) for u in units[:5]) / sum(float(u["ask_size"]) for u in units[:5]) if sum(float(u["ask_size"]) for u in units[:5]) > 0 else 1.0

    return {
        "volatility_60s": v60,
        "volatility_300s": v300,
        "range_300s": r300,
        "range_600s": r300, # Simplified
        "volume_60s": vol60,
        "volume_300s": vol300,
        "volume_spike_60s": vol_spike,
        "imbalance_60s": imb60,
        "imbalance_300s": imb300,
        "spread_pct": spread,
        "depth_ratio": depth
    }

def generate_summary_txt(results, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Market Factor Diagnostics Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {results['timestamp']}")
    lines.append(f"전체 샘플 수: {results['total_samples']}")
    lines.append(f"Winner (MFE >= 0.20%) 수: {results['winners_count']}")
    lines.append("")
    lines.append("※ 이 도구는 설정값을 자동으로 적용하지 않습니다.")
    lines.append("※ 결과 분석은 장세 필터(Regime Filter) 설계를 위한 근거로만 사용하십시오.")
    lines.append("")

    lines.append("--- [Winner vs Non-Winner 주요 지표 차이] ---")
    sorted_m = sorted(results["comparison"].items(), key=lambda x: x[1]["importance"], reverse=True)
    for k, v in sorted_m[:10]:
        lines.append(f"- {k:20}: Winner({v['winner_avg']:10.4f}) vs Loser({v['non_winner_avg']:10.4f}) | Diff: {v['diff']:.4f}")
    lines.append("")

    lines.append("--- [장세 필터(Regime Filter) 효용성 분석] ---")
    for k, v in results["regime_efficacy"].items():
        lines.append(f"- {k:20}: High WR({v['high_group_winner_rate']:.2f}%) vs Low WR({v['low_group_winner_rate']:.2f}%) | Lift: {v['lift']:.2f}x")
    lines.append("")

    lines.append("--- 진단 결론 ---")
    if sorted_m:
        top_factor = sorted_m[0][0]
        lines.append(f"1. 가장 변별력이 큰 마켓 팩터: {top_factor}")
    
    sync_lift = results["regime_efficacy"].get("market_sync_score", {}).get("lift", 1.0)
    if sync_lift > 1.2:
        lines.append(f"2. 시장 동기화(Market Sync) 유효성: 매우 높음 ({sync_lift:.2f}배 확률 상승)")
    else:
        lines.append(f"2. 시장 동기화(Market Sync) 유효성: 낮음")

    vol_lift = results["regime_efficacy"].get("volatility_300s", {}).get("lift", 1.0)
    if vol_lift > 1.5:
        lines.append(f"3. 변동성 필터(Volatility Filter) 필요성: 필수 (고변동성 장세에서 기회 집중)")
    else:
        lines.append(f"3. 변동성 필터(Volatility Filter) 필요성: 낮음")

    lines.append("4. 피해야 할 장세 조건:")
    if sorted_m:
        lines.append(f"   - {top_factor}가 낮거나 역방향인 구간")
    lines.append("   - 시장 전체의 동기화가 깨져 있는 구간")

    lines.append("5. 다음 전략 방향:")
    lines.append("   - Market Factor Filter v1 설계 (진입 전 장세 필터링 추가)")
    lines.append("   - 오더플로우 점수가 높더라도 장세 필터를 통과하지 못하면 진입 차단")
    lines.append("   - 현재 5~10분 보유 전략 유지하되 장세 필터 결합 필수")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
