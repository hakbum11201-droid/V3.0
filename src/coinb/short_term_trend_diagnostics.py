import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

def run_short_term_trend_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    3시간 WS 로그에서 단기 추세(Winner) 구간을 찾고 진입 전 주문흐름 특징을 분석합니다.
    """
    print(f"[TrendDiag] Starting diagnostics with WS log: {ws_path}")

    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"File not found: {ws_path}"}
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return

    # Data structures
    market_data: Dict[str, Dict[str, Any]] = {}
    windows = [120, 180, 300, 600]
    threshold = 0.20
    
    # Feature collection
    # We will sample every 1s
    samples: Dict[str, List[Dict[str, Any]]] = {}

    print("[TrendDiag] Loading and processing events...")
    
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line_idx, line in enumerate(f):
                if not line.strip(): continue
                try:
                    event = json.loads(line)
                except Exception as je:
                    if line_idx < 5: # Only print for first few lines to avoid spam
                        print(f"[TrendDiag] JSON Load Error at line {line_idx+1}: {je}")
                    continue
                    
                raw = event.get("raw", {})
                
                is_trade = (event.get("event_type") == "trade") or (raw.get("type") == "trade")
                is_ob = (event.get("event_type") == "orderbook") or (raw.get("type") == "orderbook")
                
                symbol = raw.get("code") or event.get("market")
                if not symbol: continue
                
                if symbol not in market_data:
                    market_data[symbol] = {
                        "trades": [],
                        "ob": None,
                        "last_sample_ts": 0
                    }
                    samples[symbol] = []

                # Update State
                if is_trade:
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    price = float(raw.get("trade_price") or event.get("trade_price"))
                    volume = float(raw.get("trade_volume") or event.get("trade_volume"))
                    side = raw.get("ask_bid") # 'ASK' (buy), 'BID' (sell)
                    
                    market_data[symbol]["trades"].append({
                        "ts": ts, "price": price, "vol": volume, "side": side
                    })
                    
                    # Keep trades only for last 600s + buffer (for features and future window)
                    # Actually, we need to keep all trades to calculate future MFE easily, 
                    # but to save memory we can prune old trades that are no longer needed for feature calc.
                    # Wait, we need future trades to calculate MFE. 
                    # Let's keep all trades for now, it's only 3 hours.
                    
                elif is_ob:
                    market_data[symbol]["ob"] = raw

                # Sampling logic (approx every 1s)
                current_ts = event.get("received_at")
                if current_ts - market_data[symbol]["last_sample_ts"] >= 1.0:
                    if market_data[symbol]["ob"] and market_data[symbol]["trades"]:
                        sample = calculate_features(market_data[symbol], current_ts)
                        if sample:
                            samples[symbol].append(sample)
                            market_data[symbol]["last_sample_ts"] = current_ts

    except Exception as e:
        print(f"[TrendDiag] Error processing: {e}")
        return

    print("[TrendDiag] Analyzing windows and labeling winners...")
    
    final_results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "input_file": ws_path,
        "summary": {},
        "comparison": {}
    }

    # Labeling and Comparison
    for symbol, s_list in samples.items():
        all_trades = market_data[symbol]["trades"]
        trade_ts = np.array([t["ts"] for t in all_trades])
        trade_prices = np.array([t["price"] for t in all_trades])
        
        for s in s_list:
            start_ts = s["ts"]
            start_price = s["price"]
            
            s["winners"] = {}
            for w in windows:
                end_ts = start_ts + w
                # Find max price in [start_ts, end_ts]
                idx_start = np.searchsorted(trade_ts, start_ts, side='right')
                idx_end = np.searchsorted(trade_ts, end_ts, side='right')
                
                if idx_end > idx_start:
                    window_prices = trade_prices[idx_start:idx_end]
                    max_p = np.max(window_prices)
                    mfe = (max_p - start_price) / start_price * 100.0
                    s["winners"][str(w)] = (mfe >= threshold)
                else:
                    s["winners"][str(w)] = False

    # Aggregate Statistics
    feature_keys = [
        "buy_trade_value_3s", "buy_trade_value_10s", 
        "sell_trade_value_3s", "sell_trade_value_10s",
        "imbalance_3s", "imbalance_10s",
        "spread_pct", "depth_ratio",
        "price_chg_1s", "price_chg_3s", "price_chg_10s"
    ]

    for w in windows:
        w_key = str(w)
        winners_f = {k: [] for k in feature_keys}
        losers_f = {k: [] for k in feature_keys}
        w_count = 0
        total_count = 0
        
        for symbol, s_list in samples.items():
            for s in s_list:
                total_count += 1
                is_win = s["winners"].get(w_key, False)
                if is_win:
                    w_count += 1
                    for k in feature_keys: winners_f[k].append(s[k])
                else:
                    for k in feature_keys: losers_f[k].append(s[k])
        
        if total_count == 0: continue
        
        comparison = {}
        for k in feature_keys:
            w_avg = np.mean(winners_f[k]) if winners_f[k] else 0
            l_avg = np.mean(losers_f[k]) if losers_f[k] else 0
            diff = w_avg - l_avg
            comparison[k] = {
                "winner_avg": float(w_avg),
                "non_winner_avg": float(l_avg),
                "diff": float(diff),
                "importance": float(abs(diff) / (abs(l_avg) + 1e-9)) if l_avg != 0 else 0
            }
            
        final_results["comparison"][w_key] = {
            "winner_count": w_count,
            "winner_rate": float(w_count / total_count * 100.0),
            "total_samples": total_count,
            "metrics": comparison
        }

    # Write Results
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=2)

    generate_summary_txt(final_results, output_txt, windows)
    print(f"[TrendDiag] Done. Reports: {output_json}, {output_txt}")

def calculate_features(data: Dict[str, Any], ts: float) -> Optional[Dict[str, Any]]:
    trades = data["trades"]
    ob = data["ob"]
    if not ob: return None
    
    # Recent trades for price
    if not trades: return None
    current_price = trades[-1]["price"]
    
    # 1. Trade Values and Imbalance - Optimized with reverse iteration
    def get_trade_metrics(lookback: float):
        cutoff = ts - lookback
        buys = 0.0
        sells = 0.0
        for i in range(len(trades)-1, -1, -1):
            t = trades[i]
            if t["ts"] < cutoff:
                break
            if t["side"] == 'ASK': # UPBIT standard: ASK is buy side in trade event
                buys += t["price"] * t["vol"]
            elif t["side"] == 'BID': # BID is sell side
                sells += t["price"] * t["vol"]
        
        total = buys + sells
        imbal = (buys - sells) / total if total > 0 else 0
        return buys, sells, imbal

    b3, s3, i3 = get_trade_metrics(3.0)
    b10, s10, i10 = get_trade_metrics(10.0)
    
    # 2. Spread and Depth
    units = ob.get("orderbook_units", [])
    if not units: return None
    best_ask = float(units[0]["ask_price"])
    best_bid = float(units[0]["bid_price"])
    spread_pct = (best_ask - best_bid) / best_bid * 100.0
    
    # Depth ratio (top 5 levels)
    ask_depth = sum(float(u["ask_size"]) for u in units[:5])
    bid_depth = sum(float(u["bid_size"]) for u in units[:5])
    depth_ratio = bid_depth / ask_depth if ask_depth > 0 else 1.0
    
    # 3. Price Changes - Optimized
    def get_price_chg(lookback: float):
        cutoff = ts - lookback
        past_price = None
        for i in range(len(trades)-1, -1, -1):
            if trades[i]["ts"] <= cutoff:
                past_price = trades[i]["price"]
                break
        
        if past_price is None:
            # If no trade found at cutoff, use the oldest available trade if within reason
            if trades:
                past_price = trades[0]["price"]
            else:
                return 0
                
        return (current_price - past_price) / past_price * 100.0

    c1 = get_price_chg(1.0)
    c3 = get_price_chg(3.0)
    c10 = get_price_chg(10.0)
    
    return {
        "ts": ts,
        "price": current_price,
        "buy_trade_value_3s": b3,
        "buy_trade_value_10s": b10,
        "sell_trade_value_3s": s3,
        "sell_trade_value_10s": s10,
        "imbalance_3s": i3,
        "imbalance_10s": i10,
        "spread_pct": spread_pct,
        "depth_ratio": depth_ratio,
        "price_chg_1s": c1,
        "price_chg_3s": c3,
        "price_chg_10s": c10
    }

def generate_summary_txt(results, output_txt, windows):
    lines = []
    lines.append("====================================================================")
    lines.append("        Short-term Trend Diagnostics Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {results['timestamp']}")
    lines.append(f"대상 로그: {results['input_file']}")
    lines.append("")
    lines.append("※ 이 도구는 설정값을 자동으로 적용하지 않습니다.")
    lines.append("※ 실거래 활성화 기능이 포함되어 있지 않습니다.")
    lines.append("※ Soft Score v1은 초단타용이므로 단기추세(5분+)에는 부적합할 수 있습니다.")
    lines.append("")

    for w in windows:
        w_key = str(w)
        if w_key not in results["comparison"]: continue
        
        comp = results["comparison"][w_key]
        lines.append(f"--- [Window: {w}s] 분석 결과 ---")
        lines.append(f"전체 샘플: {comp['total_samples']}개")
        lines.append(f"Winner (MFE >= 0.20%) 수: {comp['winner_count']}개")
        lines.append(f"Winner 발생률: {comp['winner_rate']:.2f}%")
        lines.append("")
        
        # Sort metrics by importance (diff)
        metrics = comp["metrics"]
        sorted_m = sorted(metrics.items(), key=lambda x: x[1]["importance"], reverse=True)
        
        lines.append("주요 지표 차이 (Winner vs Non-Winner):")
        for k, v in sorted_m[:5]:
            lines.append(f"- {k:20}: W({v['winner_avg']:10.4f}) vs L({v['non_winner_avg']:10.4f}) | Diff: {v['diff']:.4f}")
        lines.append("")

    lines.append("--- 진단 결론 ---")
    w300 = results["comparison"].get("300", {})
    w600 = results["comparison"].get("600", {})
    
    if w300.get("winner_rate", 0) > 1.0:
        lines.append("1. 단기추세 전략 전환 가능성: 높음 (5분 기준 기회 충분)")
    else:
        lines.append("1. 단기추세 전략 전환 가능성: 낮음 (변동성 여전히 부족)")

    best_w = "300s" if w300.get("winner_rate", 0) > w600.get("winner_rate", 0) else "600s"
    lines.append(f"2. 추천 보유 시간: {best_w}")
    
    lines.append("3. 핵심 진입 지표 제안:")
    # Look at 300s top metrics
    top_m = sorted(results["comparison"].get("300", {}).get("metrics", {}).items(), 
                   key=lambda x: x[1]["importance"], reverse=True)
    for k, _ in top_m[:3]:
        lines.append(f"   - {k}")

    lines.append("4. 주의사항:")
    lines.append("   - Soft Score v1 가중치를 그대로 사용하지 마십시오.")
    lines.append("   - 위 핵심 지표를 바탕으로 Soft Score v2 재설계가 필요합니다.")
    lines.append("   - 추가적인 Paper Trading 실험을 통해 실효성을 검증해야 합니다.")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
