"""
run_cross_market_reversal_validation.py
Cross-Market Reversal Feature Validation

발견된 공통 feature 후보 5개를 대상으로 시장 편중, timeout 비율, 방향성 일관성을 검증한다.
이 스크립트는 validation 구조 확인용이며 최종 전략 확정이 아니다.
candidate / config / live 파일은 수정하지 않는다.
"""
import os
import json
import sqlite3
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import combinations

# ─── Paths ────────────────────────────────────────────────────────────────────
SQLITE_CACHE = "logs/experiments/master/reversal_edge_master_dataset.sqlite"
OUT_DIR      = "reports/experiments"
JSON_REPORT  = os.path.join(OUT_DIR, "cross_market_validation_latest.json")
TXT_REPORT   = os.path.join(OUT_DIR, "cross_market_validation_latest.txt")

# ─── Validation targets (from discovery result) ───────────────────────────────
VALIDATION_FEATURES = [
    "recent_return_30s",
    "sell_pressure_ratio_10s",
    "recent_return_60s",
    "recent_return_10s",
    "sell_pressure_ratio_30s",
]

# ─── Labeling ─────────────────────────────────────────────────────────────────
TP_300_PCT = 0.20
TP_600_PCT = 0.30
SL_PCT     = -0.20

# ─── Sampling (reuse discover approach) ───────────────────────────────────────
N_BANDS     = 6
WINDOW_MIN  = 60    # minutes per band
STEP_SEC    = 10.0
MAX_SNAPS   = 1500  # per market

# ─── Validation thresholds ────────────────────────────────────────────────────
MIN_VALID_MARKETS        = 5
MIN_WIN_PER_MARKET       = 50
MIN_LOSS_PER_MARKET      = 50
MAX_TIMEOUT_RATIO        = 0.85   # warn if > 85% are timeouts
MAX_SINGLE_MARKET_SHARE  = 0.60   # warn if one market contributes > 60%
SKIP_MARKETS = {"unknown", ""}

# ─── Raw distribution saving ──────────────────────────────────────────────────
RAW_DIST_FEATURES        = ["recent_return_30s", "recent_return_60s", "sell_pressure_ratio_10s"]
MAX_RAW_PER_LABEL_MARKET = 2000   # per market per label per feature
MAX_RAW_AGG              = 10000  # aggregate per label per feature

# ─── Validation mode ──────────────────────────────────────────────────────────
# Options:
#   "time_uniform_sampling"  — 6 bands × 60 min  (fast, ~9K snapshots total)
#   "full_dataset_banded"    — 20 bands × 120 min (full 200h, ~50K snapshots total)
VALIDATION_MODE = "full_dataset_banded"

# Full-dataset banded mode config
N_BANDS_FULL                   = 20     # bands across full timeline
WINDOW_MIN_FULL                = 120    # minutes per band (2h windows)
TARGET_SNAPSHOTS_PER_MARKET_FULL = 5000
MIN_SNAPSHOTS_PER_MARKET_FULL    = 1000


