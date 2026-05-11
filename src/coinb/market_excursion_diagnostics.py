import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_excursion_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    WebSocket 로그에서 각 마켓의 변동 한계(Excursion)를 분석하여 0.2% 이상의 움직임이 얼마나 발생하는지 진단합니다.
    """
    print(f"[Excursion] Starting diagnostics. WS: {ws_path}")

    market_data: Dict[str, List[float]] = {}
    market_times: Dict[str, List[float]] = {}
    
    try:
        with open(ws_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                try: event = json.loads(line)
                except: continue
                raw = event.get("raw", {})
                if (event.get("event_type") == "trade") or (raw.get("type") == "trade"):
                    symbol = raw.get("code") or event.get("market")
                    if not symbol: continue
                    if symbol not in market_data:
                        market_data[symbol] = []
                        market_times[symbol] = []
                    price = float(raw.get("trade_price") or event.get("trade_price"))
                    ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
                    ts = ts_ms / 1000.0 if ts_ms else event.get("received_at")
                    market_data[symbol].append(price)
                    market_times[symbol].append(ts)
    except Exception as e:
        print(f"[Excursion] Load Error: {e}"); return

    windows = [30, 60, 120, 300, 600]
    thresholds = [0.1, 0.2, 0.3]
    
    results = {}
    for symbol in market_data:
        prices = np.array(market_data[symbol])
        times = np.array(market_times[symbol])
        symbol_results = {w: {t: 0 for t in thresholds} for w in windows}
        total_points = len(prices)
        
        if total_points < 10: continue

        for w in windows:
            for i in range(0, total_points, max(1, total_points // 1000)):
                start_p = prices[i]
                start_t = times[i]
                end_t = start_t + w
                idx_end = np.searchsorted(times, end_t, side='right')
                if idx_end > i:
                    window_prices = prices[i:idx_end]
                    max_excursion = (np.max(window_prices) - start_p) / start_p * 100
                    for t in thresholds:
                        if max_excursion >= t:
                            symbol_results[w][t] += 1
        
        results[symbol] = {
            "total_samples": 1000 if total_points > 1000 else total_points,
            "hits": symbol_results
        }

    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "data": results
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[Excursion] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Market Excursion Analysis Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append("")
    
    for sym, res in out["data"].items():
        lines.append(f"--- [Market: {sym}] (Samples: {res['total_samples']}) ---")
        for w in sorted(res["hits"].keys()):
            h = res["hits"][w]
            p01 = h.get(0.1, 0) / res["total_samples"] * 100
            p02 = h.get(0.2, 0) / res["total_samples"] * 100
            p03 = h.get(0.3, 0) / res["total_samples"] * 100
            lines.append(f"  Window {w:4}s | 0.1% Hit: {p01:6.2f}% | 0.2% Hit: {p02:6.2f}% | 0.3% Hit: {p03:6.2f}%")
        lines.append("")

    lines.append("--- 진단 결론 ---")
    lines.append("1. 0.2% 이상의 움직임이 1% 미만으로 발생하는 구간은 거래 비용(0.2%) 극복이 매우 어렵습니다.")
    lines.append("2. 보유 시간(Window)이 길어질수록 0.2% 돌파 확률이 높아지는지 확인하십시오.")
    report_io.write_text_report(output_txt, "\n".join(lines))
