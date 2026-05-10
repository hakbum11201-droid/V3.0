import json
import os
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any

def run_market_excursion_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    전체 WS 로그를 기반으로 마켓별 가격 움직임(Excursion)을 진단합니다.
    """
    print(f"[MarketExcursion] Starting diagnostics with WS log: {ws_path}")

    if not os.path.exists(ws_path):
        result = {
            "ok": False,
            "reason": f"WebSocket log file not found: {ws_path}"
        }
        print(f"[MarketExcursion] Error: {result['reason']}")
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return

    # 1. Load trade events
    market_trades: Dict[str, List[Dict[str, Any]]] = {}
    
    try:
        with open(ws_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    raw = event.get("raw", {})
                    
                    # Handle both flat and nested (standard in this project) formats
                    is_trade = (event.get("type") == "trade") or (event.get("event_type") == "trade") or (raw.get("type") == "trade")
                    
                    if is_trade:
                        symbol = raw.get("code") or event.get("market") or event.get("code")
                        if not symbol:
                            continue
                        
                        if symbol not in market_trades:
                            market_trades[symbol] = []
                            
                        # Try to get best timestamp
                        # raw["timestamp"] is usually ms
                        ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                        if ts_ms:
                            ts = ts_ms / 1000.0
                        else:
                            ts = event.get("received_at")
                            
                        price = raw.get("trade_price") or event.get("trade_price") or event.get("price")
                        
                        if ts is None or price is None:
                            continue

                        market_trades[symbol].append({
                            "timestamp": float(ts),
                            "price": float(price)
                        })
                except Exception:
                    continue
    except Exception as e:
        print(f"[MarketExcursion] Error reading file: {e}")
        return

    if not market_trades:
        print("[MarketExcursion] No trade events found in log.")
        return

    windows = [30, 60, 120, 180, 300, 600]
    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30]
    
    results = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "input_file": ws_path,
        "markets": {},
        "aggregate": {}
    }

    all_window_stats = {w: [] for w in windows}

    for symbol, trades in market_trades.items():
        print(f"[MarketExcursion] Analyzing {symbol} ({len(trades)} trades)...")
        
        # Sort by timestamp just in case
        trades.sort(key=lambda x: x["timestamp"])
        
        symbol_results = {}
        
        # Extract prices and timestamps for faster lookup
        timestamps = np.array([t["timestamp"] for t in trades])
        prices = np.array([t["price"] for t in trades])
        
        for window in windows:
            mfe_list = []
            mae_list = []
            return_list = []
            
            # Sub-sampling to speed up (every 1 second or so)
            last_processed_ts = 0
            
            for i in range(len(trades)):
                start_ts = timestamps[i]
                
                # Skip if we processed a trade very recently (within 1s) to avoid redundant calculations
                if start_ts - last_processed_ts < 1.0:
                    continue
                
                last_processed_ts = start_ts
                start_price = prices[i]
                end_ts_limit = start_ts + window
                
                # Find trades within window
                # Use searchsorted for speed
                end_idx = np.searchsorted(timestamps, end_ts_limit, side='right')
                
                if end_idx <= i + 1:
                    continue
                    
                window_prices = prices[i+1 : end_idx]
                if len(window_prices) == 0:
                    continue
                
                max_p = np.max(window_prices)
                min_p = np.min(window_prices)
                final_p = window_prices[-1]
                
                mfe = (max_p - start_price) / start_price * 100.0
                mae = (min_p - start_price) / start_price * 100.0
                ret = (final_p - start_price) / start_price * 100.0
                
                mfe_list.append(mfe)
                mae_list.append(mae)
                return_list.append(ret)
                
                all_window_stats[window].append({
                    "mfe": mfe,
                    "mae": mae,
                    "ret": ret
                })

            if not mfe_list:
                continue

            mfe_arr = np.array(mfe_list)
            mae_arr = np.array(mae_list)
            ret_arr = np.array(return_list)
            
            stats = {
                "sample_count": len(mfe_list),
                "mfe_avg": float(np.mean(mfe_arr)),
                "mfe_p50": float(np.percentile(mfe_arr, 50)),
                "mfe_p75": float(np.percentile(mfe_arr, 75)),
                "mfe_p90": float(np.percentile(mfe_arr, 90)),
                "mfe_p95": float(np.percentile(mfe_arr, 95)),
                "mfe_p99": float(np.percentile(mfe_arr, 99)),
                "mfe_max": float(np.max(mfe_arr)),
                "mae_avg": float(np.mean(mae_arr)),
                "ret_avg": float(np.mean(ret_arr)),
                "threshold_counts": {},
                "threshold_rates": {}
            }
            
            for th in thresholds:
                count = int(np.sum(mfe_arr >= th))
                stats["threshold_counts"][f"ge_{th:.2f}"] = count
                stats["threshold_rates"][f"ge_{th:.2f}"] = float(count / len(mfe_list) * 100.0)
                
            symbol_results[str(window)] = stats
            
        results["markets"][symbol] = symbol_results

    # Aggregate calculation
    for window in windows:
        window_data = all_window_stats[window]
        if not window_data:
            continue
            
        mfe_arr = np.array([d["mfe"] for d in window_data])
        mae_arr = np.array([d["mae"] for d in window_data])
        ret_arr = np.array([d["ret"] for d in window_data])
        
        agg_stats = {
            "sample_count": len(window_data),
            "mfe_avg": float(np.mean(mfe_arr)),
            "mfe_p50": float(np.percentile(mfe_arr, 50)),
            "mfe_p75": float(np.percentile(mfe_arr, 75)),
            "mfe_p90": float(np.percentile(mfe_arr, 90)),
            "mfe_p95": float(np.percentile(mfe_arr, 95)),
            "mfe_p99": float(np.percentile(mfe_arr, 99)),
            "mfe_max": float(np.max(mfe_arr)),
            "mae_avg": float(np.mean(mae_arr)),
            "ret_avg": float(np.mean(ret_arr)),
            "threshold_counts": {},
            "threshold_rates": {}
        }
        
        for th in thresholds:
            count = int(np.sum(mfe_arr >= th))
            agg_stats["threshold_counts"][f"ge_{th:.2f}"] = count
            agg_stats["threshold_rates"][f"ge_{th:.2f}"] = float(count / len(window_data) * 100.0)
            
        results["aggregate"][str(window)] = agg_stats

    # Write JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    # Write Summary TXT (Korean)
    generate_summary_txt(results, output_txt, windows, thresholds)
    print(f"[MarketExcursion] Diagnostics complete. Reports: {output_json}, {output_txt}")

def generate_summary_txt(results, output_txt, windows, thresholds):
    lines = []
    lines.append("====================================================================")
    lines.append("         Market Excursion Diagnostics Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {results['timestamp']}")
    lines.append(f"대상 로그: {results['input_file']}")
    lines.append("")
    lines.append("※ 이 도구는 설정값을 자동으로 적용하지 않습니다.")
    lines.append("※ 실거래 활성화 기능이 포함되어 있지 않습니다.")
    lines.append("")

    for window in windows:
        w_key = str(window)
        if w_key not in results["aggregate"]:
            continue
        
        agg = results["aggregate"][w_key]
        lines.append(f"--- [Window: {window}s] 전체 마켓 통합 통계 ---")
        lines.append(f"분석 샘플 수: {agg['sample_count']}")
        lines.append(f"평균 MFE: {agg['mfe_avg']:.4f}%")
        lines.append(f"P90 MFE: {agg['mfe_p90']:.4f}%")
        lines.append(f"P95 MFE: {agg['mfe_p95']:.4f}%")
        lines.append(f"P99 MFE: {agg['mfe_p99']:.4f}%")
        lines.append(f"MAX MFE: {agg['mfe_max']:.4f}%")
        lines.append(f"평균 MAE: {agg['mae_avg']:.4f}%")
        lines.append(f"평균 수익률: {agg['ret_avg']:.4f}%")
        
        rate_020 = agg["threshold_rates"].get("ge_0.20", 0)
        lines.append(f"0.20% 이상 상승 기회 발생률: {rate_020:.2f}%")
        lines.append("")

    lines.append("--- 마켓별 0.20% 기회 발생 빈도 (60s 기준) ---")
    w60 = "60"
    for symbol, market_data in results["markets"].items():
        if w60 in market_data:
            rate = market_data[w60]["threshold_rates"].get("ge_0.20", 0)
            count = market_data[w60]["threshold_counts"].get("ge_0.20", 0)
            lines.append(f"- {symbol}: {rate:.2f}% ({count}회)")
    lines.append("")

    # Conclusion Logic
    lines.append("--- 진단 결론 ---")
    
    # 1. 기회 존재 여부
    has_opportunity = False
    best_market = "None"
    max_rate = -1
    
    for symbol, market_data in results["markets"].items():
        if w60 in market_data:
            rate = market_data[w60]["threshold_rates"].get("ge_0.20", 0)
            if rate > 0.01: # 0.01% 이상이면 존재한다고 판단
                has_opportunity = True
            if rate > max_rate:
                max_rate = rate
                best_market = symbol

    if has_opportunity:
        lines.append(f"1. 0.20% 이상 움직임이 실제로 발생했는가: 예 (최고 {max_rate:.2f}%)")
        lines.append(f"2. 가장 기회가 많았던 마켓: {best_market}")
    else:
        lines.append("1. 0.20% 이상 움직임이 실제로 발생했는가: 아니오 (매우 희소함)")
        lines.append("2. 가장 기회가 많았던 마켓: 없음")

    # 3 & 4. Holding time efficacy
    agg_60 = results["aggregate"].get("60", {})
    agg_300 = results["aggregate"].get("300", {})
    
    rate_60 = agg_60.get("threshold_rates", {}).get("ge_0.20", 0)
    rate_300 = agg_300.get("threshold_rates", {}).get("ge_0.20", 0)
    
    if rate_60 < 0.1:
        lines.append("3. 5~60초 초단타 적합성: 부적합 (수수료 극복 가능한 움직임 부족)")
    else:
        lines.append(f"3. 5~60초 초단타 적합성: 제한적 (기회 발생률 {rate_60:.2f}%)")

    if rate_300 > rate_60 * 1.5:
        lines.append(f"4. 2~10분 보유 구간 기회 변화: 대폭 증가 ({rate_60:.2f}% -> {rate_300:.2f}%)")
    else:
        lines.append(f"4. 2~10분 보유 구간 기회 변화: 미미함 또는 감소")

    lines.append(f"5. 추천 마켓: {best_market}")
    
    # 6. Soft Score v1 실패 원인
    # 만약 시장 자체에 0.20% 기회가 있는데 Winner가 0개였다면 모델이 못 잡은 것.
    # 만약 시장 자체에 0.20% 기회가 거의 없었다면 시장이 조용했던 것.
    if rate_60 < 0.05:
        lines.append("6. Soft Score v1 실패 원인: 시장 변동성 자체가 0.20% 비용을 상회하기에 부족함 (시장 정체)")
    else:
        lines.append("6. Soft Score v1 실패 원인: 시장에 기회는 존재하나 모델이 이를 선별하지 못함 (신호 노이즈)")

    lines.append("7. 다음 전략 방향:")
    if rate_300 > 0.5:
        lines.append("   - 2~5분 보유 단기추세 전략으로의 전환 검토 (보유 시간 확장)")
    elif rate_60 > 0.5:
        lines.append("   - Soft Score v2 재설계 (현재 보유 시간 유지하되 신호 정밀화)")
    else:
        lines.append("   - 현재 마켓/시간대 거래 보류 (변동성 확장 대기)")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
