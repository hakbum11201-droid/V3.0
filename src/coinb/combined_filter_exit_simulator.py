import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
from . import report_io

def run_combined_filter_exit_simulator(ws_path: str, market_factor_path: str, market_focus_path: str, trend_candidate_path: str, output_json: str, output_txt: str):
    print(f"[ExitSim] Starting combined filter exit simulator. WS: {ws_path}")

    if not all(os.path.exists(p) for p in [ws_path, market_factor_path, market_focus_path, trend_candidate_path]):
        result = {"ok": False, "reason": "One or more input files not found."}
        report_io.write_json_report(output_json, result)
        print(f"[ExitSim] Error: {result['reason']}")
        return

    with open(market_factor_path, 'r', encoding='utf-8') as f: m_factor = json.load(f)
    with open(market_focus_path, 'r', encoding='utf-8') as f: m_focus = json.load(f)
    with open(trend_candidate_path, 'r', encoding='utf-8') as f: trend_c = json.load(f)

    mf_cfg = m_factor.get("market_factor_filter", {})
    focus_cfg = m_focus.get("market_focus_filter", {})
    weights = trend_c.get("weights", {})
    cost_floor = trend_c.get("cost_floor_pct", 0.20)

    market_data: Dict[str, Dict[str, Any]] = {}
    print("[ExitSim] Loading WS logs...")
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
        print(f"[ExitSim] Load Error: {e}")
        return

    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    print("[ExitSim] Finding entry candidates (1s step)...")
    modes = ["ALL_MARKETS", "STATIC_SOL_ONLY", "DYNAMIC_LEADER"]
    thresholds = [75, 85, 95, 105]
    candidates = {m: {th: [] for th in thresholds} for m in modes}
    
    all_ts = []
    for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    for ts in np.arange(min_ts + 600, max_ts - 600, 1.0):
        for symbol in market_data:
            factors = calculate_factors_v3(market_data[symbol], symbol_arrays.get(symbol), ts)
            if not factors: continue
            if not pass_market_factor_filter(factors, mf_cfg): continue
            if not pass_market_focus_filter(factors, focus_cfg): continue
            score = calculate_trend_score_v3(factors, weights)
            entry_price = factors["price"]
            
            for mode in modes:
                if mode == "STATIC_SOL_ONLY" and symbol != "KRW-SOL": continue
                for th in thresholds:
                    if score >= th:
                        candidates[mode][th].append((symbol, ts, entry_price))

    print("[ExitSim] Simulating exit paths...")
    timeouts = [300, 600]
    tps = [0.20, 0.25, 0.30, 0.40, 0.50]
    sls = [-0.10, -0.15, -0.20, -0.30]
    
    results_by_combo = {}
    results_by_market = defaultdict(lambda: {"count": 0, "net_pnl_sum": 0, "wins": 0, "tp_hits": 0, "sl_hits": 0, "timeouts": 0})
    
    def sim_exit(symbol, ts, entry_price, timeout, tp, sl):
        arr = symbol_arrays[symbol]
        idx_s = np.searchsorted(arr["ts"], ts, side='right')
        idx_e = np.searchsorted(arr["ts"], ts + timeout, side='right')
        if idx_s == idx_e: return 0, timeout, "TIMEOUT"
        prices = arr["pr"][idx_s:idx_e]
        times = arr["ts"][idx_s:idx_e]
        returns = (prices - entry_price) / entry_price * 100.0
        
        sl_hits = returns <= sl
        tp_hits = returns >= tp
        sl_idx = np.argmax(sl_hits) if np.any(sl_hits) else len(returns)
        tp_idx = np.argmax(tp_hits) if np.any(tp_hits) else len(returns)
        
        if sl_idx == len(returns) and tp_idx == len(returns): return returns[-1], times[-1] - ts, "TIMEOUT"
        if sl_idx <= tp_idx: return returns[sl_idx], times[sl_idx] - ts, "SL"
        else: return returns[tp_idx], times[tp_idx] - ts, "TP"

    for mode in modes:
        for th in thresholds:
            cands = candidates[mode][th]
            if not cands: continue
            
            for timeout in timeouts:
                for tp in tps:
                    for sl in sls:
                        key = f"{mode}_th{th}_w{timeout}_tp{tp}_sl{sl}"
                        count = len(cands)
                        net_pnls, gross_pnls, hold_times = [], [], []
                        tp_count, sl_count, to_count = 0, 0, 0
                        
                        for symbol, ts, entry_price in cands:
                            gross_pnl, hold_time, exit_type = sim_exit(symbol, ts, entry_price, timeout, tp, sl)
                            net_pnl = gross_pnl - cost_floor
                            net_pnls.append(net_pnl)
                            gross_pnls.append(gross_pnl)
                            hold_times.append(hold_time)
                            
                            if exit_type == "TP": tp_count += 1
                            elif exit_type == "SL": sl_count += 1
                            else: to_count += 1
                            
                            results_by_market[symbol]["count"] += 1
                            results_by_market[symbol]["net_pnl_sum"] += net_pnl
                            if net_pnl > 0: results_by_market[symbol]["wins"] += 1
                            if exit_type == "TP": results_by_market[symbol]["tp_hits"] += 1
                            elif exit_type == "SL": results_by_market[symbol]["sl_hits"] += 1
                            else: results_by_market[symbol]["timeouts"] += 1

                        net_pnls = np.array(net_pnls)
                        results_by_combo[key] = {
                            "mode": mode, "threshold": th, "timeout": timeout, "tp": tp, "sl": sl,
                            "candidate_count": count, "avg_gross_pnl_pct": float(np.mean(gross_pnls)), "avg_net_pnl_pct": float(np.mean(net_pnls)),
                            "median_net_pnl_pct": float(np.median(net_pnls)), "win_rate_net_positive": float(np.sum(net_pnls > 0) / count * 100),
                            "tp_hit_count": tp_count, "sl_hit_count": sl_count, "timeout_count": to_count,
                            "tp_hit_rate": tp_count / count * 100, "sl_hit_rate": sl_count / count * 100, "timeout_rate": to_count / count * 100,
                            "avg_holding_seconds": float(np.mean(hold_times)), "max_loss_pct": float(np.min(net_pnls)), "worst_net_pnl_pct": float(np.min(net_pnls)), "best_net_pnl_pct": float(np.max(net_pnls))
                        }

    print("[ExitSim] Generating reports...")
    combos = list(results_by_combo.values())
    top_20_by_avg_net_pnl = sorted(combos, key=lambda x: x["avg_net_pnl_pct"], reverse=True)[:20]
    top_20_by_win_rate = sorted(combos, key=lambda x: x["win_rate_net_positive"], reverse=True)[:20]
    top_20_by_tp_hit_rate = sorted(combos, key=lambda x: x["tp_hit_rate"], reverse=True)[:20]
    
    def balanced_score(c):
        if c["candidate_count"] < 10: return -9999
        return c["avg_net_pnl_pct"] * 100 + c["win_rate_net_positive"] * 0.5 + c["tp_hit_rate"] * 0.5 - c["sl_hit_rate"] * 0.5 - (50 if c["max_loss_pct"] < -2.0 else 0)
        
    top_20_balanced = sorted(combos, key=balanced_score, reverse=True)[:20]
    positive_net = [c for c in combos if c["avg_net_pnl_pct"] > 0]
    
    best_by_mode = {}
    for m in modes:
        m_combos = [c for c in combos if c["mode"] == m and c["candidate_count"] >= 10]
        if m_combos: best_by_mode[m] = sorted(m_combos, key=lambda x: x["avg_net_pnl_pct"], reverse=True)[0]
        
    best_by_timeout = {}
    for w in timeouts:
        w_combos = [c for c in combos if c["timeout"] == w and c["candidate_count"] >= 10]
        if w_combos: best_by_timeout[str(w)] = sorted(w_combos, key=lambda x: x["avg_net_pnl_pct"], reverse=True)[0]

    market_res = {}
    for m, v in results_by_market.items():
        if v["count"] > 0:
            market_res[m] = {"candidate_count": v["count"], "avg_net_pnl_pct": v["net_pnl_sum"] / v["count"], "win_rate": v["wins"] / v["count"] * 100, "tp_hit_rate": v["tp_hits"] / v["count"] * 100, "sl_hit_rate": v["sl_hits"] / v["count"] * 100, "timeout_rate": v["timeouts"] / v["count"] * 100}

    report = {
        "ok": True, "generated_at": datetime.now().isoformat(), "total_combinations": len(combos), "total_candidates": sum(len(c) for mode in candidates for th, c in candidates[mode].items()), "cost_floor_pct": cost_floor,
        "rankings": {"top_20_by_avg_net_pnl": top_20_by_avg_net_pnl, "top_20_by_win_rate": top_20_by_win_rate, "top_20_by_tp_hit_rate": top_20_by_tp_hit_rate, "top_20_balanced": top_20_balanced, "positive_net_pnl_combinations": positive_net, "best_by_mode": best_by_mode, "best_by_timeout": best_by_timeout}, "market_stats": market_res
    }

    report_io.write_json_report(output_json, report)
    
    lines = []
    lines.append("====================================================================")
    lines.append("      Combined Filter Exit Simulator Summary (TP/SL/Timeout)")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {report['generated_at']}")
    lines.append(f"전체 탐색 조합: {len(combos)}개")
    lines.append(f"Net PnL 양수 조합: {len(positive_net)}개")
    lines.append("")
    
    if top_20_by_avg_net_pnl:
        c = top_20_by_avg_net_pnl[0]
        lines.append("--- [최고 Avg Net PnL 조합] ---")
        lines.append(f"Mode: {c['mode']} | Thresh: {c['threshold']} | Timeout: {c['timeout']}s | TP: {c['tp']}% | SL: {c['sl']}%")
        lines.append(f"Avg Net PnL: {c['avg_net_pnl_pct']:.4f}% | Win Rate: {c['win_rate_net_positive']:.2f}% | Count: {c['candidate_count']}")
        lines.append(f"TP Hit: {c['tp_hit_rate']:.2f}% | SL Hit: {c['sl_hit_rate']:.2f}% | TO Hit: {c['timeout_rate']:.2f}%\n")
    
    if top_20_by_win_rate:
        c = top_20_by_win_rate[0]
        lines.append("--- [최고 Win Rate 조합] ---")
        lines.append(f"Mode: {c['mode']} | Thresh: {c['threshold']} | Timeout: {c['timeout']}s | TP: {c['tp']}% | SL: {c['sl']}%")
        lines.append(f"Avg Net PnL: {c['avg_net_pnl_pct']:.4f}% | Win Rate: {c['win_rate_net_positive']:.2f}% | Count: {c['candidate_count']}")
        lines.append(f"TP Hit: {c['tp_hit_rate']:.2f}% | SL Hit: {c['sl_hit_rate']:.2f}% | TO Hit: {c['timeout_rate']:.2f}%\n")
        
    if top_20_balanced:
        c = top_20_balanced[0]
        lines.append("--- [최고 Balanced 조합] ---")
        lines.append(f"Mode: {c['mode']} | Thresh: {c['threshold']} | Timeout: {c['timeout']}s | TP: {c['tp']}% | SL: {c['sl']}%")
        lines.append(f"Avg Net PnL: {c['avg_net_pnl_pct']:.4f}% | Win Rate: {c['win_rate_net_positive']:.2f}% | Count: {c['candidate_count']}")
        lines.append(f"TP Hit: {c['tp_hit_rate']:.2f}% | SL Hit: {c['sl_hit_rate']:.2f}% | TO Hit: {c['timeout_rate']:.2f}%\n")

    lines.append("--- [300초 vs 600초 최고 조합 비교] ---")
    for w in timeouts:
        cw = best_by_timeout.get(str(w))
        if cw: lines.append(f"Timeout {w}s Best: {cw['avg_net_pnl_pct']:.4f}% ({cw['mode']}/th{cw['threshold']}/tp{cw['tp']}/sl{cw['sl']})")
    lines.append("")

    lines.append("--- [모드별 최고 조합 비교] ---")
    for m in modes:
        cm = best_by_mode.get(m)
        if cm: lines.append(f"{m} Best: {cm['avg_net_pnl_pct']:.4f}% (th{cm['threshold']}/w{cm['timeout']}/tp{cm['tp']}/sl{cm['sl']})")
    lines.append("")
    
    lines.append("--- [마켓별 전체 요약 (모든 조합 누적)] ---")
    for m, v in market_res.items():
        lines.append(f"- {m}: Avg Net {v['avg_net_pnl_pct']:.4f}% | Win {v['win_rate']:.2f}% | TP {v['tp_hit_rate']:.2f}% | SL {v['sl_hit_rate']:.2f}%")
    lines.append("")
    
    lines.append("--- [진단 결론 및 제언] ---")
    if len(positive_net) > 0:
        lines.append("1. [성과] TP/SL을 적용했을 때 평균 Net PnL 양수 전환 조합이 존재합니다. 고정 보유 방식 대비 개선 효과가 있습니다.")
        lines.append("2. [결정] 해당 정책은 Paper 전략 실험으로 넘겨 검증해볼 가치가 충분합니다.")
    else:
        lines.append("1. [성과] TP/SL을 적용해도 평균 Net PnL 양수 조합이 존재하지 않습니다. 고정 보유 대비 유의미한 개선이 이루어지지 않았습니다.")
        lines.append("2. [문제] 비용(Cost Floor)을 극복하지 못하는 본질적인 수익성 부족 또는 과도한 수수료/슬리피지 설정이 원인일 수 있습니다.")
        if combos and top_20_by_avg_net_pnl and top_20_by_avg_net_pnl[0]["sl_hit_rate"] > 50:
            lines.append("3. [분석] SL 히트 비율이 매우 높아 손절이 잦은 상황입니다. 진입 타점이 정교하지 않거나 SL이 너무 좁을 수 있습니다.")
        if combos and top_20_by_avg_net_pnl and top_20_by_avg_net_pnl[0]["tp_hit_rate"] < 10:
            lines.append("4. [분석] TP 도달 비율이 낮아 비용 상쇄가 어렵습니다. 이익 실현 구간까지의 모멘텀이 부족합니다.")
        lines.append("5. [결정] Paper 전략 실험으로 넘기는 것은 권장하지 않으며, 필터 및 스코어 공식 자체의 고도화가 필요합니다.")

    lines.append("\n※ 자동 config 반영 금지. 실거래 반영 금지.")
    report_io.write_text_report(output_txt, "\n".join(lines))
    print(f"[ExitSim] Complete. Text Summary written to {output_txt}")

