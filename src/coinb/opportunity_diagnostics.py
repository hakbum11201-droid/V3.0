import json
import os
import argparse
from datetime import datetime
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional
from . import report_io

def _to_float(v: Any) -> float:
    try: return float(v)
    except: return 0.0

def _trade_price(e): return _to_float(e.get("raw", {}).get("trade_price", e.get("raw", {}).get("tp", 0.0)))
def _trade_volume(e): return _to_float(e.get("raw", {}).get("trade_volume", e.get("raw", {}).get("tv", 0.0)))
def _trade_side(e): return str(e.get("raw", {}).get("ask_bid", e.get("raw", {}).get("ab", ""))).upper()
def _orderbook_units(e): 
    u = e.get("raw", {}).get("orderbook_units", e.get("raw", {}).get("obu", []))
    return u if isinstance(u, list) else []

def _best_bid_ask(e):
    u = _orderbook_units(e)
    if not u: return 0.0, 0.0
    return _to_float(u[0].get("bid_price", u[0].get("bp", 0.0))), _to_float(u[0].get("ask_price", u[0].get("ap", 0.0)))

def _depth_krw(e, levels=5):
    u = _orderbook_units(e)[:levels]
    b_d, a_d = 0.0, 0.0
    for it in u:
        b_d += _to_float(it.get("bid_price", it.get("bp", 0.0))) * _to_float(it.get("bid_size", it.get("bs", 0.0)))
        a_d += _to_float(it.get("ask_price", it.get("ap", 0.0))) * _to_float(it.get("ask_size", it.get("as", 0.0)))
    return b_d, a_d

def _spread_pct(b, a):
    if b <= 0 or a <= 0: return 0.0
    m = (b + a) / 2.0
    return ((a - b) / m) * 100.0 if m > 0 else 0.0

def _clamp(v, l, h): return max(l, min(h, v))
def _pct_change(c, p): return ((c - p) / p) * 100.0 if p > 0 else 0.0

def calc_ofi_score(imb, b_v, r, s_v):
    s = _clamp((imb - 1.0) * 30.0, 0.0, 45.0) + _clamp(b_v / 10_000_000.0 * 10.0, 0.0, 30.0) + _clamp((r - 1.0) * 20.0, 0.0, 25.0)
    return _clamp(s * 0.65 if s_v > b_v else s, 0.0, 100.0)

def calc_sweep_score(p1, p3, b1, b3, spr):
    s = _clamp(p1 * 25.0, 0.0, 25.0) + _clamp(p3 * 15.0, 0.0, 25.0) + _clamp(b1 / 5_000_000.0 * 15.0, 0.0, 20.0) + _clamp(b3 / 20_000_000.0 * 15.0, 0.0, 20.0)
    return _clamp(s * 0.7 if spr > 0.25 else s, 0.0, 100.0)

def calc_absorption_score(s3, p3, r5):
    s = _clamp(s3 / 10_000_000.0 * 20.0, 0.0, 40.0) + (25.0 if p3 >= -0.15 else 0) + _clamp((r5 - 1.0) * 15.0, 0.0, 15.0)
    return _clamp(s, 0.0, 100.0)

def calc_continuation_score(ofi, swp, abs_s, p3, spr):
    s = ofi * 0.35 + swp * 0.35 + abs_s * 0.15 + (10.0 if p3 > 0 else 0) + (5.0 if spr <= 0.15 else (-10.0 if spr > 0.30 else 0))
    return _clamp(s, 0.0, 100.0)

