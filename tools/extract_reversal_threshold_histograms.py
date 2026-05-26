"""
extract_reversal_threshold_histograms.py
Feature Percentile Threshold Extractor

Reads cross-market validation and design reports and attempts to compute
per-feature percentile thresholds for candidate entry condition design.

IMPORTANT:
  - This script does NOT create or modify any candidate / config / live file.
  - Output is a RESEARCH REPORT ONLY.
  - If raw snapshot distributions are absent from the validation JSON,
    this script reports RAW_DISTRIBUTIONS_MISSING and provides guidance.
"""
import json
import os
import numpy as np
from datetime import datetime

# ─── Input paths ──────────────────────────────────────────────────────────────
VALIDATION_JSON = "reports/experiments/cross_market_validation_latest.json"
DESIGN_JSON     = "reports/experiments/reversal_paper_candidate_design_latest.json"

# ─── Output paths ─────────────────────────────────────────────────────────────
OUT_DIR  = "reports/experiments"
OUT_JSON = os.path.join(OUT_DIR, "reversal_threshold_histograms_latest.json")
OUT_TXT  = os.path.join(OUT_DIR, "reversal_threshold_histograms_latest.txt")

# ─── Target features & percentile targets ────────────────────────────────────
RETURN_FEATURES = ["recent_return_30s", "recent_return_60s"]
SELL_FEATURES   = ["sell_pressure_ratio_10s"]

RETURN_PERCENTILES  = [5, 10, 15, 20]
SELL_PERCENTILES    = [70, 75, 80, 85]

# ─── Labels tracked ───────────────────────────────────────────────────────────
LABELS = ["WIN", "LOSS", "TIMEOUT", "ALL"]


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Could not load {path}: {e}")
        return None


def _percs(values, percentiles):
    """Return dict {pN: value} for a list of floats."""
    if not values:
        return {f"p{p}": None for p in percentiles}
    arr = np.array(values, dtype=float)
    return {f"p{p}": float(np.percentile(arr, p)) for p in percentiles}


def _describe(values):
    """Basic descriptive stats for a list of floats."""
    if not values:
        return {"count": 0, "mean": None, "std": None, "min": None, "max": None}
    arr = np.array(values, dtype=float)
    return {
        "count": len(arr),
        "mean":  float(np.mean(arr)),
        "std":   float(np.std(arr)),
        "min":   float(np.min(arr)),
        "max":   float(np.max(arr)),
    }


def compute_from_raw_snapshots(snapshots, market_label):
    """
    Compute per-feature, per-label percentiles from a list of snapshot dicts.
    Each snapshot must have 'label' and feature keys.
    """
    all_features = RETURN_FEATURES + SELL_FEATURES
    results = {}

    for feat in all_features:
        percs_target = RETURN_PERCENTILES if feat in RETURN_FEATURES else SELL_PERCENTILES

        by_label = {lbl: [] for lbl in LABELS}
        for s in snapshots:
            val = s.get(feat)
            if val is None:
                continue
            lbl = s.get("label", "UNKNOWN")
            by_label["ALL"].append(float(val))
            if lbl in ("WIN_300", "WIN_600", "WIN"):
                by_label["WIN"].append(float(val))
            elif lbl == "LOSS":
                by_label["LOSS"].append(float(val))
            elif lbl == "TIMEOUT":
                by_label["TIMEOUT"].append(float(val))

        feat_result = {}
        for lbl in LABELS:
            vals = by_label[lbl]
            feat_result[lbl] = {
                "stats":      _describe(vals),
                "percentiles": _percs(vals, percs_target),
            }
        results[feat] = feat_result

    return results