# ─── Utility ──────────────────────────────────────────────────────────────────
def _cohens_d(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0
    v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
    ps = np.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    return float((np.mean(a) - np.mean(b)) / ps) if ps else 0.0


def get_markets(conn):
    cur = conn.execute(
        "SELECT DISTINCT market FROM events WHERE market IS NOT NULL AND market != ''"
    )
    return [r[0] for r in cur.fetchall()
            if r[0] not in SKIP_MARKETS and r[0].startswith("KRW-")]


def _load_window(conn, market, w_start, w_end):
    cur = conn.execute(
        "SELECT ts, event_type, raw_json FROM events "
        "WHERE market=? AND ts BETWEEN ? AND ? ORDER BY ts ASC",
        (market, w_start, w_end),
    )
    return cur.fetchall()


def _parse_rows(rows):
    tr_ts, tr_pr, tr_vol, tr_side = [], [], [], []
    ob_ts, ob_bd, ob_ad = [], [], []

    for (ts_col, etype, raw_str) in rows:
        try:
            ev  = json.loads(raw_str)
            raw = ev.get("raw", {})
            et  = etype or ev.get("event_type") or raw.get("type")
            ts_ms = raw.get("timestamp") or raw.get("trade_timestamp")
            ts = ts_ms / 1000.0 if ts_ms else ev.get("received_at", ts_col)
            if ts is None: continue

            if et == "trade":
                pr = raw.get("trade_price") or ev.get("trade_price")
                vl = raw.get("trade_volume") or ev.get("trade_volume")
                if pr is None or vl is None: continue
                tr_ts.append(float(ts))
                tr_pr.append(float(pr))
                tr_vol.append(float(vl))
                tr_side.append(-1 if raw.get("ask_bid") == "ASK" else 1)
            elif et == "orderbook":
                units = raw.get("orderbook_units", [])
                if not units: continue
                ob_ts.append(float(ts))
                ob_bd.append(sum(float(u["bid_size"]) for u in units[:5]))
                ob_ad.append(sum(float(u["ask_size"]) for u in units[:5]))
        except Exception:
            pass

    if not tr_ts: return None
    sort = np.argsort(tr_ts)
    return {
        "t_ts":   np.array(tr_ts)[sort],
        "t_pr":   np.array(tr_pr)[sort],
        "t_vol":  np.array(tr_vol)[sort],
        "t_side": np.array(tr_side)[sort],
        "o_ts":   np.array(ob_ts) if ob_ts else np.array([]),
        "o_bd":   np.array(ob_bd) if ob_bd else np.array([]),
        "o_ad":   np.array(ob_ad) if ob_ad else np.array([]),
    }


def _compute_snapshot_features(arrs, snap_ts, pr_curr, i_curr):
    """Return dict of validation features for a single snapshot."""
    t_ts  = arrs["t_ts"]; t_pr = arrs["t_pr"]
    t_vol = arrs["t_vol"]; t_side = arrs["t_side"]

    def gidx(v): return np.searchsorted(t_ts, v, side="right")

    i_10s = gidx(snap_ts - 10)
    i_30s = gidx(snap_ts - 30)
    i_60s = gidx(snap_ts - 60)

    pr10 = t_pr[i_10s] if i_10s < len(t_pr) else pr_curr
    pr30 = t_pr[i_30s] if i_30s < len(t_pr) else pr_curr
    pr60 = t_pr[i_60s] if i_60s < len(t_pr) else pr_curr

    v10s = t_vol[i_10s:i_curr]; s10s = t_side[i_10s:i_curr]
    v30s = t_vol[i_30s:i_curr]; s30s = t_side[i_30s:i_curr]
    vol10 = float(np.sum(v10s)); vol30 = float(np.sum(v30s))
    sell10 = float(np.sum(v10s[s10s == -1]))
    sell30 = float(np.sum(v30s[s30s == -1]))

    return {
        "recent_return_10s":       float((pr_curr - pr10) / pr10 * 100) if pr10 else 0.0,
        "recent_return_30s":       float((pr_curr - pr30) / pr30 * 100) if pr30 else 0.0,
        "recent_return_60s":       float((pr_curr - pr60) / pr60 * 100) if pr60 else 0.0,
        "sell_pressure_ratio_10s": sell10 / (vol10 + 1e-8),
        "sell_pressure_ratio_30s": sell30 / (vol30 + 1e-8),
    }


def process_market_validation(conn, market, warnings):
    """Sample market data and compute validation snapshots."""
    row = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)
    ).fetchone()
    if not row or row[0] is None:
        warnings.append(f"{market}: no ts data")
        return []

    min_ts, max_ts = float(row[0]), float(row[1])
    if max_ts - min_ts < 3600:
        warnings.append(f"{market}: duration < 1h, skipped")
        return []

    win_sec       = WINDOW_MIN * 60
    band_starts   = np.linspace(min_ts, max(min_ts, max_ts - win_sec), N_BANDS)
    budget_per_band = max(1, MAX_SNAPS // N_BANDS)
    snaps = []

    for w_start in band_starts:
        w_end = min(w_start + win_sec, max_ts)
        rows  = _load_window(conn, market, w_start, w_end)
        if not rows: continue
        arrs = _parse_rows(rows)
        if arrs is None: continue

        t_ts = arrs["t_ts"]; t_pr = arrs["t_pr"]
        def gidx(v): return np.searchsorted(t_ts, v, side="right")

        band_snaps = []
        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - 650, STEP_SEC):
            if len(band_snaps) >= budget_per_band: break
            i_curr = gidx(snap_ts)
            if i_curr == 0: continue
            pr_curr = t_pr[i_curr - 1]
            if i_curr == gidx(snap_ts - 10): continue  # no recent trades

            # Label
            pr_300 = t_pr[i_curr : gidx(snap_ts + 300)]
            pr_600 = t_pr[i_curr : gidx(snap_ts + 600)]
            if len(pr_600) == 0: continue
            r300 = (pr_300 - pr_curr) / pr_curr * 100
            r600 = (pr_600 - pr_curr) / pr_curr * 100
            sl_i  = int(np.argmax(r600 <= SL_PCT))  if np.any(r600 <= SL_PCT)  else 999999
            tp3_i = int(np.argmax(r300 >= TP_300_PCT)) if np.any(r300 >= TP_300_PCT) else 999999
            tp6_i = int(np.argmax(r600 >= TP_600_PCT)) if np.any(r600 >= TP_600_PCT) else 999999
            if   sl_i < tp6_i and sl_i < tp3_i:  label = "LOSS"
            elif tp3_i < 999999 and tp3_i < sl_i: label = "WIN"
            elif tp6_i < 999999 and tp6_i < sl_i: label = "WIN"
            else:                                  label = "TIMEOUT"

            fwd60 = float((t_pr[gidx(snap_ts + 60) - 1] - pr_curr) / pr_curr * 100) \
                    if gidx(snap_ts + 60) > i_curr else 0.0

            feat = _compute_snapshot_features(arrs, snap_ts, pr_curr, i_curr)
            feat.update({"label": label, "fwd60": fwd60, "market": market})
            band_snaps.append(feat)

        snaps.extend(band_snaps)
        if len(snaps) >= MAX_SNAPS: break
        del rows, arrs, band_snaps

    w = sum(1 for s in snaps if s["label"] == "WIN")
    l = sum(1 for s in snaps if s["label"] == "LOSS")
    t = sum(1 for s in snaps if s["label"] == "TIMEOUT")
    print(f"[Info] {market}: snaps={len(snaps)} WIN={w} LOSS={l} TO={t}")
    return snaps


