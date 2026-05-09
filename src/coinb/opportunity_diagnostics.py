import json
import os
import argparse
from datetime import datetime
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional

# Helper functions similar to microstructure.py for consistency
def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def _trade_price(event: Dict[str, Any]) -> float:
    raw = event.get("raw", {})
    return _to_float(raw.get("trade_price", raw.get("tp", 0.0)))

def _trade_volume(event: Dict[str, Any]) -> float:
    raw = event.get("raw", {})
    return _to_float(raw.get("trade_volume", raw.get("tv", 0.0)))

def _trade_side(event: Dict[str, Any]) -> str:
    raw = event.get("raw", {})
    return str(raw.get("ask_bid", raw.get("ab", ""))).upper()

def _orderbook_units(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = event.get("raw", {})
    units = raw.get("orderbook_units", raw.get("obu", []))
    return units if isinstance(units, list) else []

def _best_bid_ask(event: Dict[str, Any]) -> tuple[float, float]:
    units = _orderbook_units(event)
    if not units:
        return 0.0, 0.0
    first = units[0]
    return _to_float(first.get("bid_price", first.get("bp", 0.0))), _to_float(first.get("ask_price", first.get("ap", 0.0)))

def _depth_krw(event: Dict[str, Any], levels: int = 5) -> tuple[float, float]:
    units = _orderbook_units(event)[:levels]
    bid_depth = 0.0
    ask_depth = 0.0
    for unit in units:
        bp = _to_float(unit.get("bid_price", unit.get("bp", 0.0)))
        bs = _to_float(unit.get("bid_size", unit.get("bs", 0.0)))
        ap = _to_float(unit.get("ask_price", unit.get("ap", 0.0)))
        as_ = _to_float(unit.get("ask_size", unit.get("as", 0.0)))
        bid_depth += bp * bs
        ask_depth += ap * as_
    return bid_depth, ask_depth

def _spread_pct(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0: return 0.0
    mid = (bid + ask) / 2.0
    return ((ask - bid) / mid) * 100.0 if mid > 0 else 0.0

def _clamp(v, low, high):
    return max(low, min(high, v))

# Simplified score calculators for diagnostics
def estimate_ofi_score(imbalance_3s, buy_value_3s, ratio_5):
    score = 0.0
    score += _clamp((imbalance_3s - 1.0) * 30.0, 0.0, 45.0)
    score += _clamp(buy_value_3s / 10_000_000.0 * 10.0, 0.0, 30.0)
    score += _clamp((ratio_5 - 1.0) * 20.0, 0.0, 25.0)
    return _clamp(score, 0.0, 100.0)

def run_opportunity_diagnostics(ws_path, config_path, output_json, output_txt):
    if not os.path.exists(ws_path):
        return {"ok": False, "reason": f"WS file not found: {ws_path}"}
    if not os.path.exists(config_path):
        return {"ok": False, "reason": f"Config file not found: {config_path}"}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return {"ok": False, "reason": f"Failed to load config: {e}"}

    ms_cfg = cfg.get("microstructure", {})
    strat_cfg = cfg.get("strategy", {})
    
    # Thresholds with fallbacks
    min_val_3s = ms_cfg.get("min_trade_value_3s", 1500000)
    max_spread = ms_cfg.get("max_spread_pct", 0.2)
    min_ratio_5 = ms_cfg.get("bid_ask_depth_ratio_min", 1.5)
    min_cont_score = strat_cfg.get("min_continuation_score", 60)
    
    using_fallbacks = []
    if "min_trade_value_3s" not in ms_cfg: using_fallbacks.append("min_trade_value_3s")
    if "max_spread_pct" not in ms_cfg: using_fallbacks.append("max_spread_pct")
    if "bid_ask_depth_ratio_min" not in ms_cfg: using_fallbacks.append("bid_ask_depth_ratio_min")
    if "min_continuation_score" not in strat_cfg: using_fallbacks.append("min_continuation_score")

    events_by_market = defaultdict(list)
    try:
        with open(ws_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    m = data.get("market")
                    if m: events_by_market[m].append(data)
                except: continue
    except Exception as e:
        return {"ok": False, "reason": f"Failed to read WS: {e}"}

    market_reports = {}
    total_samples = 0
    total_all_pass = 0
    gate_stats_global = defaultdict(int)

    for market, events in events_by_market.items():
        events.sort(key=lambda x: _to_float(x.get("received_at", 0.0)))
        if not events: continue
        
        start_ts = int(_to_float(events[0].get("received_at")))
        end_ts = int(_to_float(events[-1].get("received_at")))
        
        trades = [e for e in events if e.get("event_type") == "trade"]
        orderbooks = [e for e in events if e.get("event_type") == "orderbook"]
        
        if not trades or not orderbooks: continue
        
        samples = []
        market_all_pass = 0
        market_gate_stats = defaultdict(int)
        
        # 1-second interval analysis
        for t in range(start_ts + 10, end_ts + 1):
            # Window data
            w_trades_10s = [tr for tr in trades if t - 10 <= _to_float(tr.get("received_at")) <= t]
            w_trades_3s = [tr for tr in w_trades_10s if t - 3 <= _to_float(tr.get("received_at")) <= t]
            
            # Latest orderbook at or before t
            cur_ob = None
            for ob in reversed(orderbooks):
                if _to_float(ob.get("received_at")) <= t:
                    cur_ob = ob
                    break
            if not cur_ob: continue
            
            # Calc features
            buy_3s = sum(_trade_price(tr) * _trade_volume(tr) for tr in w_trades_3s if _trade_side(tr) == "BID")
            sell_3s = sum(_trade_price(tr) * _trade_volume(tr) for tr in w_trades_3s if _trade_side(tr) == "ASK")
            bid_5, ask_5 = _depth_krw(cur_ob, 5)
            bid, ask = _best_bid_ask(cur_ob)
            
            spread = _spread_pct(bid, ask)
            ratio_5 = (bid_5 / ask_5) if ask_5 > 0 else (bid_5 if bid_5 > 0 else 0)
            imbalance_3s = (buy_3s / sell_3s) if sell_3s > 0 else (buy_3s if buy_3s > 0 else 0)
            
            # Scores (Simplified)
            ofi = estimate_ofi_score(imbalance_3s, buy_3s, ratio_5)
            cont = ofi * 0.7 # Placeholder for complex logic, mostly OFI driven in diagnostics
            
            # Gates
            v_pass = buy_3s >= min_val_3s
            s_pass = spread <= max_spread
            i_pass = ratio_5 >= min_ratio_5
            o_pass = cont >= min_cont_score
            
            all_pass = v_pass and s_pass and i_pass and o_pass
            
            if v_pass: market_gate_stats["volume_pass"] += 1
            if s_pass: market_gate_stats["spread_pass"] += 1
            if i_pass: market_gate_stats["imbalance_pass"] += 1
            if o_pass: market_gate_stats["orderflow_pass"] += 1
            if all_pass: market_all_pass += 1
            
            samples.append({
                "t": t,
                "all_pass": all_pass,
                "buy_3s": buy_3s,
                "spread": spread,
                "ratio_5": ratio_5,
                "cont_score": cont
            })

        sample_count = len(samples)
        if sample_count > 0:
            market_reports[market] = {
                "sample_count": sample_count,
                "all_pass_count": market_all_pass,
                "all_pass_rate": (market_all_pass / sample_count) * 100,
                "gate_rates": {k: (v / sample_count) * 100 for k, v in market_gate_stats.items()}
            }
            total_samples += sample_count
            total_all_pass += market_all_pass
            for k, v in market_gate_stats.items(): gate_stats_global[k] += v

    global_report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "using_fallbacks": using_fallbacks,
        "thresholds": {
            "min_trade_value_3s": min_val_3s,
            "max_spread_pct": max_spread,
            "bid_ask_depth_ratio_min": min_ratio_5,
            "min_continuation_score": min_cont_score
        },
        "total_samples": total_samples,
        "total_all_pass": total_all_pass,
        "total_all_pass_rate": (total_all_pass / total_samples * 100) if total_samples > 0 else 0,
        "global_gate_rates": {k: (v / total_samples * 100) if total_samples > 0 else 0 for k, v in gate_stats_global.items()},
        "markets": market_reports
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(global_report, f, indent=2)

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("=== 진입 기회 진단 리포트 (Opportunity Diagnostics) ===\n")
        f.write(f"분석 일시: {global_report['generated_at']}\n")
        f.write(f"대상 로그: {ws_path}\n")
        f.write(f"사용 Config: {config_path}\n\n")
        
        if using_fallbacks:
            f.write(f"[주의] 다음 기준값은 Config에 없어 기본값(fallback)을 사용함: {', '.join(using_fallbacks)}\n\n")
            
        f.write(f"--- 전체 요약 ---\n")
        f.write(f"총 분석 샘플 (1초 단위): {total_samples:,}개\n")
        f.write(f"모든 Gate 통과 횟수: {total_all_pass:,}회\n")
        f.write(f"종합 기회 발생률: {global_report['total_all_pass_rate']:.2f}%\n\n")
        
        f.write(f"--- Gate별 통과율 (병목 분석) ---\n")
        gr = global_report["global_gate_rates"]
        f.write(f"1. Volume Gate  (>= {min_val_3s:,.0f}): {gr.get('volume_pass', 0):.2f}%\n")
        f.write(f"2. Spread Gate  (<= {max_spread:.2f}%): {gr.get('spread_pass', 0):.2f}%\n")
        f.write(f"3. Imbalance Gate (>= {min_ratio_5:.2f}): {gr.get('imbalance_pass', 0):.2f}%\n")
        f.write(f"4. Orderflow Gate (>= {min_cont_score}): {gr.get('orderflow_pass', 0):.2f}%\n\n")
        
        # Bottleneck rank
        sorted_gates = sorted(gr.items(), key=lambda x: x[1])
        f.write(f"가장 강력한 병목: {sorted_gates[0][0].upper()} ({sorted_gates[0][1]:.2f}%만 통과)\n\n")
        
        f.write(f"--- 마켓별 기회 발생률 ---\n")
        for m, r in market_reports.items():
            f.write(f"- {m}: {r['all_pass_rate']:.2f}% (총 {r['all_pass_count']}회)\n")
            
        f.write("\n--- 진단 결론 및 제언 ---\n")
        if total_all_pass > 0:
            f.write(f"1. 30분간 총 {total_all_pass}회의 1초 단위 진입 기회가 있었으나, 30초 스냅샷 방식으로는 대부분 놓쳤을 가능성이 높음.\n")
        else:
            f.write(f"1. 분석 기간 동안 모든 조건을 동시에 만족하는 기회가 1회도 없었음.\n")
            
        f.write("2. 판단 주기를 30초에서 1~5초 내외로 단축하는 것이 거래 집행력 향상에 필수적임.\n")
        f.write("3. 특정 Gate 통과율이 극단적으로 낮다면 해당 임계값의 현실성 재검토 필요.\n")
        f.write("4. 결론: 전략 로직 수정 이전에 '판단 주기(Interval)' 개선에 대한 기술적 검토 필요.\n")

    return global_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-txt", required=True)
    args = parser.parse_args()
    run_opportunity_diagnostics(args.ws, args.config, args.output_json, args.output_txt)