def build_missing_report(valid, design):
    """Build a report when raw snapshot distributions are not in the JSON."""
    # We can still pull mean/effect_size from per_feature_results
    available_stats = {}
    for fr in valid.get("per_feature_results", []):
        fname = fr.get("feature")
        if fname in RETURN_FEATURES + SELL_FEATURES:
            available_stats[fname] = {
                "win_mean":           fr.get("win_mean"),
                "loss_mean":          fr.get("loss_mean"),
                "effect_size":        fr.get("effect_size"),
                "consistent_markets": fr.get("consistent_markets"),
                "available_percentiles": None,
                "note": (
                    "Raw snapshot distributions were not saved in the validation output. "
                    "Only aggregate WIN/LOSS means are available. "
                    "Percentile thresholds cannot be computed from this data alone."
                ),
            }

    guidance = {
        "problem": (
            "run_cross_market_reversal_validation.py does not currently save "
            "raw snapshot feature values to its output JSON. "
            "Only win_mean / loss_mean / effect_size are available."
        ),
        "recommended_fix": (
            "Add a 'raw_feature_distributions' block to the validation JSON output "
            "that stores, per market and per label, the list of feature values "
            "for the sampled snapshots. "
            "Then re-run validate + this histogram extractor."
        ),
        "alternative": (
            "Re-run the SQLite-based sampling (same time_uniform_sampling approach) "
            "inside this extractor directly and compute histograms without modifying "
            "the validation script."
        ),
    }

    return {
        "judgement":           "RAW_DISTRIBUTIONS_MISSING",
        "available_stats":     available_stats,
        "guidance":            guidance,
    }


def main():
    print("=" * 60)
    print(" Reversal Threshold Histogram Extractor")
    print("=" * 60)

    valid  = load_json(VALIDATION_JSON)
    design = load_json(DESIGN_JSON)

    if valid is None:
        print(f"[Error] Validation JSON not found: {VALIDATION_JSON}")
        _save({"judgement": "HISTOGRAM_FAILED",
               "error": f"{VALIDATION_JSON} not found"}, [])
        return

    # ── Check for raw snapshot distributions ──────────────────────────────────
    # The validation JSON may contain 'raw_feature_distributions' if we added it.
    # Currently (as of this implementation) it likely does NOT contain them.
    raw_dist = valid.get("raw_feature_distributions")  # None if not present
    per_market_snapshots = valid.get("per_market_snapshots")  # None if not present

    if raw_dist:
        print("[Info] raw_feature_distributions found in validation JSON.")
        warnings_hist = []

        # ── Actual structure:
        # raw_dist["aggregate"] = { label: { feature: [values] } }
        # raw_dist["by_market"] = { market: { label: { feature: [values] } } }

        def _read_label_feat(label_dict, scope_name):
            """
            Read { label: { feature: [values] } } and return
            { feature: { label: { stats, percentiles } } }
            """
            all_features = RETURN_FEATURES + SELL_FEATURES
            result_block = {}
            for feat in all_features:
                percs_target = RETURN_PERCENTILES if feat in RETURN_FEATURES else SELL_PERCENTILES
                feat_block = {}
                all_vals = []
                for lbl in ["WIN", "LOSS", "TIMEOUT"]:
                    vals = label_dict.get(lbl, {}).get(feat, [])
                    if not isinstance(vals, list):
                        warnings_hist.append(
                            f"{scope_name}[{lbl}][{feat}]: expected list, got {type(vals).__name__}"
                        )
                        vals = []
                    feat_block[lbl] = {
                        "stats":       _describe(vals),
                        "percentiles": _percs(vals, percs_target),
                    }
                    all_vals.extend(vals)
                feat_block["ALL"] = {
                    "stats":       _describe(all_vals),
                    "percentiles": _percs(all_vals, percs_target),
                }
                result_block[feat] = feat_block
            return result_block

        # Aggregate
        agg_label_dict = raw_dist.get("aggregate", {})
        aggregate_results = _read_label_feat(agg_label_dict, "aggregate")

        # Per-market
        by_market_dict = raw_dist.get("by_market", {})
        per_market_results = {}
        for market, label_dict in by_market_dict.items():
            per_market_results[market] = _read_label_feat(label_dict, market)

        # Total count from aggregate WIN list (representative)
        first_feat = (RETURN_FEATURES + SELL_FEATURES)[0]
        total_count = sum(
            len(agg_label_dict.get(lbl, {}).get(first_feat, []))
            for lbl in ["WIN", "LOSS", "TIMEOUT"]
        )

        result = {
            "judgement":          "HISTOGRAM_READY",
            "aggregate":          aggregate_results,
            "per_market":         per_market_results,
            "sample_count_total": total_count,
            "histogram_warnings": warnings_hist,
        }
        print(f"[Info] Computed histograms. Aggregate sample ref count: {total_count:,}")

    elif per_market_snapshots:
        print("[Info] per_market_snapshots found — computing histograms.")
        all_snapshots = []
        per_market_results = {}
        for market, snaps in per_market_snapshots.items():
            per_market_results[market] = compute_from_raw_snapshots(snaps, market)
            all_snapshots.extend(snaps)
        aggregate_results = compute_from_raw_snapshots(all_snapshots, "ALL_MARKETS")
        result = {
            "judgement":          "HISTOGRAM_READY",
            "aggregate":          aggregate_results,
            "per_market":         per_market_results,
            "sample_count_total": len(all_snapshots),
        }
        print(f"[Info] Computed histograms from {len(all_snapshots):,} snapshots.")

    else:
        print("[Info] No raw distributions in validation JSON. Building missing report.")
        result = build_missing_report(valid, design)

    # Attach metadata
    result["generated_at"]    = datetime.now().isoformat()
    result["source_files"]    = {
        "validation": VALIDATION_JSON,
        "design":     DESIGN_JSON if design else "(not found)",
    }
    result["target_features"] = RETURN_FEATURES + SELL_FEATURES
    result["note"] = (
        "This is a RESEARCH REPORT ONLY. "
        "No candidate or config file was created or modified."
    )

    _save(result, _build_txt(result))
    print(f"[Done] Judgement: {result['judgement']}")
    print(f"[Done] JSON : {OUT_JSON}")
    print(f"[Done] TXT  : {OUT_TXT}")


