"""
discover_cross_market_reversal_features.py
공통 Reversal Feature 탐색 [time_uniform_sampling mode]

변경 내역:
- rowid 간격 샘플링 → 시간 균등 샘플링(6 bands × 1h window)
- 전체 fetchall/풀스캔 금지 유지
- ORDER BY RANDOM() 금지
- unknown 마켓 제외 유지
- 이 결과는 discovery용이며 최종 전략 확정 아님
"""
import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict

# ─── Paths ────────────────────────────────────────────────────────────────────
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "cross_market_feature_discovery_latest.json")
TXT_REPORT  = os.path.join(OUT_DIR, "cross_market_feature_discovery_latest.txt")

# ─── Labeling ─────────────────────────────────────────────────────────────────
TP_300_PCT = 0.20
TP_600_PCT = 0.30
SL_PCT     = -0.20

# ─── Time-uniform sampling config ────────────────────────────────────────────
N_BANDS                    = 6      # timeline divided into this many bands
WINDOW_MINUTES             = 60     # minutes loaded per band
TARGET_SNAPSHOTS_PER_MARKET = 1500
MIN_SNAPSHOTS_PER_MARKET    = 500
STEP_SEC                   = 10.0  # snapshot interval (s)

# ─── Market filter ────────────────────────────────────────────────────────────
SKIP_MARKETS = {"unknown", ""}


