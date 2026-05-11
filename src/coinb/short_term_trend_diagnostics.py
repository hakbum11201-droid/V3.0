import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_short_term_trend_diagnostics(ws_path: str, output_json: str, output_txt: str):
    """
    WebSocket 로그에서 단기 추세 전략의 핵심 지표(Imbalance, Price Change 등)와 수익성 사이의 상관관계를 진단합니다.
    """
    print(f"[TrendDiag] Starting diagnostics. WS: {ws_path}")

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
        print(f"[TrendDiag] Load Error: {e}"); return

    # Analyze samples
    results = []
    for symbol in market_data:
        trades = market_data[symbol]["trades"]
        if len(trades) < 100: continue
        
        prices = np.array([t["price"] for t in trades])
        times = np.array([t["ts"] for t in trades])
        
        for i in range(100, len(trades), max(1, len(trades) // 500)):
            ts = times[i]
            p = prices[i]
            
            # 10s Window Indicators
            idx_10s = np.searchsorted(times, ts - 10, side='left')
            p_10s = (p - prices[idx_10s]) / prices[idx_10s] * 100
            
            t_10s = trades[idx_10s:i]
            v_buy = sum(t["vol"] for t in t_10s if t["side"] == 'ASK')
            v_tot = sum(t["vol"] for t in t_10s)
            imb_10s = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
            
            # 300s/600s Outcome
            idx_300s = np.searchsorted(times, ts + 300, side='right')
            mfe_300s = (np.max(prices[i:idx_300s]) - p) / p * 100 if idx_300s > i else 0
            
            idx_600s = np.searchsorted(times, ts + 600, side='right')
            mfe_600s = (np.max(prices[i:idx_600s]) - p) / p * 100 if idx_600s > i else 0
            
            results.append({
                "imb_10s": imb_10s, "p_10s": p_10s, "mfe_300s": mfe_300s, "mfe_600s": mfe_600s
            })

    # Summary
    if not results: return
    
    winners_300s = [r for r in results if r["mfe_300s"] >= 0.20]
    winners_600s = [r for r in results if r["mfe_600s"] >= 0.20]
    
    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(results),
        "winners_300s": len(winners_300s),
        "winners_600s": len(winners_600s),
        "avg_imb_winner_300s": float(np.mean([r["imb_10s"] for r in winners_300s])) if winners_300s else 0,
        "avg_p10s_winner_300s": float(np.mean([r["p_10s"] for r in winners_300s])) if winners_300s else 0
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[TrendDiag] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Short-Term Trend Analysis Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append(f"전체 샘플 수: {out['total_samples']}")
    lines.append("")
    lines.append(f"300s Winner (>=0.20%): {out['winners_300s']} ({out['winners_300s']/out['total_samples']*100:6.2f}%)")
    lines.append(f"600s Winner (>=0.20%): {out['winners_600s']} ({out['winners_600s']/out['total_samples']*100:6.2f}%)")
    lines.append("")
    lines.append(f"Winner Avg Imbalance (10s): {out['avg_imb_winner_300s']:8.4f}")
    lines.append(f"Winner Avg Price Chg (10s): {out['avg_p10s_winner_300s']:8.4f}")
    lines.append("")
    lines.append("--- 진단 결론 ---")
    lines.append("1. Winner 집단의 지표가 전체 평균보다 유의미하게 높은지 확인하십시오.")
    lines.append("2. 300초보다 600초 보유 시 Winner 확률이 높아지는지 확인하십시오.")
    report_io.write_text_report(output_txt, "\n".join(lines))