def _evaluate_feature(name, snaps, valid_markets, mstats):
    """Single-feature validation metrics."""
    win_s  = [s for s in snaps if s["label"] == "WIN"]
    loss_s = [s for s in snaps if s["label"] == "LOSS"]

    w_vals = np.array([s[name] for s in win_s],  dtype=float)
    l_vals = np.array([s[name] for s in loss_s], dtype=float)
    d = _cohens_d(w_vals, l_vals)

    consistent = 0
    sign = 1 if d > 0 else -1
    per_market = {}
    for m in valid_markets:
        mw = np.array([s[name] for s in mstats[m]["snaps"] if s["label"] == "WIN"],  dtype=float)
        ml = np.array([s[name] for s in mstats[m]["snaps"] if s["label"] == "LOSS"], dtype=float)
        md = _cohens_d(mw, ml)
        per_market[m] = float(md)
        if md * sign > 0.05: consistent += 1

    fwd_w = np.array([s["fwd60"] for s in win_s],  dtype=float)
    fwd_l = np.array([s["fwd60"] for s in loss_s], dtype=float)

    return {
        "feature": name,
        "effect_size": float(d),
        "consistent_markets": consistent,
        "valid_markets_total": len(valid_markets),
        "win_mean": float(np.mean(w_vals)) if len(w_vals) else 0.0,
        "loss_mean": float(np.mean(l_vals)) if len(l_vals) else 0.0,
        "avg_fwd60_win":  float(np.mean(fwd_w)) if len(fwd_w) else 0.0,
        "avg_fwd60_loss": float(np.mean(fwd_l)) if len(fwd_l) else 0.0,
        "per_market_d": per_market,
    }