def run_opportunity_diagnostics(ws_path, config_path, output_json, output_txt):
    if not os.path.exists(ws_path) or not os.path.exists(config_path): return {"ok": False}
    with open(config_path, "r", encoding="utf-8") as f: cfg = json.load(f)
    ms_cfg = cfg.get("microstructure", {}); strat_cfg = cfg.get("strategy", {})
    m_v3, m_s, m_r5, m_c = ms_cfg.get("min_trade_value_3s", 1500000), ms_cfg.get("max_spread_pct", 0.2), ms_cfg.get("bid_ask_depth_ratio_min", 1.5), strat_cfg.get("min_continuation_score", 60)
    
    events_m = defaultdict(list)
    with open(ws_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get("market"): events_m[d["market"]].append(d)
            except: continue

    m_reports, t_samples, t_pass = {}, 0, 0
    g_stats = defaultdict(int)

    for market, events in events_m.items():
        events.sort(key=lambda x: _to_float(x.get("received_at", 0.0)))
        trades = [e for e in events if e.get("event_type") == "trade"]
        obs = [e for e in events if e.get("event_type") == "orderbook"]
        if not trades or not obs: continue
        
        start, end = int(_to_float(events[0]["received_at"])), int(_to_float(events[-1]["received_at"]))
        samples, m_pass, m_g = [], 0, defaultdict(int)
        
        for t in range(start + 10, end + 1):
            w10 = [tr for tr in trades if t - 10 <= _to_float(tr["received_at"]) <= t]
            w3 = [tr for tr in w10 if t - 3 <= _to_float(tr["received_at"]) <= t]
            w1 = [tr for tr in w3 if t - 1 <= _to_float(tr["received_at"]) <= t]
            cur_ob = next((ob for ob in reversed(obs) if _to_float(ob["received_at"]) <= t), None)
            if not cur_ob: continue
            
            b3 = sum(_trade_price(tr)*_trade_volume(tr) for tr in w3 if _trade_side(tr)=="BID")
            s3 = sum(_trade_price(tr)*_trade_volume(tr) for tr in w3 if _trade_side(tr)=="ASK")
            b1 = sum(_trade_price(tr)*_trade_volume(tr) for tr in w1 if _trade_side(tr)=="BID")
            p_now, p_1, p_3 = _trade_price(w1[-1]) if w1 else 0, _trade_price(w3[0]) if w3 else 0, _trade_price(w10[0]) if w10 else 0
            b5, a5 = _depth_krw(cur_ob, 5); bid, ask = _best_bid_ask(cur_ob)
            spr, r5 = _spread_pct(bid, ask), b5/a5 if a5>0 else 0
            ofi = calc_ofi_score(b3/s3 if s3>0 else 0, b3, r5, s3)
            swp = calc_sweep_score(_pct_change(p_now, p_1), _pct_change(p_now, p_3), b1, b3, spr)
            abs_s = calc_absorption_score(s3, _pct_change(p_now, p_3), r5)
            cont = calc_continuation_score(ofi, swp, abs_s, _pct_change(p_now, p_3), spr)
            v_p, s_p, i_p, o_p = b3>=m_v3, spr<=m_s, r5>=m_r5, cont>=m_c
            all_p = v_p and s_p and i_p and o_p
            if v_p: m_g["vol"]+=1
            if s_p: m_g["spr"]+=1
            if i_p: m_g["imb"]+=1
            if o_p: m_g["ord"]+=1
            if all_p: m_pass+=1
            samples.append({"market": market, "ts": t, "all_pass": all_p})

        if samples:
            m_reports[market] = {"sample_count": len(samples), "all_pass_count": m_pass, "all_pass_rate": m_pass/len(samples)*100}
            t_samples += len(samples); t_pass += m_pass
            for k, v in m_g.items(): g_stats[k] += v

    report = {"ok": True, "generated_at": datetime.now().isoformat(), "total_samples": t_samples, "total_all_pass": t_pass, "total_all_pass_rate": t_pass/t_samples*100 if t_samples>0 else 0, "markets": m_reports}
    report_io.write_json_report(output_json, report)
    
    lines = []
    lines.append("=== 진입 기회 진단 리포트 (Opportunity Diagnostics) ===")
    lines.append(f"분석 일시: {report['generated_at']} | 대상 로그: {ws_path}")
    lines.append(f"총 샘플: {t_samples:,}개 | 통과 횟수: {t_pass:,}회 | 발생률: {report['total_all_pass_rate']:.2f}%")
    lines.append("\n--- 마켓별 기회 발생률 ---")
    for m, r in m_reports.items(): lines.append(f"- {m}: {r['all_pass_rate']:.2f}% ({r['all_pass_count']}회)")
    lines.append("\n(본 리포트는 진단용이며 설정값 변경은 수동 검토 후 진행하십시오.)")
    report_io.write_text_report(output_txt, "\n".join(lines))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True); parser.add_argument("--config", required=True); parser.add_argument("--output-json", required=True); parser.add_argument("--output-txt", required=True)
    args = parser.parse_args(); run_opportunity_diagnostics(args.ws, args.config, args.output_json, args.output_txt)
