"""
reversal_edge_paper_runner.py
Paper-only simulation runner for Reversal Edge v2.
- No live orders are ever placed.
- Uses Upbit public WebSocket (trade + orderbook) for data.
- Writes events.jsonl, trades.jsonl, and summary reports.
- Guaranteed report generation via finally block.
"""

import json
import os
import uuid
import numpy as np
from collections import defaultdict
from datetime import datetime
import time
from typing import Dict, Any, Optional
from . import report_io

# Orderbook sampling: write raw sample to events.jsonl at most once per N seconds
_OB_SAMPLE_INTERVAL_SEC = 5.0


def _write_line(fh, obj: dict) -> None:
    """Write a JSON line and flush immediately so LastWriteTime stays current."""
    fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    fh.flush()


def _build_report(
    run_id: str,
    run_time: str,
    duration_sec: int,
    mode: str,
    candidate_path: str,
    tp_pct: float,
    sl_pct: float,
    timeout_sec: int,
    completed_trades: list,
    elapsed_sec: float,
    stop_reason: str,
) -> dict:
    npnls = [t["net_pnl_pct"] for t in completed_trades]
    gpnls = [t["gross_pnl_pct"] for t in completed_trades]
    tpc = sum(1 for t in completed_trades if t["exit_type"] == "TP")
    slc = sum(1 for t in completed_trades if t["exit_type"] == "SL")
    toc = sum(1 for t in completed_trades if t["exit_type"] == "TIMEOUT")
    foc = sum(1 for t in completed_trades if t["exit_type"] == "FORCED")
    wins = sum(1 for p in npnls if p > 0)

    return {
        "ok": True,
        "run_id": run_id,
        "run_time": run_time,
        "stop_reason": stop_reason,
        "elapsed_sec": round(elapsed_sec, 1),
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


def _build_text_report(report: dict, completed_trades: list) -> str:
    tp_pct = report["tp_pct"]
    sl_pct = report["sl_pct"]
    timeout_sec = report["timeout_sec"]
    tpc = report["tp_count"]
    slc = report["sl_count"]
    toc = report["timeout_count"]
    foc = report["forced_count"]
    duration_sec = report["duration_sec"]
    mode = report["mode"]
    stop_reason = report["stop_reason"]
    elapsed_sec = report["elapsed_sec"]

    lines = [
        "====================================================================",
        "         Reversal Edge v2 Paper Runner Summary",
        "====================================================================",
        f"Run ID        : {report['run_id']}",
        f"실행 시간     : {report['run_time']}",
        f"목표 실행 기간: {duration_sec}초",
        f"실제 경과     : {elapsed_sec}초",
        f"종료 사유     : {stop_reason}",
        f"실행 모드     : {mode}",
        f"Paper 진입 수 : {len(completed_trades)}",
        "",
        f"TP 청산 수   : {tpc} (목표 {tp_pct}%)",
        f"SL 청산 수   : {slc} (손절 {sl_pct}%)",
        f"Timeout 청산 수: {toc} (보유 {timeout_sec}초)",
        f"Forced 청산 수 : {foc} (종료 시점 강제 청산)",
        "",
        f"평균 Gross PnL : {report['avg_gross_pnl_pct']:.4f}%",
        f"평균 Net PnL   : {report['avg_net_pnl_pct']:.4f}%",
        f"승률(Net 양수) : {report['win_rate']:.2f}%",
        f"최대 손실(Net) : {report['max_loss']:.4f}%",
        "",
        "--- [마켓별 결과] ---",
    ]

    mc = defaultdict(list)
    for t in completed_trades:
        mc[t["market"]].append(t["net_pnl_pct"])
    if mc:
        for m_sym, pnls in mc.items():
            m_win = sum(1 for p in pnls if p > 0)
            lines.append(
                f"- {m_sym}: {len(pnls)}건 "
                f"(승률 {m_win/len(pnls)*100:.1f}%, "
                f"평균 Net {float(np.mean(pnls)):.4f}%)"
            )
    else:
        lines.append("- 진입 없음 (NO_TRADES)")

    lines.extend([
        "",
        "--- [안전 경고] ---",
        "※ 실거래 아님: 본 러너는 실거래 주문을 발생시키지 않는 모의(Paper) 검증용입니다.",
        "※ config 자동 반영 금지: 검증 결과가 좋더라도 실거래 설정에 자동 덮어쓰기를 하지 않습니다.",
    ])
    return "\n".join(lines)


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

    run_id = str(uuid.uuid4())[:8]
    run_time_str = datetime.now().isoformat()
    stop_reason = "UNKNOWN"

    # ------------------------------------------------------------------ setup
    if not os.path.exists(candidate_path):
        report_io.write_json_report(
            output_json, {"ok": False, "reason": "Missing candidate file.", "run_id": run_id}
        )
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
    active_markets = ["KRW-SOL"] if mode == "STATIC_SOL_ONLY" else list(all_markets)

    normalized_markets = normalize_markets(active_markets)
    subscription_message = build_subscription_message(
        markets=normalized_markets,
        include_trade=True,
        include_orderbook=True,
    )

    market_data: Dict[str, Any] = {
        m: {"trades": [], "ob": None, "last_eval_ts": 0.0, "last_ob_logged": 0.0}
        for m in normalized_markets
    }
    positions: Dict[str, Any] = {}
    completed_trades = []
    events_count = 0

    # ------------------------------------------------------------------ dirs
    for p in [output_events, output_trades, output_json, output_txt]:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)

    # Separate summary path under reports/experiments
    exp_dir = "reports/experiments"
    os.makedirs(exp_dir, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_json = os.path.join(exp_dir, f"reversal_edge_v2_paper_run_summary_{ts_tag}.json")
    exp_txt  = os.path.join(exp_dir, f"reversal_edge_v2_paper_run_summary_{ts_tag}.txt")

    # Clear rolling output files
    open(output_events, "w", encoding="utf-8").close()
    open(output_trades, "w", encoding="utf-8").close()

    print(f"[Paper] run_id={run_id}  Starting runner for {duration_sec}s in {mode} mode")
    print(f"[Paper] Markets: {normalized_markets}")
    print(f"[Paper] TP={tp_pct}% SL={sl_pct}% Timeout={timeout_sec}s Threshold={threshold}")
    print("[Paper] NOTE: No live orders will be placed. Paper-only simulation.")
    print(f"[Paper] Final reports will be written to:\n"
          f"         {exp_json}\n         {exp_txt}")

    # ------------------------------------------------------------------ hard deadline
    start_mono = time.monotonic()
    end_mono   = start_mono + duration_sec
    start_wall = time.time()
    last_hb_mono   = start_mono   # heartbeat
    last_log_mono  = start_mono   # console log
    HB_INTERVAL    = 60.0         # heartbeat every 60 s
    LOG_INTERVAL   = 60.0         # console print every 60 s
    WS_RECV_TIMEOUT = 5.0         # ws.recv() timeout (seconds)

    ws: Optional[Any] = None

    # ------------------------------------------------------------------ event log handle (persistent open)
    evt_fh = open(output_events, "a", encoding="utf-8")
    trd_fh = open(output_trades, "a", encoding="utf-8")

    try:
        ws = websocket.create_connection(UPBIT_WS_URL, timeout=10)
        ws.send(json.dumps(subscription_message))

        # ---------------------------------------------------------------- main loop
        while True:
            now_mono = time.monotonic()
            now_wall = time.time()

            # --- Hard deadline check (always at top of loop) ---
            if now_mono >= end_mono:
                stop_reason = "DURATION_COMPLETE"
                break

            # --- Heartbeat ---
            if now_mono - last_hb_mono >= HB_INTERVAL:
                hb = {
                    "event_type": "heartbeat",
                    "run_id": run_id,
                    "elapsed_sec": round(now_mono - start_mono, 1),
                    "remaining_sec": round(end_mono - now_mono, 1),
                    "events_count": events_count,
                    "trades_count": len(completed_trades),
                    "open_positions": list(positions.keys()),
                    "ts": now_wall,
                }
                _write_line(evt_fh, hb)
                last_hb_mono = now_mono

            # --- Console log ---
            if now_mono - last_log_mono >= LOG_INTERVAL:
                elapsed = int(now_mono - start_mono)
                print(f"[Paper] {elapsed}/{duration_sec}s | events={events_count} "
                      f"trades={len(completed_trades)} positions={list(positions.keys())}")
                last_log_mono = now_mono

            # --- Receive from WebSocket with hard timeout ---
            try:
                ws.settimeout(WS_RECV_TIMEOUT)
                payload = ws.recv()
            except websocket.WebSocketTimeoutException:
                # No data for WS_RECV_TIMEOUT seconds; loop back to check deadline
                _write_line(evt_fh, {
                    "event_type": "ws_timeout",
                    "run_id": run_id,
                    "elapsed_sec": round(now_mono - start_mono, 1),
                    "ts": now_wall,
                })
                continue
            except KeyboardInterrupt:
                stop_reason = "KEYBOARD_INTERRUPT"
                break
            except Exception as e:
                print(f"[Paper] WS Error: {e}")
                _write_line(evt_fh, {
                    "event_type": "ws_error",
                    "run_id": run_id,
                    "error": str(e),
                    "ts": now_wall,
                })
                stop_reason = f"WS_ERROR:{e}"
                break

            # --- Parse ---
            try:
                data = parse_ws_payload(payload)
            except Exception as e:
                continue

            event_type = get_event_type(data)
            market     = get_market(data)
            events_count += 1

            # --- Selective event logging ---
            # Always log trade events; orderbook only sampled
            symbol = market
            if symbol in market_data:
                if event_type == "orderbook":
                    last_ob = market_data[symbol]["last_ob_logged"]
                    if now_wall - last_ob >= _OB_SAMPLE_INTERVAL_SEC:
                        evt_obj = UpbitWsEvent(received_at=now_wall, event_type="orderbook_sample",
                                               market=market, raw=data)
                        _write_line(evt_fh, evt_obj.to_dict())
                        market_data[symbol]["last_ob_logged"] = now_wall
                elif event_type == "trade":
                    evt_obj = UpbitWsEvent(received_at=now_wall, event_type=event_type,
                                           market=market, raw=data)
                    _write_line(evt_fh, evt_obj.to_dict())

            # --- Update internal state ---
            if symbol not in market_data:
                continue

            raw = data
            ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
            ts = ts_ms / 1000.0 if ts_ms else now_wall

            if event_type == "trade":
                price = float(raw.get("trade_price") or 0)
                vol   = float(raw.get("trade_volume") or 0)
                side  = raw.get("ask_bid")

                market_data[symbol]["trades"].append({"ts": ts, "price": price, "vol": vol, "side": side})
                cutoff = ts - 305
                market_data[symbol]["trades"] = [t for t in market_data[symbol]["trades"] if t["ts"] >= cutoff]

                # --- Exit check ---
                if symbol in positions:
                    pos     = positions[symbol]
                    entry_p = pos["entry_price"]
                    ret     = (price - entry_p) / entry_p * 100.0
                    held    = ts - pos["entry_ts"]

                    exit_type: Optional[str] = None
                    if ret >= tp_pct:     exit_type = "TP"
                    elif ret <= sl_pct:   exit_type = "SL"
                    elif held >= timeout_sec: exit_type = "TIMEOUT"

                    if exit_type:
                        net_pnl = ret - cost_floor
                        trade_rec = {
                            "run_id": run_id, "market": symbol,
                            "entry_ts": pos["entry_ts"], "exit_ts": ts,
                            "entry_price": entry_p, "exit_price": price,
                            "held_sec": held, "exit_type": exit_type,
                            "gross_pnl_pct": ret, "net_pnl_pct": net_pnl,
                            "score": pos["score"],
                        }
                        completed_trades.append(trade_rec)
                        _write_line(trd_fh, trade_rec)
                        _write_line(evt_fh, {"event_type": "paper_exit", **trade_rec})
                        print(f"[Paper] Exit {symbol} {exit_type} | NetPnL={net_pnl:.4f}%")
                        del positions[symbol]

                # --- Entry evaluation ---
                if symbol not in positions and (ts - market_data[symbol]["last_eval_ts"] >= 1.0):
                    market_data[symbol]["last_eval_ts"] = ts
                    tr = market_data[symbol]["trades"]
                    if len(tr) < 2:
                        continue

                    t_ts = np.array([t["ts"] for t in tr])
                    t_pr = np.array([t["price"] for t in tr])

                    def get_idx(dt):
                        return int(np.searchsorted(t_ts, ts - dt, side="left"))

                    idx_10s  = get_idx(10)
                    idx_300s = get_idx(300)

                    pr_10s   = t_pr[idx_10s] if idx_10s < len(t_pr) else price
                    pchg_10s = (price - pr_10s) / pr_10s if pr_10s > 0 else 0.0

                    tr_10s   = tr[idx_10s:]
                    b10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == "ASK")
                    s10 = sum(t["price"] * t["vol"] for t in tr_10s if t["side"] == "BID")
                    sb_rat_10 = s10 / b10 if b10 > 0 else (s10 / 1000.0)

                    p300   = t_pr[idx_300s:]
                    vol300 = (float(np.std(p300) / np.mean(p300) * 100)
                              if len(p300) > 1 and np.mean(p300) > 0 else 0.0)

                    spread = 0.1; depth = 1.0
                    ob = market_data[symbol]["ob"]
                    if ob:
                        units = ob.get("orderbook_units", [])
                        if units:
                            ap = float(units[0].get("ask_price", 0))
                            bp = float(units[0].get("bid_price", 0))
                            spread = (ap - bp) / bp * 100.0 if bp > 0 else 0.1
                            bs  = sum(float(u.get("bid_size",  0)) for u in units[:5])
                            as_ = sum(float(u.get("ask_size",  0)) for u in units[:5])
                            depth = bs / as_ if as_ > 0 else 1.0

                    # Reversal condition checks (unchanged logic)
                    ok = True
                    if rev_cond.get("require_negative_price_chg_10s", False):
                        if pchg_10s >= rev_cond.get("max_price_chg_10s", 0.0): ok = False
                    if sb_rat_10 < rev_cond.get("min_sell_buy_ratio_10s",  1.2): ok = False
                    if depth     < rev_cond.get("min_bid_ask_depth_ratio_5", 0.8): ok = False
                    if spread    > rev_cond.get("max_spread_pct",           0.12): ok = False
                    if vol300    < rev_cond.get("min_volatility_300s_pct",  0.04): ok = False

                    if ok:
                        def scale(v, min_v, max_v):
                            rng = max_v - min_v
                            return float(np.clip((v - min_v) / rng * 100, 0, 100)) if rng != 0 else 0.0

                        w_sum = sum(weights.values())
                        score = 0.0
                        if w_sum > 0:
                            score = (
                                scale(pchg_10s,   0.0,  -0.01)  * weights.get("negative_price_chg_score", 0)
                                + scale(s10,      0.0, 50_000_000.0) * weights.get("sell_pressure_score",    0)
                                + scale(sb_rat_10, 1.2,  5.0)   * weights.get("sell_buy_ratio_score",    0)
                                + scale(depth,    0.8,  3.0)    * weights.get("bid_depth_support_score", 0)
                                + scale(spread,   0.12, 0.02)   * weights.get("spread_safety_score",     0)
                                + scale(vol300,   0.04, 0.20)   * weights.get("volatility_score",        0)
                                + 50.0                          * weights.get("market_sync_score",        0)
                            ) / w_sum

                        if score >= threshold:
                            positions[symbol] = {
                                "entry_ts": ts, "entry_price": price, "score": score
                            }
                            entry_evt = {
                                "event_type": "paper_entry", "run_id": run_id,
                                "market": symbol, "price": price, "score": score, "ts": ts,
                            }
                            _write_line(evt_fh, entry_evt)
                            print(f"[Paper] Entry {symbol} at {price} (score={score:.1f})")

            elif event_type == "orderbook":
                market_data[symbol]["ob"] = raw

        # end while

    except KeyboardInterrupt:
        stop_reason = "KEYBOARD_INTERRUPT"
    except Exception as e:
        stop_reason = f"EXCEPTION:{e}"
        print(f"[Paper] Unexpected error: {e}")
    finally:
        # ---------------------------------------------------------------- cleanup WS
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

        # ---------------------------------------------------------------- force-close open positions
        now_wall = time.time()
        for symbol, pos in list(positions.items()):
            entry_p = pos["entry_price"]
            tr      = market_data[symbol]["trades"]
            price   = tr[-1]["price"] if tr else entry_p
            ret     = (price - entry_p) / entry_p * 100.0
            net_pnl = ret - cost_floor
            trade_rec = {
                "run_id": run_id, "market": symbol,
                "entry_ts": pos["entry_ts"], "exit_ts": now_wall,
                "entry_price": entry_p, "exit_price": price,
                "held_sec": now_wall - pos["entry_ts"], "exit_type": "FORCED",
                "gross_pnl_pct": ret, "net_pnl_pct": net_pnl, "score": pos["score"],
            }
            completed_trades.append(trade_rec)
            try:
                _write_line(trd_fh, trade_rec)
                _write_line(evt_fh, {"event_type": "paper_exit_forced", **trade_rec})
            except Exception:
                pass

        # ---------------------------------------------------------------- flush & close file handles
        elapsed_sec = time.time() - start_wall
        try:
            _write_line(evt_fh, {
                "event_type": "runner_end",
                "run_id": run_id,
                "stop_reason": stop_reason,
                "elapsed_sec": round(elapsed_sec, 1),
                "events_count": events_count,
                "trades_count": len(completed_trades),
                "ts": time.time(),
            })
            evt_fh.flush()
        except Exception:
            pass
        finally:
            try: evt_fh.close()
            except Exception: pass
            try: trd_fh.close()
            except Exception: pass

        # ---------------------------------------------------------------- build & write reports
        report = _build_report(
            run_id=run_id,
            run_time=run_time_str,
            duration_sec=duration_sec,
            mode=mode,
            candidate_path=candidate_path,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            timeout_sec=timeout_sec,
            completed_trades=completed_trades,
            elapsed_sec=elapsed_sec,
            stop_reason=stop_reason,
        )
        text_report = _build_text_report(report, completed_trades)

        # Write to caller-specified paths
        try:
            report_io.write_json_report(output_json, report)
        except Exception as e:
            print(f"[Paper] WARNING: Failed to write output_json: {e}")
        try:
            report_io.write_text_report(output_txt, text_report)
        except Exception as e:
            print(f"[Paper] WARNING: Failed to write output_txt: {e}")

        # Write canonical summary to reports/experiments (always created)
        try:
            report_io.write_json_report(exp_json, report)
        except Exception as e:
            print(f"[Paper] WARNING: Failed to write exp_json: {e}")
        try:
            report_io.write_text_report(exp_txt, text_report)
        except Exception as e:
            print(f"[Paper] WARNING: Failed to write exp_txt: {e}")

        print(f"\n[Paper] === Run complete ===")
        print(f"[Paper] stop_reason  : {stop_reason}")
        print(f"[Paper] elapsed      : {elapsed_sec:.1f}s")
        print(f"[Paper] events logged: {events_count}")
        print(f"[Paper] trades       : {len(completed_trades)}")
        print(f"[Paper] Summary JSON : {exp_json}")
        print(f"[Paper] Summary TXT  : {exp_txt}")
