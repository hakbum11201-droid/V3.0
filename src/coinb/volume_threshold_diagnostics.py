import json
import os
import argparse
from datetime import datetime
from collections import deque, defaultdict

def calculate_percentiles(values):
    if not values:
        return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "p95", "p99", "max"]}
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    def get_p(p):
        idx = int(n * p / 100)
        return sorted_vals[min(idx, n - 1)]

    return {
        "count": n,
        "mean": sum(values) / n,
        "p50": get_p(50),
        "p75": get_p(75),
        "p90": get_p(90),
        "p95": get_p(95),
        "p99": get_p(99),
        "max": sorted_vals[-1]
    }

def run_diagnostics(ws_path, output_json, output_txt):
    if not os.path.exists(ws_path):
        result = {"ok": False, "reason": f"File not found: {ws_path}"}
        print(json.dumps(result))
        return result

    trades_by_market = defaultdict(list)
    
    try:
        with open(ws_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("event_type") == "trade":
                        market = data.get("market")
                        raw = data.get("raw", {})
                        
                        ts = raw.get("trade_timestamp")
                        if ts is None:
                            continue
                        
                        # Upbit timestamp is in ms
                        ts_sec = ts / 1000.0
                        
                        price = raw.get("trade_price", 0)
                        volume = raw.get("trade_volume", 0)
                        value = price * volume
                        
                        side = raw.get("ask_bid") or raw.get("side")
                        is_buy = side == "BID"
                        
                        trades_by_market[market].append({
                            "ts": ts_sec,
                            "value": value,
                            "is_buy": is_buy
                        })
                except Exception:
                    continue
    except Exception as e:
        result = {"ok": False, "reason": str(e)}
        print(json.dumps(result))
        return result

    if not trades_by_market:
        result = {"ok": False, "reason": "No trade events found"}
        print(json.dumps(result))
        return result

    market_stats = {}
    all_3s_buy_values = []
    all_10s_buy_values = []

    thresholds = {
        "conservative": 3000000,
        "moderate": 1500000,
        "aggressive": 750000
    }

    for market, trades in trades_by_market.items():
        # Sort trades by timestamp just in case
        trades.sort(key=lambda x: x["ts"])
        
        buy_values_3s = []
        buy_values_10s = []
        
        # Sliding window using two pointers or deques
        window_3s = deque()
        sum_3s = 0.0
        
        window_10s = deque()
        sum_10s = 0.0
        
        for trade in trades:
            ts = trade["ts"]
            val = trade["value"]
            is_buy = trade["is_buy"]
            
            # Add current trade if it's a buy (for the sum)
            # But the rolling sum should be calculated at each trade event point
            # regardless of whether it's buy or sell, to see the "current state"
            
            if is_buy:
                window_3s.append((ts, val))
                sum_3s += val
                window_10s.append((ts, val))
                sum_10s += val
            
            # Remove old trades from 3s window
            while window_3s and window_3s[0][0] < ts - 3:
                sum_3s -= window_3s.popleft()[1]
                
            # Remove old trades from 10s window
            while window_10s and window_10s[0][0] < ts - 10:
                sum_10s -= window_10s.popleft()[1]
            
            # Record the state at this trade event
            # Ensure sums don't go negative due to float precision
            current_sum_3s = max(0, sum_3s)
            current_sum_10s = max(0, sum_10s)
            
            buy_values_3s.append(current_sum_3s)
            buy_values_10s.append(current_sum_10s)
            
            all_3s_buy_values.append(current_sum_3s)
            all_10s_buy_values.append(current_sum_10s)

        dist_3s = calculate_percentiles(buy_values_3s)
        dist_10s = calculate_percentiles(buy_values_10s)
        
        def calc_pass_rates(vals):
            rates = {}
            total = len(vals)
            if total == 0:
                return {k: 0 for k in thresholds}
            for k, threshold in thresholds.items():
                passed = sum(1 for v in vals if v >= threshold)
                rates[k] = (passed / total) * 100
            return rates

        market_stats[market] = {
            "buy_trade_value_3s": dist_3s,
            "buy_trade_value_10s": dist_10s,
            "pass_rates_3s": calc_pass_rates(buy_values_3s),
            "pass_rates_10s": calc_pass_rates(buy_values_10s)
        }

    # Global stats
    global_dist_3s = calculate_percentiles(all_3s_buy_values)
    global_dist_10s = calculate_percentiles(all_10s_buy_values)
    
    def calc_global_pass_rates(vals):
        rates = {}
        total = len(vals)
        if total == 0:
            return {k: 0 for k in thresholds}
        for k, threshold in thresholds.items():
            passed = sum(1 for v in vals if v >= threshold)
            rates[k] = (passed / total) * 100
        return rates

    global_stats = {
        "buy_trade_value_3s": global_dist_3s,
        "buy_trade_value_10s": global_dist_10s,
        "pass_rates_3s": calc_global_pass_rates(all_3s_buy_values),
        "pass_rates_10s": calc_global_pass_rates(all_10s_buy_values)
    }

    full_report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "source_ws": ws_path,
        "thresholds": thresholds,
        "global": global_stats,
        "markets": market_stats
    }

    # Save JSON
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    # Save TXT (Korean)
    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== 체결대금 임계값 진단 리포트 ===\n")
        f.write(f"분석 일시: {full_report['generated_at']}\n")
        f.write(f"대상 로그: {ws_path}\n\n")
        
        f.write("--- 전체 마켓 통합 분포 (3초 Buy Trade Value) ---\n")
        g3 = global_stats["buy_trade_value_3s"]
        f.write(f"샘플 수: {g3['count']}\n")
        f.write(f"평균: {g3['mean']:,.0f}\n")
        f.write(f"P50: {g3['p50']:,.0f}\n")
        f.write(f"P90: {g3['p90']:,.0f}\n")
        f.write(f"P95: {g3['p95']:,.0f}\n")
        f.write(f"P99: {g3['p99']:,.0f}\n")
        f.write(f"MAX: {g3['max']:,.0f}\n\n")
        
        f.write("--- 임계값별 통과율 (통합) ---\n")
        pr3 = global_stats["pass_rates_3s"]
        f.write(f"Conservative (3,000,000): {pr3['conservative']:.2f}%\n")
        f.write(f"Moderate     (1,500,000): {pr3['moderate']:.2f}%\n")
        f.write(f"Aggressive   (  750,000): {pr3['aggressive']:.2f}%\n\n")
        
        f.write("--- 마켓별 요약 (3초 통과율) ---\n")
        for m, stats in market_stats.items():
            rate = stats["pass_rates_3s"]["moderate"]
            f.write(f"- {m}: {rate:.2f}% (Moderate 기준)\n")
            
        f.write("\n--- 진단 결론 ---\n")
        f.write("1. 현재 설정된 Moderate 기준(1,500,000)은 시장의 평균 체결 강도 대비 관찰이 필요함.\n")
        f.write("2. 통과율이 너무 낮을 경우 진입 기회가 극도로 제한될 수 있으나, 성급한 완화는 위험함.\n")
        f.write("3. Aggressive 기준(750,000)으로의 하향 조정 가능성을 포함하여 데이터 기반의 추가 검토 필요.\n")
        f.write("4. 본 리포트는 진단용이며, 실제 설정 변경은 별도의 실험 과정을 거쳐야 함.\n")

    print(json.dumps({"ok": True, "output_json": output_json, "output_txt": output_txt}))
    return full_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    
    run_diagnostics(args.ws, args.output_json, args.output_txt)