def _build_txt(result):
    judgement = result.get("judgement", "UNKNOWN")
    lines = [
        "=" * 72,
        "  Reversal Threshold Histogram Report",
        "=" * 72,
        f"Generated  : {result.get('generated_at', 'N/A')}",
        f"Judgement  : {judgement}",
        "",
    ]

    if judgement == "HISTOGRAM_READY":
        agg = result.get("aggregate", {})
        lines.append("[ Aggregate Percentile Thresholds ]")
        lines.append("-" * 72)
        for feat in RETURN_FEATURES + SELL_FEATURES:
            feat_data = agg.get(feat, {})
            lines.append(f"  {feat}:")
            for lbl in LABELS:
                lbl_data = feat_data.get(lbl, {})
                percs    = lbl_data.get("percentiles", {})
                stats    = lbl_data.get("stats", {})
                n        = stats.get("count", 0)
                p_str    = "  ".join(f"{k}={v:.4f}" for k, v in percs.items() if v is not None)
                lines.append(f"    [{lbl:<8}] n={n:>6}  {p_str}")
        lines.append("-" * 72)

        lines += [
            "",
            "[ Per-Market Breakdown ]",
            "  (see JSON for full per-market details)",
            "",
            f"  Total snapshots analysed: {result.get('sample_count_total', 0):,}",
        ]

    elif judgement == "RAW_DISTRIBUTIONS_MISSING":
        lines += [
            "[ Problem ]",
            f"  {result['guidance']['problem']}",
            "",
            "[ Available Aggregate Stats (from validation JSON) ]",
            "-" * 72,
        ]
        for feat, st in result.get("available_stats", {}).items():
            wm = st.get("win_mean")
            lm = st.get("loss_mean")
            d  = st.get("effect_size")
            cm = st.get("consistent_markets")
            lines.append(
                f"  {feat:<32}"
                f"  WIN_mean={wm:.4f}" if isinstance(wm, float) else f"  {feat:<32}  WIN_mean=N/A"
            )
            if isinstance(wm, float):
                lines.append(
                    f"  {'':>32}  LOSS_mean={lm:.4f}  d={d:.4f}  mkts={cm}"
                    if isinstance(lm, float) else ""
                )
        lines += [
            "-" * 72,
            "",
            "[ Recommended Fix ]",
            f"  {result['guidance']['recommended_fix']}",
            "",
            "[ Alternative ]",
            f"  {result['guidance']['alternative']}",
        ]

    else:
        lines.append(f"  Error or failure: {result.get('error', 'unknown')}")

    lines += [
        "",
        "=" * 72,
        "  RESEARCH REPORT ONLY.",
        "  No candidate / config / live files were created or modified.",
        "=" * 72,
    ]
    return lines


def _save(result, txt_lines):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")


if __name__ == "__main__":
    main()