def _cohens_d(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0
    v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
    ps = np.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    return (np.mean(a) - np.mean(b)) / ps if ps else 0.0


def get_markets(conn):
    cur = conn.execute(
        "SELECT DISTINCT market FROM events WHERE market IS NOT NULL AND market != ''"
    )
    return [r[0] for r in cur.fetchall()
            if r[0] not in SKIP_MARKETS and r[0].startswith("KRW-")]


def _load_window(conn, market, w_start, w_end):
    """market + ts BETWEEN w_start AND w_end — ts 컬럼 직접 사용."""
    cur = conn.execute(
        "SELECT ts, event_type, raw_json FROM events "
        "WHERE market=? AND ts BETWEEN ? AND ? ORDER BY ts ASC",
        (market, w_start, w_end),
    )
    return cur.fetchall()


def _parse_rows(rows):
    """Parse rows into trade/ob numpy arrays."""
    tr_ts, tr_pr, tr_vol, tr_side = [], [], [], []
    ob_ts, ob_bd, ob_ad, ob_sp   = [], [], [], []

    for (ts_col, etype, raw_str) in rows:
        try:
            ev  = json.loads(raw_str)
            raw = ev.get("raw", {})
            et  = etype or ev.get("event_type") or raw.get("type")

            # Resolve timestamp
            ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
            ts = ts_ms / 1000.0 if ts_ms else ev.get("received_at", ts_col)
            if ts is None:
                continue

            if et == "trade":
                pr = raw.get("trade_price") or ev.get("trade_price")
                vl = raw.get("trade_volume") or ev.get("trade_volume")
                if pr is None or vl is None:
                    continue
                tr_ts.append(float(ts))
                tr_pr.append(float(pr))
                tr_vol.append(float(vl))
                tr_side.append(-1 if raw.get("ask_bid") == "ASK" else 1)

            elif et == "orderbook":
                units = raw.get("orderbook_units", [])
                if not units:
                    continue
                ap = float(units[0]["ask_price"])
                bp = float(units[0]["bid_price"])
                ob_ts.append(float(ts))
                ob_sp.append((ap - bp) / bp * 100 if bp > 0 else 0.0)
                ob_bd.append(sum(float(u["bid_size"]) for u in units[:5]))
                ob_ad.append(sum(float(u["ask_size"]) for u in units[:5]))
        except Exception:
            pass

    if not tr_ts:
        return None

    sort = np.argsort(tr_ts)
    return {
        "t_ts":  np.array(tr_ts)[sort],
        "t_pr":  np.array(tr_pr)[sort],
        "t_vol": np.array(tr_vol)[sort],
        "t_side":np.array(tr_side)[sort],
        "o_ts":  np.array(ob_ts) if ob_ts else np.array([]),
        "o_bd":  np.array(ob_bd) if ob_bd else np.array([]),
        "o_ad":  np.array(ob_ad) if ob_ad else np.array([]),
        "o_sp":  np.array(ob_sp) if ob_sp else np.array([]),
    }


def _snapshots_from_arrays(arrs, snap_budget):
    """Generate labeled snapshots from parsed arrays, up to snap_budget."""
    t_ts  = arrs["t_ts"];  t_pr = arrs["t_pr"]
    t_vol = arrs["t_vol"]; t_side = arrs["t_side"]
    o_ts  = arrs["o_ts"];  o_bd = arrs["o_bd"]
    o_ad  = arrs["o_ad"];  o_sp = arrs["o_sp"]

    def gidx(v): return np.searchsorted(t_ts, v, side="right")
    def oidx(v):
        if len(o_ts) == 0: return -1
        return int(np.searchsorted(o_ts, v, side="right")) - 1

    min_ts = float(t_ts[0]) if len(t_ts) > 0 else 0
    max_ts = float(t_ts[-1]) if len(t_ts) > 0 else 0
    snaps  = []

    for snap_ts in np.arange(min_ts + 60, max_ts - 650, STEP_SEC):
        if len(snaps) >= snap_budget:
            break

        i_curr = gidx(snap_ts)
        if i_curr == 0: continue
        pr_curr = t_pr[i_curr - 1]
        i_10s   = gidx(snap_ts - 10)
        if i_curr == i_10s: continue

        # Label
        pr_300 = t_pr[i_curr : gidx(snap_ts + 300)]
        pr_600 = t_pr[i_curr : gidx(snap_ts + 600)]
        if len(pr_600) == 0: continue

        r300 = (pr_300 - pr_curr) / pr_curr * 100
        r600 = (pr_600 - pr_curr) / pr_curr * 100
        sl_h  = r600 <= SL_PCT
        tp3_h = r300 >= TP_300_PCT
        tp6_h = r600 >= TP_600_PCT
        sl_i  = int(np.argmax(sl_h))  if np.any(sl_h)  else 999999
        tp3_i = int(np.argmax(tp3_h)) if np.any(tp3_h) else 999999
        tp6_i = int(np.argmax(tp6_h)) if np.any(tp6_h) else 999999

        if   sl_i < tp6_i and sl_i < tp3_i:  label = "LOSS"
        elif tp3_i < 999999 and tp3_i < sl_i: label = "WIN_300"
        elif tp6_i < 999999 and tp6_i < sl_i: label = "WIN_600"
        else:                                  label = "TIMEOUT"

        # Features
        i_30s = gidx(snap_ts - 30); i_60s = gidx(snap_ts - 60)
        pr10  = t_pr[i_10s] if i_10s < len(t_pr) else pr_curr
        pr30  = t_pr[i_30s] if i_30s < len(t_pr) else pr_curr
        pr60  = t_pr[i_60s] if i_60s < len(t_pr) else pr_curr

        v10s = t_vol[i_10s:i_curr]; s10s = t_side[i_10s:i_curr]
        v30s = t_vol[i_30s:i_curr]; s30s = t_side[i_30s:i_curr]
        vol10 = float(np.sum(v10s)); vol30 = float(np.sum(v30s))
        sell10 = float(np.sum(v10s[s10s == -1]))
        sell30 = float(np.sum(v30s[s30s == -1]))
        i_5s  = gidx(snap_ts - 5)
        v5s   = t_vol[i_5s:i_curr]; s5s = t_side[i_5s:i_curr]
        buy5  = float(np.sum(v5s[s5s == 1]))
        buy5_10 = float(np.sum(v10s[s10s == 1])) - buy5
        v20s  = t_vol[gidx(snap_ts - 20) : i_10s]

        pr60_arr = t_pr[i_60s:i_curr]
        volat = (float(np.std(pr60_arr) / np.mean(pr60_arr) * 100)
                 if len(pr60_arr) > 1 else 0.0)

        io = oidx(snap_ts); io10 = oidx(snap_ts - 10)
        if io >= 0 and io10 >= 0 and len(o_bd) > 0:
            bdc = o_bd[io]; adc = o_ad[io]; spc = o_sp[io]
            bd10 = o_bd[io10]; ad10 = o_ad[io10]; sp10 = o_sp[io10]
            f_bdc = bdc / (bd10 + 1e-8); f_adc = adc / (ad10 + 1e-8)
            f_sp  = spc; f_spr = spc - sp10
            f_obi = bdc / (bdc + adc + 1e-8)
            f_liq = f_bdc - f_adc
        else:
            f_bdc = f_adc = 1.0; f_sp = f_spr = 0.0
            f_obi = 0.5; f_liq = 0.0

        snaps.append({
            "label": label,
            "recent_return_10s":      float((pr_curr - pr10) / pr10 * 100),
            "recent_return_30s":      float((pr_curr - pr30) / pr30 * 100),
            "recent_return_60s":      float((pr_curr - pr60) / pr60 * 100),
            "trade_volume_10s":       vol10,
            "trade_volume_30s":       vol30,
            "trade_count_10s":        len(v10s),
            "trade_count_30s":        len(v30s),
            "sell_pressure_ratio_10s":sell10 / (vol10 + 1e-8),
            "sell_pressure_ratio_30s":sell30 / (vol30 + 1e-8),
            "buy_recovery_ratio_10s": buy5 / (buy5_10 + 1e-8),
            "bid_depth_change":       f_bdc,
            "ask_depth_change":       f_adc,
            "spread_pct":             f_sp,
            "spread_recovery":        f_spr,
            "orderbook_imbalance":    f_obi,
            "trade_intensity_change": vol10 / (float(np.sum(v20s)) + 1e-8),
            "volatility_60s":         volat,
            "liquidity_refill_score": f_liq,
        })
    return snaps


def process_market(conn, market, warnings):
    """
    6 bands × 60-min window → snapshots.
    """
    row = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)
    ).fetchone()
    if not row or row[0] is None:
        warnings.append(f"{market}: no ts data")
        return []

    min_ts, max_ts = float(row[0]), float(row[1])
    total_dur = max_ts - min_ts
    win_sec   = WINDOW_MINUTES * 60

    if total_dur < 3600:
        warnings.append(f"{market}: duration {total_dur/3600:.1f}h < 1h, skipped")
        return []

    band_starts = np.linspace(min_ts, max(min_ts, max_ts - win_sec), N_BANDS)
    budget_per_band = max(1, TARGET_SNAPSHOTS_PER_MARKET // N_BANDS)

    all_snaps = []
    for b_idx, w_start in enumerate(band_starts):
        w_end = min(w_start + win_sec, max_ts)
        rows  = _load_window(conn, market, w_start, w_end)
        if not rows:
            continue
        arrs = _parse_rows(rows)
        if arrs is None:
            continue
        snaps = _snapshots_from_arrays(arrs, budget_per_band)
        for s in snaps:
            s["market"] = market
        all_snaps.extend(snaps)
        del rows, arrs, snaps  # help GC

    win_cnt  = sum(1 for s in all_snaps if s["label"] in ("WIN_300", "WIN_600"))
    loss_cnt = sum(1 for s in all_snaps if s["label"] == "LOSS")
    to_cnt   = sum(1 for s in all_snaps if s["label"] == "TIMEOUT")
    print(f"[Info] {market}: snaps={len(all_snaps):,} "
          f"WIN={win_cnt} LOSS={loss_cnt} TO={to_cnt}")

    if len(all_snaps) < MIN_SNAPSHOTS_PER_MARKET:
        warnings.append(f"{market}: only {len(all_snaps)} snapshots (< {MIN_SNAPSHOTS_PER_MARKET})")

    return all_snaps


def main():
    print("=" * 60)
    print(" Cross-Market Reversal Feature Discovery  [time_uniform_sampling]")
    print("=" * 60)

    if not os.path.exists(SQLITE_CACHE):
        print(f"[Error] SQLite not found: {SQLITE_CACHE}")
        return

    conn = sqlite3.connect(SQLITE_CACHE)
    markets = get_markets(conn)
    if not markets:
        print("[Error] No KRW markets found.")
        conn.close()
        return

    print(f"[Info] Markets: {markets}")
    print(f"[Info] bands={N_BANDS}  window={WINDOW_MINUTES}min  "
          f"target_snaps={TARGET_SNAPSHOTS_PER_MARKET}\n")

    all_snapshots = []
    warnings      = []
    skipped       = []

    for i, m in enumerate(markets):
        print(f"[{i+1}/{len(markets)}] {m} ...", flush=True)
        try:
            snaps = process_market(conn, m, warnings)
            all_snapshots.extend(snaps)
        except Exception as ex:
            msg = f"{m}: error - {ex}"
            warnings.append(msg)
            skipped.append(m)
            print(f"  [Warning] {msg}")

    conn.close()
    print(f"\n[Info] Total snapshots: {len(all_snapshots):,}")

    if not all_snapshots:
        _save_failed(markets, skipped, warnings)
        return

    # ── Analysis ──────────────────────────────────────────────────────────────
    feature_names = [k for k in all_snapshots[0] if k not in ("market", "label")]

    mstats = defaultdict(lambda: {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "snaps": []})
    for s in all_snapshots:
        m = s["market"]; lbl = s["label"]
        if lbl in ("WIN_300", "WIN_600"): mstats[m]["WIN"] += 1
        elif lbl == "LOSS":               mstats[m]["LOSS"] += 1
        else:                             mstats[m]["TIMEOUT"] += 1
        mstats[m]["snaps"].append(s)

    valid_markets = [m for m, st in mstats.items()
                     if st["WIN"] >= 50 and st["LOSS"] >= 50]

    win_s  = [s for s in all_snapshots if s["label"] in ("WIN_300", "WIN_600")]
    loss_s = [s for s in all_snapshots if s["label"] == "LOSS"]
    to_s   = [s for s in all_snapshots if s["label"] == "TIMEOUT"]

    feature_analysis = []
    for f in feature_names:
        wv  = np.array([s[f] for s in win_s],  dtype=float)
        lv  = np.array([s[f] for s in loss_s], dtype=float)
        tov = np.array([s[f] for s in to_s],   dtype=float)

        w_mean = float(np.mean(wv)) if len(wv) else 0.0
        l_mean = float(np.mean(lv)) if len(lv) else 0.0
        d      = _cohens_d(wv, lv)
        sign   = 1 if d > 0 else -1

        consistent = 0
        mdet = {}
        for m in valid_markets:
            mwv = np.array([s[f] for s in mstats[m]["snaps"]
                            if s["label"] in ("WIN_300","WIN_600")], dtype=float)
            mlv = np.array([s[f] for s in mstats[m]["snaps"]
                            if s["label"] == "LOSS"], dtype=float)
            md  = _cohens_d(mwv, mlv)
            mdet[m] = float(md)
            if md * sign > 0.1:
                consistent += 1

        # Dominance warning
        if valid_markets and len(wv) > 0:
            top_m = max(valid_markets, key=lambda m: mstats[m]["WIN"])
            frac  = mstats[top_m]["WIN"] / max(len(win_s), 1)
            if frac > 0.6:
                warnings.append(
                    f"Feature {f}: {top_m} dominates WIN ({frac:.0%}) — possible bias"
                )

        feature_analysis.append({
            "feature": f,
            "win_mean":          w_mean,
            "loss_mean":         l_mean,
            "timeout_mean":      float(np.mean(tov)) if len(tov) else 0.0,
            "effect_size":       float(d),
            "consistent_markets":consistent,
            "valid_markets_total":len(valid_markets),
            "market_effects":    mdet,
            "higher_is_better":  bool(d > 0),
        })

    feature_analysis.sort(key=lambda x: abs(x["effect_size"]), reverse=True)

    # ── Judgement ─────────────────────────────────────────────────────────────
    if len(valid_markets) < 3:
        judgement = "NEED_MORE_DATA"
    elif not feature_analysis:
        judgement = "DISCOVERY_FAILED"
    else:
        strong = [f for f in feature_analysis if abs(f["effect_size"]) > 0.2]
        if not strong:
            judgement = "FEATURE_WEAK_BUT_DATA_OK"
        else:
            universal = [f for f in strong if f["consistent_markets"] >= 3]
            judgement = "COMMON_FEATURE_CANDIDATES_FOUND" if universal else "FEATURE_WEAK_BUT_DATA_OK"

    common_cands = [
        f["feature"] for f in feature_analysis
        if f["consistent_markets"] >= 3 and abs(f["effect_size"]) > 0.2
    ]

    per_market_dist = {
        m: {"WIN": st["WIN"], "LOSS": st["LOSS"], "TIMEOUT": st["TIMEOUT"]}
        for m, st in mstats.items()
    }

    # ── Save reports ──────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at":              datetime.now().isoformat(),
            "mode":                      "time_uniform_sampling",
            "target_snapshots_per_market": TARGET_SNAPSHOTS_PER_MARKET,
            "min_snapshots_per_market":  MIN_SNAPSHOTS_PER_MARKET,
            "band_count":                N_BANDS,
            "window_minutes":            WINDOW_MINUTES,
            "total_snapshots":           len(all_snapshots),
            "win_count":                 len(win_s),
            "loss_count":                len(loss_s),
            "timeout_count":             len(to_s),
            "good_markets":              markets,
            "valid_markets":             valid_markets,
            "valid_markets_count":       len(valid_markets),
            "skipped_markets":           skipped,
            "per_market_label_distribution": per_market_dist,
            "feature_top10":             feature_analysis[:10],
            "common_feature_candidates": common_cands,
            "warnings":                  warnings,
            "judgement":                 judgement,
            "note": (
                "This is a time_uniform_sampling DISCOVERY report. "
                "NOT a final strategy validation. "
                "No config / candidate / live files were modified."
            ),
        }, f, ensure_ascii=False, indent=2)

    # TXT
    lines = [
        "=" * 72,
        " Cross-Market Reversal Feature Discovery  [time_uniform_sampling]",
        "=" * 72,
        f"Generated        : {datetime.now().isoformat()}",
        f"Mode             : time_uniform_sampling",
        f"Bands x Window   : {N_BANDS} x {WINDOW_MINUTES}min",
        f"Target snaps/mkt : {TARGET_SNAPSHOTS_PER_MARKET}",
        f"Total snapshots  : {len(all_snapshots):,}",
        f"WIN              : {len(win_s):,}  LOSS: {len(loss_s):,}  TO: {len(to_s):,}",
        f"Valid markets    : {len(valid_markets)} / {len(markets)}  (>=50W/50L)",
        f"Judgement        : {judgement}",
        "",
        "[ Per-Market Label Distribution ]",
    ]
    for m, st in sorted(per_market_dist.items(), key=lambda x: x[1]["WIN"], reverse=True):
        lines.append(f"  {m}: WIN={st['WIN']} LOSS={st['LOSS']} TO={st['TIMEOUT']}")

    lines += [
        "",
        "[ Feature Top 10 by |Cohen's d| ]",
        "-" * 72,
        f"{'Feature':<28} {'W_mean':>8} {'L_mean':>8} {'d':>7} {'MktsConsist':>12}",
        "-" * 72,
    ]
    for fa in feature_analysis[:10]:
        lines.append(
            f"{fa['feature']:<28} {fa['win_mean']:>8.4f} {fa['loss_mean']:>8.4f} "
            f"{fa['effect_size']:>7.4f} {fa['consistent_markets']:>5}/{len(valid_markets)}"
        )
    lines.append("-" * 72)

    if common_cands:
        lines += ["", f"Common feature candidates (|d|>0.2, mkts>=3): {common_cands}"]

    if warnings:
        lines += ["", "[ Warnings ]"] + [f"  ! {w}" for w in warnings]

    lines += [
        "",
        "NOTE: DISCOVERY ONLY — not a final strategy validation.",
        "      No config / candidate / live files were modified.",
    ]

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")
    print(f"Judgement   : {judgement}")


def _save_failed(markets, skipped, warnings):
    os.makedirs(OUT_DIR, exist_ok=True)
    result = {
        "generated_at": datetime.now().isoformat(),
        "mode": "time_uniform_sampling",
        "judgement": "DISCOVERY_FAILED",
        "markets": markets,
        "skipped_markets": skipped,
        "warnings": warnings,
    }
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write(f"Judgement: DISCOVERY_FAILED\nWarnings: {warnings}\n")
    print("[Error] DISCOVERY_FAILED — no snapshots generated.")


if __name__ == "__main__":
    main()
