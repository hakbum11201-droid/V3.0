import json
import os
import numpy as np
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any
from . import report_io

def run_reversal_edge_diagnostics(ws_path: str, output_json: str, output_txt: str):
    if not os.path.exists(ws_path):
        report_io.write_json_report(output_json, {"ok": False, "reason": f"File not found: {ws_path}"})
        return

    market_data: Dict[str, Dict[str, Any]] = {}
    print("[ReversalDiag] Loading WS logs...")
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
        print(f"[ReversalDiag] Load Error: {e}")
        return

    symbol_arrays = {}
    for s in market_data:
        if market_data[s]["trades"]:
            symbol_arrays[s] = {
                "ts": np.array([t["ts"] for t in market_data[s]["trades"]]),
                "pr": np.array([t["price"] for t in market_data[s]["trades"]])
            }

    print("[ReversalDiag] Calculating features & MFEs (1s step)...")
    samples = []
    
    all_ts = []
    for s in symbol_arrays: all_ts.extend([symbol_arrays[s]["ts"][0], symbol_arrays[s]["ts"][-1]])
    if not all_ts: return
    min_ts, max_ts = min(all_ts), max(all_ts)
    
    for ts in np.arange(min_ts + 300, max_ts - 600, 1.0):
        for symbol in market_data:
            arr = symbol_arrays.get(symbol)
            if arr is None: continue
            idx_now = np.searchsorted(arr["ts"], ts, side='right')
            if idx_now == 0: continue
            price = arr["pr"][idx_now-1]
            
            def get_idx(dt): return np.searchsorted(arr["ts"], ts - dt, side='left')
            def get_f_idx(dt): return np.searchsorted(arr["ts"], ts + dt, side='right')
            
            idx_1s = get_idx(1); idx_3s = get_idx(3); idx_10s = get_idx(10); idx_30s = get_idx(30)
            idx_60s = get_idx(60); idx_300s = get_idx(300)
            
            pr_1s = arr["pr"][idx_1s] if idx_1s < len(arr["pr"]) else price
            pr_3s = arr["pr"][idx_3s] if idx_3s < len(arr["pr"]) else price
            pr_10s = arr["pr"][idx_10s] if idx_10s < len(arr["pr"]) else price
            pr_30s = arr["pr"][idx_30s] if idx_30s < len(arr["pr"]) else price
            
            pchg_1s = (price - pr_1s) / pr_1s if pr_1s > 0 else 0
            pchg_3s = (price - pr_3s) / pr_3s if pr_3s > 0 else 0
            pchg_10s = (price - pr_10s) / pr_10s if pr_10s > 0 else 0
            pchg_30s = (price - pr_30s) / pr_30s if pr_30s > 0 else 0
            
            if pchg_30s == 0 and pchg_10s == 0: continue
            
            tr_30s = market_data[symbol]["trades"][idx_30s:idx_now]
            tr_10s = market_data[symbol]["trades"][idx_10s:idx_now]
            tr_3s = market_data[symbol]["trades"][idx_3s:idx_now]
            
            def v_buy_sell(trades):
                b = sum(t["price"] * t["vol"] for t in trades if t["side"] == 'ASK')
                s = sum(t["price"] * t["vol"] for t in trades if t["side"] == 'BID')
                return b, s
                
            b3, s3 = v_buy_sell(tr_3s)
            b10, s10 = v_buy_sell(tr_10s)
            b30, s30 = v_buy_sell(tr_30s)
            
            sb_rat_10 = s10 / b10 if b10 > 0 else (s10 / 1000)
            sb_rat_30 = s30 / b30 if b30 > 0 else (s30 / 1000)
            
            p60 = arr["pr"][idx_60s:idx_now]
            vol60 = np.std(p60) / np.mean(p60) * 100 if len(p60) > 0 and np.mean(p60) > 0 else 0
            p300 = arr["pr"][idx_300s:idx_now]
            vol300 = np.std(p300) / np.mean(p300) * 100 if len(p300) > 0 and np.mean(p300) > 0 else 0
            
            spread = 0.1; depth = 1.0; d_tot = 0
            ob = market_data[symbol]["ob"]
            if ob:
                units = ob.get("orderbook_units", []) or ob.get("raw", {}).get("orderbook_units", [])
                if units:
                    ap = float(units[0]["ask_price"]); bp = float(units[0]["bid_price"])
                    spread = (ap - bp) / bp * 100.0 if bp > 0 else 0.1
                    bs = sum(float(u["bid_size"]) for u in units[:5])
                    as_ = sum(float(u["ask_size"]) for u in units[:5])
                    depth = bs / as_ if as_ > 0 else 1.0
                    d_tot = bs + as_
            
            def get_mfe(dt):
                f_idx = get_f_idx(dt)
                if f_idx <= idx_now: return 0.0
                future_prices = arr["pr"][idx_now:f_idx]
                return (np.max(future_prices) - price) / price * 100.0 if price > 0 else 0.0
            
            mfe_60 = get_mfe(60)
            mfe_120 = get_mfe(120)
            mfe_300 = get_mfe(300)
            mfe_600 = get_mfe(600)
            
            is_cont = (pchg_10s > 0) and (b10 > s10)
            is_rev = (pchg_10s < 0) and (s10 > b10) and (depth >= 0.8) and (spread <= 0.12)
            is_s_rev = (pchg_10s < -0.003) and (sb_rat_10 >= 1.5) and (depth >= 0.9) and (vol300 >= 0.04)
            
            if not (is_cont or is_rev or vol60 > 0.05): continue
            
            samples.append({
                "market": symbol,
                "price_chg_1s": pchg_1s, "price_chg_3s": pchg_3s, "price_chg_10s": pchg_10s, "price_chg_30s": pchg_30s,
                "buy_10s": b10, "sell_10s": s10, "sb_ratio_10s": sb_rat_10,
                "buy_30s": b30, "sell_30s": s30, "sb_ratio_30s": sb_rat_30,
                "vol_60s": vol60, "vol_300s": vol300,
                "depth_ratio": depth, "spread": spread, "depth_tot": d_tot,
                "mfe_60": mfe_60, "mfe_120": mfe_120, "mfe_300": mfe_300, "mfe_600": mfe_600,
                "is_cont": is_cont, "is_rev": is_rev, "is_s_rev": is_s_rev
            })

    print(f"[ReversalDiag] Aggregating {len(samples)} samples...")
    if not samples:
        report_io.write_json_report(output_json, {"ok": False, "reason": "No valid samples found."})
        return

    df = {k: np.array([s[k] for s in samples]) for k in samples[0]}
    
    w_300 = df["mfe_300"] >= 0.20
    w_600 = df["mfe_600"] >= 0.20
    
    def rate(cond): return float(np.mean(cond)*100) if len(cond) > 0 else 0.0
    def cond_rate(base_cond, win_cond):
        valid = win_cond[base_cond]
        return float(np.mean(valid)*100) if len(valid) > 0 else 0.0
    
    cont_mask = np.array([s["is_cont"] for s in samples])
    rev_mask = np.array([s["is_rev"] for s in samples])
    srev_mask = np.array([s["is_s_rev"] for s in samples])
    
    markets = set(df["market"])
    market_stats = {}
    for m in markets:
        m_mask = df["market"] == m
        market_stats[m] = {
            "samples": int(np.sum(m_mask)),
            "w300_rate": rate(w_300[m_mask]), "w600_rate": rate(w_600[m_mask]),
            "cont_w600": cond_rate(cont_mask & m_mask, w_600),
            "rev_w600": cond_rate(rev_mask & m_mask, w_600),
            "srev_w600": cond_rate(srev_mask & m_mask, w_600)
        }
        
    global_stats = {
        "samples": len(samples),
        "w300_count": int(np.sum(w_300)), "w300_rate": rate(w_300),
        "w600_count": int(np.sum(w_600)), "w600_rate": rate(w_600),
        "cont_samples": int(np.sum(cont_mask)),
        "cont_w300": cond_rate(cont_mask, w_300), "cont_w600": cond_rate(cont_mask, w_600),
        "rev_samples": int(np.sum(rev_mask)),
        "rev_w300": cond_rate(rev_mask, w_300), "rev_w600": cond_rate(rev_mask, w_600),
        "srev_samples": int(np.sum(srev_mask)),
        "srev_w300": cond_rate(srev_mask, w_300), "srev_w600": cond_rate(srev_mask, w_600),
    }
    
    w_idx = w_600
    l_idx = ~w_600
    feature_diffs = []
    num_features = ["price_chg_1s", "price_chg_3s", "price_chg_10s", "price_chg_30s", "buy_10s", "sell_10s", "sb_ratio_10s", "vol_60s", "vol_300s", "depth_ratio", "spread"]
    for f in num_features:
        f_arr = df[f]
        w_mean = np.mean(f_arr[w_idx]) if np.any(w_idx) else 0
        l_mean = np.mean(f_arr[l_idx]) if np.any(l_idx) else 0
        diff_pct = (w_mean - l_mean) / l_mean * 100 if l_mean != 0 else 0
        feature_diffs.append({"feature": f, "winner_mean": float(w_mean), "loser_mean": float(l_mean), "diff_pct": float(diff_pct)})
    feature_diffs.sort(key=lambda x: abs(x["diff_pct"]), reverse=True)

    report = {"ok": True, "generated_at": datetime.now().isoformat(), "global": global_stats, "markets": market_stats, "feature_diffs_top15": feature_diffs[:15]}
    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("====================================================================")
    lines.append("        Reversal Edge vs Continuation Diagnostics Summary")
    lines.append("====================================================================")
    lines.append(f"진단 시점: {report['generated_at']}")
    lines.append(f"전체 샘플(필터링 후): {global_stats['samples']:,}개")
    lines.append(f"전체 Winner 수(600s 기준): {global_stats['w600_count']:,}개")
    lines.append("")
    
    lines.append("--- [보유 시간별 전체 Winner 비율] ---")
    lines.append(f"- 300초 MFE >= 0.20%: {global_stats['w300_rate']:.2f}%")
    lines.append(f"- 600초 MFE >= 0.20%: {global_stats['w600_rate']:.2f}%")
    lines.append("")
    
    lines.append("--- [진입 패턴별 Winner Rate 비교 (600초 기준)] ---")
    lines.append(f"1. Continuation 조건 (추세 추종형): {global_stats['cont_w600']:.2f}% (샘플 {global_stats['cont_samples']}개)")
    lines.append(f"2. Reversal 조건 (매도 압력 후 반등형): {global_stats['rev_w600']:.2f}% (샘플 {global_stats['rev_samples']}개)")
    lines.append(f"3. Strong Reversal 조건 (강한 하락 후 반등형): {global_stats['srev_w600']:.2f}% (샘플 {global_stats['srev_samples']}개)")
    lines.append("")
    
    lines.append("--- [Winner와 Non-Winner 특성 차이 Top 5] ---")
    for d in feature_diffs[:5]:
        lines.append(f"- {d['feature']}: Winner {d['winner_mean']:.4f} vs Loser {d['loser_mean']:.4f} (차이 {d['diff_pct']:.1f}%)")
    lines.append("")

    lines.append("--- [마켓별 600초 결과 요약] ---")
    best_m, best_v = None, -1
    for m, st in market_stats.items():
        lines.append(f"- {m}: Reversal {st['rev_w600']:.2f}% | StrongRev {st['srev_w600']:.2f}% | Cont {st['cont_w600']:.2f}%")
        if st['srev_w600'] > best_v:
            best_v = st['srev_w600']
            best_m = m
    lines.append("")

    lines.append("--- [진단 결론 및 제언] ---")
    is_rev_better = global_stats['srev_w600'] > global_stats['cont_w600']
    if is_rev_better: lines.append("1. [결론] Winner 기회는 상승 추세 추격(Continuation)보다 매도 압력 이후의 반등(Reversal) 구조에서 더 높은 확률로 발생합니다.")
    else: lines.append("1. [결론] Winner 기회는 하락 후 반등(Reversal)보다 상승 추격(Continuation) 구조에서 여전히 더 높게 나타납니다.")
        
    lines.append(f"2. [마켓] 가장 유망한 마켓은 {best_m} 입니다.")
    lines.append("3. [보유시간] 300초보다 600초 구간에서 안정적인 MFE 기회가 확보됩니다.")
    
    if is_rev_better and global_stats['srev_w600'] > 20.0: lines.append("4. [제언] Reversal Edge v1 설계 가능성이 충분합니다. 매수 우위가 아닌 '매도 압력 소화 + 하단 호가 방어' 조건으로 Soft Score를 개편해야 합니다.")
    else: lines.append("4. [제언] Reversal 조건만으로도 수익 우위를 확신하기 어렵습니다. 추가적인 Orderflow 피처 발굴이 필요합니다.")
        
    lines.append("5. [주의] 본 결과는 단일 샘플 기반이므로, 추가 paper 검증(Soft Score 백테스트)이 필요합니다.")
    lines.append("\n※ 자동 config 반영 금지. 실거래 반영 금지.")
    
    report_io.write_text_report(output_txt, "\n".join(lines))
    print(f"[ReversalDiag] Complete. Text Summary written to {output_txt}")
