import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from . import report_io

def run_market_focus_diagnostics(backtest_json: str, output_json: str, output_txt: str):
    """
    Market Factor Filter를 통과한 후보 중 주도 종목(Market Focus)의 특성을 분석합니다.
    """
    print(f"[FocusDiag] Loading backtest results: {backtest_json}")

    if not os.path.exists(backtest_json):
        result = {"ok": False, "reason": "Backtest file not found."}
        report_io.write_json_report(output_json, result)
        return

    with open(backtest_json, 'r', encoding='utf-8') as f:
        bt_data = json.load(f)

    samples = bt_data.get("samples", [])
    if not samples:
        result = {"ok": False, "reason": "No samples found in backtest results."}
        report_io.write_json_report(output_json, result)
        return

    # Analyze by Symbol
    symbol_stats = {}
    for s in samples:
        sym = s["symbol"]
        if sym not in symbol_stats:
            symbol_stats[sym] = {"count": 0, "net_pnl_sum": 0, "winners": 0}
        
        symbol_stats[sym]["count"] += 1
        symbol_stats[sym]["net_pnl_sum"] += s["net_pnl"]
        if s["mfe"] >= 0.20:
            symbol_stats[sym]["winners"] += 1

    # Analyze Volume Quality (buy_trade_value_10s)
    vol_vals = [s["factors"]["buy_trade_value_10s"] for s in samples]
    vol_q = np.percentile(vol_vals, [25, 50, 75]) if vol_vals else [0, 0, 0]
    
    vol_buckets = {"low": [], "mid": [], "high": [], "overheated": []}
    for s in samples:
        v = s["factors"]["buy_trade_value_10s"]
        if v <= vol_q[0]: vol_buckets["low"].append(s)
        elif v <= vol_q[1]: vol_buckets["mid"].append(s)
        elif v <= vol_q[2]: vol_buckets["high"].append(s)
        else: vol_buckets["overheated"].append(s)

    bucket_stats = {}
    for b, b_samples in vol_buckets.items():
        if b_samples:
            avg_net = np.mean([s["net_pnl"] for s in b_samples])
            wr = sum(1 for s in b_samples if s["mfe"] >= 0.20) / len(b_samples) * 100
            bucket_stats[b] = {"count": len(b_samples), "avg_net_pnl": float(avg_net), "win_rate": float(wr)}

    out = {
        "ok": True, "timestamp": datetime.now().isoformat(),
        "total_samples": len(samples),
        "symbol_stats": symbol_stats,
        "volume_quality_buckets": bucket_stats,
        "volume_percentiles": [float(v) for v in vol_q]
    }
    report_io.write_json_report(output_json, out)
    generate_summary_txt(out, output_txt)
    print(f"[FocusDiag] Done. Reports: {output_json}, {output_txt}")

def generate_summary_txt(out, output_txt):
    lines = []
    lines.append("====================================================================")
    lines.append("          Market Focus Analysis Summary (V3.0)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {out['timestamp']}")
    lines.append(f"분석 대상 후보: {out['total_samples']}개")
    lines.append("")
    
    lines.append("--- [Symbol 집중도 분석] ---")
    for sym, s in out["symbol_stats"].items():
        avg_pnl = s["net_pnl_sum"] / s["count"]
        wr = s["winners"] / s["count"] * 100
        lines.append(f"- {sym:12}: Count {s['count']:4} | Avg Net {avg_pnl:8.4f}% | Win {wr:6.2f}%")
    lines.append("")

    lines.append("--- [Volume Quality (10s Buy Value) 분석] ---")
    p = out["volume_percentiles"]
    lines.append(f"Percentiles: 25%({p[0]:.0f}), 50%({p[1]:.0f}), 75%({p[2]:.0f})")
    for b, s in out["volume_quality_buckets"].items():
        lines.append(f"- {b:12}: Count {s['count']:4} | Avg Net {s['avg_net_pnl']:8.4f}% | Win {s['win_rate']:6.2f}%")
    lines.append("")

    lines.append("--- 진단 결론 ---")
    lines.append("1. 특정 종목(예: KRW-SOL)에 수익 후보가 집중되는지 확인하십시오.")
    lines.append("2. Overheated(상위 25%) 구간에서 수익 확률이 높은지 확인하십시오.")
    lines.append("3. 주의: 본 결과는 3단계 필터링 전략의 'Focus' 기준 수립을 위한 기초 데이터입니다.")
    
    report_io.write_text_report(output_txt, "\n".join(lines))
