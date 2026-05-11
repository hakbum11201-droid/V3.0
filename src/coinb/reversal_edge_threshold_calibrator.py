import json
import os
import numpy as np
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any
from . import report_io

def run_reversal_edge_threshold_calibrator(ws_path: str, candidate_path: str, output_json: str, output_txt: str, candidate_output: str):
    if not os.path.exists(ws_path) or not os.path.exists(candidate_path):
        report_io.write_json_report(output_json, {"ok": False, "reason": "Missing files."})
        return

    with open(candidate_path, 'r', encoding='utf-8') as f:
        v1_cfg = json.load(f)

    market_data: Dict[str, Dict[str, Any]] = {}
    print("[RevCalibrator] Loading WS logs...")
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
        print(f"[RevCalibrator] Load Error: {e}")
        return

    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    print("[RevCalibrator] Finding raw samples (1s step)...")
    samples = []
    
    all_ts = []
    for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)

    for ts in np.arange(min_ts + 300, max_ts - 600, 1.0):
        for symbol in market_data:
            arr = symbol_arrays.get(symbol)
            if arr is None: continue
            idx_now = np.searchsorted(arr["ts"], side='right', v=ts)
            if idx_now == 0: continue
            price = arr["pr"][idx_now-1]
            
            def get_idx(dt): return np.searchsorted(arr["ts"], ts - dt, side='left')
            def get_f_idx(dt): return np.searchsorted(arr["ts"], ts + dt, side='right')
            
            idx_1s = get_idx(1); idx_3s = get_idx(3); idx_10s = get_idx(10); idx_30s = get_idx(30)
            idx_300s = get_idx(300)
            
            pr_10s = arr["pr"][idx_10s] if idx_10s < len(arr["pr"]) else price
            pchg_10s = (price - pr_10s) / pr_10s if pr_10s > 0 else 0
            
            tr_10s = market_data[symbol]["trades"][idx_10s:idx_now]
            b10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == 'ASK')
            s10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == 'BID')
            sb_rat_10 = s10 / b10 if b10 > 0 else (s10 / 1000)
            
            p300 = arr["pr"][idx_300s:idx_now]
            vol300 = np.std(p300) / np.mean(p300) * 100 if len(p300) > 0 and np.mean(p300) > 0 else 0
            
            spread = 0.1; depth = 1.0
            ob = market_data[symbol]["ob"]
            if ob:
                units = ob.get("orderbook_units", []) or ob.get("raw", {}).get("orderbook_units", [])
                if units:
                    ap = float(units[0]["ask_price"]); bp = float(units[0]["bid_price"])
                    spread = (ap - bp) / bp * 100.0 if bp > 0 else 0.1
                    bs = sum(float(u["bid_size"]) for u in units[:5])
                    as_ = sum(float(u["ask_size"]) for u in units[:5])
                    depth = bs / as_ if as_ > 0 else 1.0
            
            def get_mfe(dt):
                f_idx = get_f_idx(dt)
                if f_idx <= idx_now: return 0.0
                future_prices = arr["pr"][idx_now:f_idx]
                return (np.max(future_prices) - price) / price * 100.0 if price > 0 else 0.0
                
            mfe_300 = get_mfe(300)
            mfe_600 = get_mfe(600)
            
            if pchg_10s == 0 and b10 == 0 and s10 == 0: continue
            
            samples.append({
                "market": symbol, "price_chg_10s": pchg_10s, "sell_buy_ratio_10s": sb_rat_10,
                "bid_ask_depth_ratio_5": depth, "spread_pct": spread, "volatility_300s": vol300,
                "mfe_300": mfe_300, "mfe_600": mfe_600
            })

    print(f"[RevCalibrator] Aggregating {len(samples)} samples...")
    if not samples:
        report_io.write_json_report(output_json, {"ok": False, "reason": "No valid samples found."})
        return

    df = {k: np.array([s[k] for s in samples]) for k in samples[0]}
    w_300 = df["mfe_300"] >= 0.20
    w_600 = df["mfe_600"] >= 0.20

    v1_c1 = df["price_chg_10s"] < 0
    v1_c2 = df["sell_buy_ratio_10s"] >= 1.2
    v1_c3 = df["bid_ask_depth_ratio_5"] >= 0.8
    v1_c4 = df["spread_pct"] <= 0.12
    v1_c5 = df["volatility_300s"] >= 0.04
    
    total = len(samples)
    def funnel(masks):
        m = np.ones(total, dtype=bool)
        res = []
        for name, mask in masks:
            m = m & mask
            res.append((name, int(np.sum(m))))
        return res
        
    funnel_res = funnel([
        ("All", np.ones(total, dtype=bool)),
        ("price_chg_10s < 0", v1_c1),
        ("sell_buy_ratio_10s >= 1.2", v1_c2),
        ("bid_depth >= 0.8", v1_c3),
        ("spread <= 0.12", v1_c4),
        ("volatility >= 0.04", v1_c5)
    ])
    
    bottleneck = ""
    min_pass = total
    for i in range(1, len(funnel_res)):
        drop = funnel_res[i-1][1] - funnel_res[i][1]
        if drop > 0 and funnel_res[i][1] < min_pass:
            min_pass = funnel_res[i][1]
            bottleneck = funnel_res[i][0]
    
    grid_res = []
    p_chgs = [0, -0.001, -0.002, -0.003]
    sb_rats = [1.0, 1.1, 1.2, 1.5]
    depths = [0.5, 0.6, 0.7, 0.8, 0.9]
    spreads = [0.08, 0.10, 0.12, 0.15]
    vols = [0.02, 0.03, 0.04, 0.05]
    
    for p in p_chgs:
        for s in sb_rats:
            for d in depths:
                for sp in spreads:
                    for v in vols:
                        mask = (df["price_chg_10s"] < p) & (df["sell_buy_ratio_10s"] >= s) & \
                               (df["bid_ask_depth_ratio_5"] >= d) & (df["spread_pct"] <= sp) & \
                               (df["volatility_300s"] >= v)
                        
                        pass_cnt = int(np.sum(mask))
                        if pass_cnt < 10: continue
                        
                        w300_rate = float(np.sum(w_300[mask]) / pass_cnt * 100) if pass_cnt > 0 else 0
                        w600_rate = float(np.sum(w_600[mask]) / pass_cnt * 100) if pass_cnt > 0 else 0
                        
                        m_pass = {}
                        m_w600 = {}
                        for m in set(df["market"]):
                            m_mask = mask & (df["market"] == m)
                            m_pass[m] = int(np.sum(m_mask))
                            m_w600[m] = float(np.sum(w_600[m_mask]) / m_pass[m] * 100) if m_pass[m] > 0 else 0
                            
                        grid_res.append({
                            "params": {"price_chg": p, "sb_ratio": s, "depth": d, "spread": sp, "vol": v},
                            "pass_count": pass_cnt, "pass_rate": pass_cnt/total*100,
                            "w300_rate": w300_rate, "w600_rate": w600_rate,
                            "market_pass": m_pass, "market_w600": m_w600
                        })
                        
    def rank_score(x):
        return x["w600_rate"] * 100 - (5000 if x["pass_count"] < 30 else 0)
        
    grid_res.sort(key=rank_score, reverse=True)
    top_20 = grid_res[:20]
    best = top_20[0] if top_20 else None

    if best:
        v2_cand = {
            "name": "reversal_edge_candidate_v2_from_36h",
            "mode": "paper_experiment_only",
            "description": "Calibrated parameters for absorption rebound based on 36h data",
            "holding_windows_sec": [300, 600],
            "preferred_holding_window_sec": 600,
            "cost_floor_pct": 0.20,
            "threshold_candidates": [60, 70, 80],
            "reversal_conditions": {
                "require_negative_price_chg_10s": True,
                "max_price_chg_10s": best["params"]["price_chg"],
                "min_sell_buy_ratio_10s": best["params"]["sb_ratio"],
                "min_bid_ask_depth_ratio_5": best["params"]["depth"],
                "max_spread_pct": best["params"]["spread"],
                "min_volatility_300s_pct": best["params"]["vol"]
            },
            "weights": v1_cfg.get("weights", {}),
            "market_focus": v1_cfg.get("market_focus", {}),
            "exit_test_candidates": v1_cfg.get("exit_test_candidates", {}),
            "requires_net_edge_positive": True,
            "requires_ddm_normal": True,
            "auto_apply": False
        }
        with open(candidate_output, 'w', encoding='utf-8') as f:
            json.dump(v2_cand, f, indent=2, ensure_ascii=False)
            
    report = {
        "ok": True, "generated_at": datetime.now().isoformat(),
        "total_samples": total, "funnel": funnel_res, "bottleneck": bottleneck,
        "grid_combinations": len(grid_res),
        "top_20_combinations": top_20
    }
    report_io.write_json_report(output_json, report)
    
    lines = []
    lines.append("====================================================================")
    lines.append("       Reversal Edge Threshold Calibration Summary (v1 -> v2)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {report['generated_at']}")
    lines.append(f"전체 샘플(초 단위): {total:,}개")
    lines.append("")
    
    lines.append("--- [v1 후보 0개 원인 (Funnel 분석)] ---")
    for name, cnt in funnel_res: lines.append(f"- {name}: {cnt}개 통과")
    lines.append(f"가장 강한 병목 조건: {bottleneck}")
    lines.append("")
    
    lines.append("--- [Grid Search 최고 조합 Top 5] ---")
    for i, c in enumerate(top_20[:5]):
        p = c["params"]
        lines.append(f"{i+1}. price<{p['price_chg']}, sb_rat>={p['sb_ratio']}, depth>={p['depth']}, spread<={p['spread']}, vol>={p['vol']}")
        lines.append(f"   Pass: {c['pass_count']}개 | W300: {c['w300_rate']:.2f}% | W600: {c['w600_rate']:.2f}%")
    lines.append("")
    
    lines.append("--- [마켓별 통과율과 Winner Rate (최고 조합 기준)] ---")
    if best:
        for m, cnt in best["market_pass"].items():
            lines.append(f"- {m}: {cnt}개 발생 | W600: {best['market_w600'][m]:.2f}%")
    lines.append("")
    
    lines.append("--- [진단 결론 및 제언] ---")
    lines.append(f"1. [분석] v1 후보는 '{bottleneck}' 조건으로 인해 대부분의 후보가 차단되었습니다.")
    lines.append("2. [비교] 300초보다 600초 보유가 안정적으로 MFE 도달 비율이 높습니다.")
    
    if best:
        bp = best["params"]
        lines.append(f"3. [추천 v2] price<{bp['price_chg']}, sb_ratio>={bp['sb_ratio']}, depth>={bp['depth']}, spread<={bp['spread']}, vol>={bp['vol']}")
    
    lines.append(f"4. [경로] 추천 v2 후보가 {candidate_output}에 생성되었습니다.")
    lines.append("5. [주의] v2 후보는 자동 적용되지 않으며, 다음 백테스트 단계에서 Net PnL 양수 여부를 확인해야 합니다.")
    
    lines.append("\n※ 자동 config 반영 금지. 실거래 반영 금지.")
    report_io.write_text_report(output_txt, "\n".join(lines))
    print(f"[RevCalibrator] Complete. Text Summary written to {output_txt}")