def calculate_factors_v3(data, arr, ts):
    if arr is None: return None
    idx_end = np.searchsorted(arr["ts"], ts, side='right')
    if idx_end == 0: return None
    price = arr["pr"][idx_end-1]
    idx_s300 = np.searchsorted(arr["ts"], ts - 300, side='left')
    if idx_end <= idx_s300: return None
    p300 = arr["pr"][idx_s300:idx_end]
    volat = np.std(p300) / np.mean(p300) * 100.0 if np.mean(p300) != 0 else 0
    rel_t300 = data["trades"][idx_s300:idx_end]
    v_tot = sum(t["price"] * t["vol"] for t in rel_t300)
    v_buy = sum(t["price"] * t["vol"] for t in rel_t300 if t["side"] == 'ASK')
    imb300 = (v_buy - (v_tot - v_buy)) / v_tot if v_tot > 0 else 0
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
    return {"price": price, "volatility_300s": volat, "imbalance_300s": imb300, "imbalance_10s": imb300, "depth_ratio": depth, "spread_pct": spread, "price_chg_10s": p10, "buy_trade_value_10s": v_buy10}

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
    scores = {"imbalance_10s_score": scale(f["imbalance_10s"], -0.5, 0.5), "price_chg_10s_score": scale(f["price_chg_10s"], -0.05, 0.05), "volume_10s_score": scale(f["buy_trade_value_10s"], 0, 10000000), "spread_score": scale(f["spread_pct"], 0.2, 0.02), "depth_score": scale(f["depth_ratio"], 0.5, 2.0), "absorption_score": 50, "continuation_score": 50, "sweep_score": 0}
    w_sum = sum(weights.values())
    return sum(scores[k] * weights.get(k, 0) for k in scores) / w_sum if w_sum > 0 else 0
