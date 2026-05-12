import json
import os
import numpy as np
from collections import defaultdict
from datetime import datetime
import time
from typing import Dict, Any
from . import report_io


def run_reversal_edge_paper_runner(
    candidate_path: str,
    duration_sec: int,
    mode: str,
    output_events: str,
    output_trades: str,
    output_json: str,
    output_txt: str,
):
    from .upbit_ws import (
        normalize_markets,
        build_subscription_message,
        parse_ws_payload,
        get_event_type,
        get_market,
        UPBIT_WS_URL,
        UpbitWsEvent,
    )
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError(
            "websocket-client is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    from .config_loader import load_config

    if not os.path.exists(candidate_path):
        report_io.write_json_report(output_json, {"ok": False, "reason": "Missing candidate file."})
        return

    with open(candidate_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    weights = cfg.get("weights", {})
    cost_floor = cfg.get("cost_floor_pct", 0.20)
    rev_cond = cfg.get("reversal_conditions", {})
    threshold_list = cfg.get("threshold_candidates", [60, 70, 80])
    threshold = min(threshold_list) if threshold_list else 60

    tp_pct = 0.4
    sl_pct = -0.1
    timeout_sec = 300

    app_cfg = load_config()
    all_markets = app_cfg.get("markets", ["KRW-SOL", "KRW-BTC", "KRW-XRP"])
    if mode == "STATIC_SOL_ONLY":
        active_markets = ["KRW-SOL"]
    else:
        active_markets = list(all_markets)

    normalized_markets = normalize_markets(active_markets)
    subscription_message = build_subscription_message(
        markets=normalized_markets,
        include_trade=True,
        include_orderbook=True,
    )

    market_data: Dict[str, Any] = {}
    for m in normalized_markets:
        market_data[m] = {"trades": [], "ob": None, "last_eval_ts": 0.0}

    positions: Dict[str, Any] = {}
    completed_trades = []

    os.makedirs(os.path.dirname(output_events), exist_ok=True)
    os.makedirs(os.path.dirname(output_trades), exist_ok=True)
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    os.makedirs(os.path.dirname(output_txt), exist_ok=True)

    # Clear output files
    open(output_events, "w").close()
    open(output_trades, "w").close()

    print(f"[Paper] Starting runner for {duration_sec}s in {mode} mode")
    print(f"[Paper] Markets: {normalized_markets}")
    print(f"[Paper] TP={tp_pct}% SL={sl_pct}% Timeout={timeout_sec}s Threshold={threshold}")
    print("[Paper] NOTE: No live orders will be placed. Paper-only simulation.")

    ws = websocket.create_connection(UPBIT_WS_URL, timeout=10)

    try:
        ws.send(json.dumps(subscription_message))
        start_t = time.time()
        last_log_t = start_t

        while True:
            now = time.time()
            if now - start_t >= duration_sec:
                break

            try:
                ws.settimeout(1.0)
                payload = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                print(f"[Paper] WS Error: {e}")
                break

            data = parse_ws_payload(payload)
            event_type = get_event_type(data)
            market = get_market(data)

            event_obj = UpbitWsEvent(
                received_at=now,
                event_type=event_type,
                market=market,
                raw=data,
            )
            event = event_obj.to_dict()

            with open(output_events, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

            symbol = market
            if symbol not in market_data:
                continue

            raw = data
            ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
            ts = ts_ms / 1000.0 if ts_ms else now

            if event_type == "trade":
                price = float(raw.get("trade_price") or 0)
                vol = float(raw.get("trade_volume") or 0)
                side = raw.get("ask_bid")

                market_data[symbol]["trades"].append({
                    "ts": ts, "price": price, "vol": vol, "side": side
                })
                cutoff = ts - 305
                market_data[symbol]["trades"] = [
                    t for t in market_data[symbol]["trades"] if t["ts"] >= cutoff
                ]

                # Check exit for open position
                if symbol in positions:
                    pos = positions[symbol]
                    entry_p = pos["entry_price"]
                    ret = (price - entry_p) / entry_p * 100.0
                    held_sec = ts - pos["entry_ts"]

                    exit_type = None
                    if ret >= tp_pct:
                        exit_type = "TP"
                    elif ret <= sl_pct:
                        exit_type = "SL"
                    elif held_sec >= timeout_sec:
                        exit_type = "TIMEOUT"

                    if exit_type:
                        net_pnl = ret - cost_floor
                        trade_rec = {
                            "market": symbol,
                            "entry_ts": pos["entry_ts"],
                            "exit_ts": ts,
                            "entry_price": entry_p,
                            "exit_price": price,
                            "held_sec": held_sec,
                            "exit_type": exit_type,
                            "gross_pnl_pct": ret,
                            "net_pnl_pct": net_pnl,
                            "score": pos["score"],
                        }
                        completed_trades.append(trade_rec)
                        with open(output_trades, "a", encoding="utf-8") as f:
                            f.write(json.dumps(trade_rec) + "\n")
                        print(f"[Paper] Exit {symbol} {exit_type} | Net PnL: {net_pnl:.4f}%")
                        del positions[symbol]

                # Evaluate entry conditions (no duplicate entry per symbol)
                if symbol not in positions and (ts - market_data[symbol]["last_eval_ts"] >= 1.0):
                    market_data[symbol]["last_eval_ts"] = ts
                    tr = market_data[symbol]["trades"]
                    if len(tr) < 2:
                        continue

                    t_ts = np.array([t["ts"] for t in tr])
                    t_pr = np.array([t["price"] for t in tr])

                    def get_idx(dt):
                        return int(np.searchsorted(t_ts, ts - dt, side="left"))

                    idx_10s = get_idx(10)
                    idx_300s = get_idx(300)

                    pr_10s = t_pr[idx_10s] if idx_10s < len(t_pr) else price
                    pchg_10s = (price - pr_10s) / pr_10s if pr_10s > 0 else 0.0

                    tr_10s = tr[idx_10s:]
                    b10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == "ASK")
                    s10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == "BID")
                    sb_rat_10 = s10 / b10 if b10 > 0 else (s10 / 1000.0)

                    p300 = t_pr[idx_300s:]
                    vol300 = (
                        float(np.std(p300) / np.mean(p300) * 100)
                        if len(p300) > 1 and np.mean(p300) > 0
                        else 0.0
                    )

                    spread = 0.1
                    depth = 1.0
                    ob = market_data[symbol]["ob"]
                    if ob:
                        units = ob.get("orderbook_units", [])
                        if units:
                            ap = float(units[0].get("ask_price", 0))
                            bp = float(units[0].get("bid_price", 0))
                            spread = (ap - bp) / bp * 100.0 if bp > 0 else 0.1
                            bs = sum(float(u.get("bid_size", 0)) for u in units[:5])
                            as_ = sum(float(u.get("ask_size", 0)) for u in units[:5])
                            depth = bs / as_ if as_ > 0 else 1.0

                    # Reversal condition checks
                    ok = True
                    if rev_cond.get("require_negative_price_chg_10s", False):
                        if pchg_10s >= rev_cond.get("max_price_chg_10s", 0.0):
                            ok = False
                    if sb_rat_10 < rev_cond.get("min_sell_buy_ratio_10s", 1.2):
                        ok = False
                    if depth < rev_cond.get("min_bid_ask_depth_ratio_5", 0.8):
                        ok = False
                    if spread > rev_cond.get("max_spread_pct", 0.12):
                        ok = False
                    if vol300 < rev_cond.get("min_volatility_300s_pct", 0.04):
                        ok = False

                    if ok:
                        def scale(v, min_v, max_v):
                            rng = max_v - min_v
                            return float(np.clip((v - min_v) / rng * 100, 0, 100)) if rng != 0 else 0.0

                        neg_pchg_s = scale(pchg_10s, 0.0, -0.01)
                        sp_s = scale(s10, 0.0, 50_000_000.0)
                        sb_rat_s = scale(sb_rat_10, 1.2, 5.0)
                        bid_s = scale(depth, 0.8, 3.0)
                        spread_s = scale(spread, 0.12, 0.02)
                        vol_s = scale(vol300, 0.04, 0.20)
                        ms_s = 50.0

                        w_sum = sum(weights.values())
                        if w_sum > 0:
                            score = (
                                neg_pchg_s * weights.get("negative_price_chg_score", 0)
                                + sp_s * weights.get("sell_pressure_score", 0)
                                + sb_rat_s * weights.get("sell_buy_ratio_score", 0)
                                + bid_s * weights.get("bid_depth_support_score", 0)
                                + spread_s * weights.get("spread_safety_score", 0)
                                + vol_s * weights.get("volatility_score", 0)
                                + ms_s * weights.get("market_sync_score", 0)
                            ) / w_sum
                        else:
                            score = 0.0

                        if score >= threshold:
                            positions[symbol] = {
                                "entry_ts": ts,
                                "entry_price": price,
                                "score": score,
                            }
                            print(f"[Paper] Entry {symbol} at {price} (score: {score:.1f})")

            elif event_type == "orderbook":
                market_data[symbol]["ob"] = raw

            if now - last_log_t >= 60:
                print(f"[Paper] Running... {int(now - start_t)}/{duration_sec}s | Trades: {len(completed_trades)}")
                last_log_t = now

    finally:
        ws.close()

    # Force-close any remaining open positions at end of run
    now = time.time()
    for symbol, pos in list(positions.items()):
        entry_p = pos["entry_price"]
        tr = market_data[symbol]["trades"]
        price = tr[-1]["price"] if tr else entry_p
        ret = (price - entry_p) / entry_p * 100.0
        held_sec = now - pos["entry_ts"]
        net_pnl = ret - cost_floor
        trade_rec = {
            "market": symbol,
            "entry_ts": pos["entry_ts"],
            "exit_ts": now,
            "entry_price": entry_p,
            "exit_price": price,
            "held_sec": held_sec,
            "exit_type": "FORCED",
            "gross_pnl_pct": ret,
            "net_pnl_pct": net_pnl,
            "score": pos["score"],
        }
        completed_trades.append(trade_rec)

    # Build summary
    npnls = [t["net_pnl_pct"] for t in completed_trades]
    gpnls = [t["gross_pnl_pct"] for t in completed_trades]
    tpc = sum(1 for t in completed_trades if t["exit_type"] == "TP")
    slc = sum(1 for t in completed_trades if t["exit_type"] == "SL")
    toc = sum(1 for t in completed_trades if t["exit_type"] == "TIMEOUT")
    foc = sum(1 for t in completed_trades if t["exit_type"] == "FORCED")
    wins = sum(1 for p in npnls if p > 0)

    report = {
        "ok": True,
        "run_time": datetime.now().isoformat(),
        "duration_sec": duration_sec,
        "mode": mode,
        "candidate": candidate_path,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "timeout_sec": timeout_sec,
        "paper_entries": len(completed_trades),
        "tp_count": tpc,
        "sl_count": slc,
        "timeout_count": toc,
        "forced_count": foc,
        "avg_gross_pnl_pct": float(np.mean(gpnls)) if gpnls else 0.0,
        "avg_net_pnl_pct": float(np.mean(npnls)) if npnls else 0.0,
        "win_rate": (wins / len(npnls) * 100.0) if npnls else 0.0,
        "max_loss": float(np.min(npnls)) if npnls else 0.0,
        "live_orders_placed": 0,
    }

    report_io.write_json_report(output_json, report)

    lines = []
    lines.append("====================================================================")
    lines.append("         Reversal Edge v2 Paper Runner Summary")
    lines.append("====================================================================")
    lines.append(f"실행 시간: {report['run_time']}")
    lines.append(f"수집 기간: {duration_sec}초")
    lines.append(f"실행 모드: {mode}")
    lines.append(f"후보 감지 수: {len(completed_trades)}")
    lines.append(f"Paper 진입 수: {len(completed_trades)}")
    lines.append("")
    lines.append(f"TP 청산 수: {tpc} (목표 {tp_pct}%)")
    lines.append(f"SL 청산 수: {slc} (손절 {sl_pct}%)")
    lines.append(f"Timeout 청산 수: {toc} (보유 {timeout_sec}초)")
    lines.append(f"Forced 청산 수: {foc} (종료 시점 강제 청산)")
    lines.append("")
    lines.append(f"평균 Gross PnL: {report['avg_gross_pnl_pct']:.4f}%")
    lines.append(f"평균 Net PnL: {report['avg_net_pnl_pct']:.4f}%")
    lines.append(f"승률(Net 양수): {report['win_rate']:.2f}%")
    lines.append(f"최대 손실(Net): {report['max_loss']:.4f}%")
    lines.append("")
    lines.append("--- [마켓별 결과] ---")
    mc = defaultdict(list)
    for t in completed_trades:
        mc[t["market"]].append(t["net_pnl_pct"])
    for m_sym, pnls in mc.items():
        m_win = sum(1 for p in pnls if p > 0)
        lines.append(
            f"- {m_sym}: {len(pnls)}건 (승률 {m_win/len(pnls)*100:.1f}%, 평균 Net {float(np.mean(pnls)):.4f}%)"
        )
    lines.append("")
    lines.append("--- [안전 경고] ---")
    lines.append("※ 실거래 아님: 본 러너는 실거래 주문을 발생시키지 않는 모의(Paper) 검증용입니다.")
    lines.append("※ config 자동 반영 금지: 검증 결과가 좋더라도 실거래 설정에 자동 덮어쓰기를 하지 않습니다.")

    report_io.write_text_report(output_txt, "\n".join(lines))
    print(f"[Paper] Complete. Text Summary written to {output_txt}")