def _evaluate_combination(feat_list, snaps, valid_markets, mstats):
    """Multi-feature combo: score = sum of z-scores, then WIN/LOSS separation."""
    # Compute per-feature z-score direction
    all_vals = {f: np.array([s[f] for s in snaps], dtype=float) for f in feat_list}
    means = {f: float(np.mean(all_vals[f])) for f in feat_list}
    stds  = {f: float(np.std(all_vals[f])) + 1e-8 for f in feat_list}

    # Direction from discovery: recent_return features → lower is better (WIN has lower)
    # sell_pressure → higher is better (WIN has higher)
    # Use effect sign from individual feature
    # Simple: accumulate (val - mean) / std, flip sign if WIN mean < LOSS mean
    def score(snap):
        total = 0.0
        for f in feat_list:
            z = (snap[f] - means[f]) / stds[f]
            # recent_return: WIN has lower → flip
            if "return" in f: z = -z
            total += z
        return total

    for s in snaps:
        s["_combo_score"] = score(s)

    win_scores  = np.array([s["_combo_score"] for s in snaps if s["label"] == "WIN"])
    loss_scores = np.array([s["_combo_score"] for s in snaps if s["label"] == "LOSS"])
    d = _cohens_d(win_scores, loss_scores)

    return {
        "features": feat_list,
        "effect_size": float(d),
        "win_score_mean":  float(np.mean(win_scores))  if len(win_scores) else 0.0,
        "loss_score_mean": float(np.mean(loss_scores)) if len(loss_scores) else 0.0,
    }


def process_market_validation_full_banded(conn, market, warnings):
    """
    Full-dataset banded mode: covers the entire available timeline.
    Divides ts range into N_BANDS_FULL bands and loads WINDOW_MIN_FULL
    minutes per band.  Uses market + ts BETWEEN queries (no full scan).
    """
    row = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM events WHERE market=?", (market,)
    ).fetchone()
    if not row or row[0] is None:
        warnings.append(f"{market}: no ts data")
        return []

    min_ts, max_ts = float(row[0]), float(row[1])
    total_dur_h    = (max_ts - min_ts) / 3600
    if max_ts - min_ts < 3600:
        warnings.append(f"{market}: duration {total_dur_h:.1f}h < 1h, skipped")
        return []

    win_sec        = WINDOW_MIN_FULL * 60
    band_starts    = np.linspace(min_ts, max(min_ts, max_ts - win_sec), N_BANDS_FULL)
    budget_per_band = max(1, TARGET_SNAPSHOTS_PER_MARKET_FULL // N_BANDS_FULL)

    all_snaps = []
    for w_start in band_starts:
        w_end = min(w_start + win_sec, max_ts)
        rows  = _load_window(conn, market, w_start, w_end)
        if not rows:
            continue
        arrs = _parse_rows(rows)
        if arrs is None:
            continue

        t_ts = arrs["t_ts"]; t_pr = arrs["t_pr"]
        def gidx(v): return np.searchsorted(t_ts, v, side="right")

        band_snaps = []
        for snap_ts in np.arange(float(t_ts[0]) + 60, float(t_ts[-1]) - 650, STEP_SEC):
            if len(band_snaps) >= budget_per_band:
                break
            i_curr = gidx(snap_ts)
            if i_curr == 0:
                continue
            pr_curr = t_pr[i_curr - 1]
            if i_curr == gidx(snap_ts - 10):
                continue

            pr_300 = t_pr[i_curr : gidx(snap_ts + 300)]
            pr_600 = t_pr[i_curr : gidx(snap_ts + 600)]
            if len(pr_600) == 0:
                continue
            r300 = (pr_300 - pr_curr) / pr_curr * 100
            r600 = (pr_600 - pr_curr) / pr_curr * 100
            sl_i  = int(np.argmax(r600 <= SL_PCT))      if np.any(r600 <= SL_PCT)      else 999999
            tp3_i = int(np.argmax(r300 >= TP_300_PCT))  if np.any(r300 >= TP_300_PCT)  else 999999
            tp6_i = int(np.argmax(r600 >= TP_600_PCT))  if np.any(r600 >= TP_600_PCT)  else 999999
            if   sl_i < tp6_i and sl_i < tp3_i:  label = "LOSS"
            elif tp3_i < 999999 and tp3_i < sl_i: label = "WIN"
            elif tp6_i < 999999 and tp6_i < sl_i: label = "WIN"
            else:                                  label = "TIMEOUT"

            fwd60 = float((t_pr[gidx(snap_ts + 60) - 1] - pr_curr) / pr_curr * 100) \
                    if gidx(snap_ts + 60) > i_curr else 0.0

            feat = _compute_snapshot_features(arrs, snap_ts, pr_curr, i_curr)
            feat.update({"label": label, "fwd60": fwd60, "market": market})
            band_snaps.append(feat)

        all_snaps.extend(band_snaps)
        if len(all_snaps) >= TARGET_SNAPSHOTS_PER_MARKET_FULL:
            break
        del rows, arrs, band_snaps

    w = sum(1 for s in all_snaps if s["label"] == "WIN")
    l = sum(1 for s in all_snaps if s["label"] == "LOSS")
    t = sum(1 for s in all_snaps if s["label"] == "TIMEOUT")
    print(f"[Info] {market}: mode=full_banded  dur={total_dur_h:.1f}h  "
          f"snaps={len(all_snaps)} WIN={w} LOSS={l} TO={t}")

    if len(all_snaps) < MIN_SNAPSHOTS_PER_MARKET_FULL:
        warnings.append(
            f"{market}: only {len(all_snaps)} snapshots in full_banded mode "
            f"(< {MIN_SNAPSHOTS_PER_MARKET_FULL})"
        )
    return all_snaps


def main():
    print("=" * 60)
    print(f" Cross-Market Reversal Feature Validation  [{VALIDATION_MODE}]")
    print("=" * 60)
    print(f"Validation features: {VALIDATION_FEATURES}")
    print(f"Mode               : {VALIDATION_MODE}\n")

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
    warnings = []
    all_snaps = []

    _process_fn = (
        process_market_validation_full_banded
        if VALIDATION_MODE == "full_dataset_banded"
        else process_market_validation
    )
    target_snaps = (
        TARGET_SNAPSHOTS_PER_MARKET_FULL
        if VALIDATION_MODE == "full_dataset_banded"
        else MAX_SNAPS
    )

    for i, m in enumerate(markets):
        print(f"[{i+1}/{len(markets)}] {m} ...", flush=True)
        try:
            snaps = _process_fn(conn, m, warnings)
            all_snaps.extend(snaps)
        except Exception as ex:
            warnings.append(f"{m}: error - {ex}")

    conn.close()
    print(f"\n[Info] Total snapshots: {len(all_snaps):,}")

    if not all_snaps:
        _save_failed(markets, warnings)
        return

    # ── Market stats ──────────────────────────────────────────────────────────
    mstats = defaultdict(lambda: {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "snaps": []})
    total_win = total_loss = total_to = 0
    for s in all_snaps:
        m = s["market"]; lbl = s["label"]
        mstats[m][lbl if lbl != "WIN" else "WIN"] 
        if lbl == "WIN":   mstats[m]["WIN"] += 1;     total_win += 1
        elif lbl == "LOSS":mstats[m]["LOSS"] += 1;    total_loss += 1
        else:              mstats[m]["TIMEOUT"] += 1; total_to += 1
        mstats[m]["snaps"].append(s)

    valid_markets = [m for m, st in mstats.items()
                     if st["WIN"] >= MIN_WIN_PER_MARKET and st["LOSS"] >= MIN_LOSS_PER_MARKET]
    print(f"[Info] Valid markets: {len(valid_markets)} / {len(markets)}")

    # ── Timeout ratio check ───────────────────────────────────────────────────
    total = len(all_snaps)
    to_ratio = total_to / total if total else 0.0
    if to_ratio > MAX_TIMEOUT_RATIO:
        warnings.append(
            f"High timeout ratio: {to_ratio:.1%} (>{MAX_TIMEOUT_RATIO:.0%}). "
            "Signal may be too rare for reliable validation."
        )

    # ── Market bias check ─────────────────────────────────────────────────────
    if valid_markets and total_win > 0:
        top_m   = max(valid_markets, key=lambda m: mstats[m]["WIN"])
        win_share = mstats[top_m]["WIN"] / total_win
        if win_share > MAX_SINGLE_MARKET_SHARE:
            warnings.append(
                f"Market bias: {top_m} contributes {win_share:.0%} of all WIN. "
                "Results may not generalise across markets."
            )

    # ── Per-feature validation ────────────────────────────────────────────────
    per_feature_results = []
    for feat in VALIDATION_FEATURES:
        res = _evaluate_feature(feat, all_snaps, valid_markets, mstats)
        per_feature_results.append(res)
    per_feature_results.sort(key=lambda x: abs(x["effect_size"]), reverse=True)

    # ── Feature combination validation (pairs + triple of top-3) ─────────────
    combo_results = []
    top3 = [r["feature"] for r in per_feature_results[:3]]
    eval_combos = list(combinations(VALIDATION_FEATURES, 2)) + [tuple(top3)]
    for combo in eval_combos:
        if len(set(combo)) < 2: continue
        try:
            cr = _evaluate_combination(list(combo), all_snaps, valid_markets, mstats)
            combo_results.append(cr)
        except Exception as ex:
            warnings.append(f"Combo {combo}: error - {ex}")
    combo_results.sort(key=lambda x: abs(x["effect_size"]), reverse=True)

    # ── Judgement ─────────────────────────────────────────────────────────────
    if len(valid_markets) < MIN_VALID_MARKETS:
        judgement = "NEED_MORE_VALIDATION"
    else:
        strong = [r for r in per_feature_results
                  if abs(r["effect_size"]) > 0.15 and r["consistent_markets"] >= 3]
        bias_warned = any("Market bias" in w for w in warnings)
        if not strong:
            judgement = "FEATURES_WEAK"
        elif bias_warned:
            judgement = "MARKET_BIAS_WARNING"
        else:
            judgement = "VALIDATION_READY"

    # ── Per-market summary ────────────────────────────────────────────────────
    per_market_results = {
        m: {
            "WIN": st["WIN"], "LOSS": st["LOSS"], "TIMEOUT": st["TIMEOUT"],
            "valid": m in valid_markets,
        }
        for m, st in mstats.items()
    }

    aggregate = {
        "total_snapshots": total,
        "total_win":  total_win,
        "total_loss": total_loss,
        "total_timeout": total_to,
        "timeout_ratio": float(to_ratio),
        "valid_markets_count": len(valid_markets),
        "valid_markets": valid_markets,
    }

    # ── Build raw_feature_distributions ─────────────────────────────────────
    # aggregate: { label: { feature: [values...] } }
    # by_market: { market: { label: { feature: [values...] } } }
    raw_labels = ["WIN", "LOSS", "TIMEOUT"]
    agg_dist   = {lbl: {f: [] for f in RAW_DIST_FEATURES} for lbl in raw_labels}
    mkt_dist   = {}

    for s in all_snaps:
        lbl = s["label"]  # WIN, LOSS, or TIMEOUT
        mkt = s["market"]
        if lbl not in raw_labels:
            continue
        if mkt not in mkt_dist:
            mkt_dist[mkt] = {l: {f: [] for f in RAW_DIST_FEATURES} for l in raw_labels}
        for feat in RAW_DIST_FEATURES:
            val = s.get(feat)
            if val is None:
                continue
            # per-market cap
            if len(mkt_dist[mkt][lbl][feat]) < MAX_RAW_PER_LABEL_MARKET:
                mkt_dist[mkt][lbl][feat].append(float(val))
            # aggregate cap
            if len(agg_dist[lbl][feat]) < MAX_RAW_AGG:
                agg_dist[lbl][feat].append(float(val))

    # Truncation warnings
    for lbl in raw_labels:
        for feat in RAW_DIST_FEATURES:
            if len(agg_dist[lbl][feat]) >= MAX_RAW_AGG:
                warnings.append(
                    f"raw_dist aggregate [{lbl}][{feat}] truncated at {MAX_RAW_AGG}"
                )

    raw_feature_distributions = {
        "aggregate": agg_dist,
        "by_market":  mkt_dist,
    }
    # Summary counts for TXT
    raw_counts = {
        lbl: {feat: len(agg_dist[lbl][feat]) for feat in RAW_DIST_FEATURES}
        for lbl in raw_labels
    }

    # ── Save ──────────────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at":                datetime.now().isoformat(),
            "mode":                        VALIDATION_MODE,
            "target_snapshots_per_market": target_snaps,
            "fee_slippage_applied":        False,
            "fee_note":                    "fee/slippage not yet applied — feature separation validation only",
            "validation_features":         VALIDATION_FEATURES,
            "aggregate_results":           aggregate,
            "per_market_results":          per_market_results,
            "per_feature_results":         per_feature_results,
            "feature_combination_results": combo_results[:10],
            "raw_feature_distributions":   raw_feature_distributions,
            "warnings":                    warnings,
            "judgement":                   judgement,
            "note": (
                "This is a feature validation report. "
                "NOT a production strategy. "
                "No config / candidate / live files were modified."
            ),
        }, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        f" Cross-Market Reversal Feature Validation Report  [{VALIDATION_MODE}]",
        "=" * 72,
        f"Generated       : {datetime.now().isoformat()}",
        f"Mode            : {VALIDATION_MODE}",
        f"Target snaps/mkt: {target_snaps}",
        f"Fee/slippage    : NOT YET APPLIED (feature separation study only)",
        f"Judgement       : {judgement}",
        f"Snapshots       : {total:,}  (WIN={total_win} LOSS={total_loss} TO={total_to})",
        f"Timeout ratio   : {to_ratio:.1%}",
        f"Valid markets   : {len(valid_markets)} / {len(markets)}  {valid_markets}",
        "",
        "[ Per-Feature Results ]",
        "-" * 72,
        f"{'Feature':<30} {'d':>7} {'Mkts>=0.05':>12} {'W_mean':>8} {'L_mean':>8}",
        "-" * 72,
    ]
    for r in per_feature_results:
        lines.append(
            f"{r['feature']:<30} {r['effect_size']:>7.4f} "
            f"{r['consistent_markets']:>5}/{len(valid_markets):<5} "
            f"{r['win_mean']:>8.4f} {r['loss_mean']:>8.4f}"
        )
    lines.append("-" * 72)

    lines += ["", "[ Feature Combination Results (top 5) ]", "-" * 60]
    for cr in combo_results[:5]:
        lines.append(f"  {cr['features']}  d={cr['effect_size']:.4f}")
    lines.append("-" * 60)

    if warnings:
        lines += ["", "[ Warnings ]"] + [f"  ! {w}" for w in warnings]

    # Raw distribution summary (no raw values in TXT)
    raw_saved_summary = "  ".join(
        f"{lbl}:" + ",".join(f"{f}={raw_counts[lbl][f]}" for f in RAW_DIST_FEATURES)
        for lbl in raw_labels
    )
    lines += [
        "",
        "[ Raw Feature Distributions ]",
        f"  Saved: yes  (features: {RAW_DIST_FEATURES})",
        f"  Counts (aggregate): {raw_saved_summary}",
    ]
    lines += [
        "",
        "NOTE: Validation only — not a production strategy.",
        "      No config / candidate / live files were modified.",
    ]
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[Done] JSON : {JSON_REPORT}")
    print(f"[Done] TXT  : {TXT_REPORT}")
    print(f"Judgement   : {judgement}")


def _save_failed(markets, warnings):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "judgement": "VALIDATION_FAILED",
            "markets": markets,
            "warnings": warnings,
        }, f, ensure_ascii=False, indent=2)
    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write(f"Judgement: VALIDATION_FAILED\nWarnings: {warnings}\n")
    print("[Error] VALIDATION_FAILED — no snapshots.")


if __name__ == "__main__":
    main()
