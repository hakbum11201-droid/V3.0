"""
design_reversal_paper_candidate.py
Paper Candidate Design Report Generator

Reads cross-market discovery & validation results and produces a
structured design proposal for a potential paper-testing candidate.

IMPORTANT:
  - This script does NOT create or modify any candidate / config / live file.
  - This is a DESIGN DOCUMENT only, not a production strategy.
  - Paper validation must be performed before any candidate promotion.
"""
import json
import os
import numpy as np
from datetime import datetime

# ─── Input paths ──────────────────────────────────────────────────────────────
DISCOVERY_JSON  = "reports/experiments/cross_market_feature_discovery_latest.json"
VALIDATION_JSON = "reports/experiments/cross_market_validation_latest.json"

# ─── Output paths ─────────────────────────────────────────────────────────────
OUT_DIR   = "reports/experiments"
OUT_JSON  = os.path.join(OUT_DIR, "reversal_paper_candidate_design_latest.json")
OUT_TXT   = os.path.join(OUT_DIR, "reversal_paper_candidate_design_latest.txt")

# ─── Target features (from discovery + validation) ────────────────────────────
TARGET_FEATURES = [
    "recent_return_30s",
    "recent_return_60s",
    "sell_pressure_ratio_10s",
]

# ─── Percentile candidates (not confirmed thresholds) ────────────────────────
RETURN_PERCENTILES  = [5, 10, 15, 20]   # lower tail of recent_return_*
SELL_PRES_PERCS     = [70, 75, 80, 85]  # upper tail of sell_pressure_ratio

# ─── TP / SL / Timeout candidate ranges (NOT confirmed) ──────────────────────
TP_CANDIDATES      = [0.20, 0.30, 0.40]   # %
SL_CANDIDATES      = [-0.10, -0.15, -0.20]  # %
TIMEOUT_CANDIDATES = [180, 300, 450]        # seconds


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Could not load {path}: {e}")
        return {}


def extract_feature_stats(disc, valid, feat):
    """Pull win_mean / loss_mean / effect_size from validation results."""
    result = {"feature": feat, "disc_d": None, "val_d": None,
              "win_mean": None, "loss_mean": None, "consistent_markets": None}

    # Discovery
    for f in disc.get("feature_top10", []):
        if f.get("feature") == feat:
            result["disc_d"] = f.get("effect_size")
            break

    # Validation
    for f in valid.get("per_feature_results", []):
        if f.get("feature") == feat:
            result["val_d"]               = f.get("effect_size")
            result["win_mean"]            = f.get("win_mean")
            result["loss_mean"]           = f.get("loss_mean")
            result["consistent_markets"]  = f.get("consistent_markets")
            break

    return result


def percentile_description(stats):
    """Return human-readable entry condition candidates."""
    conds = []
    feat = stats["feature"]
    wm   = stats.get("win_mean")
    lm   = stats.get("loss_mean")
    if wm is None or lm is None:
        return ["(insufficient data to propose thresholds)"]

    if "return" in feat:
        # WIN has lower recent return → entry on drop
        note = f"WIN mean={wm:.4f}  LOSS mean={lm:.4f}  (WIN < LOSS: drop-then-rebound pattern)"
        conds.append(note)
        for p in RETURN_PERCENTILES:
            conds.append(f"  Candidate: {feat} <= p{p} (exact value requires paper data histogram)")
    elif "sell_pressure" in feat:
        # WIN has higher sell pressure → sell pressure spike before rebound
        note = f"WIN mean={wm:.4f}  LOSS mean={lm:.4f}  (WIN > LOSS: sell pressure spike pattern)"
        conds.append(note)
        for p in SELL_PRES_PERCS:
            conds.append(f"  Candidate: {feat} >= p{p} (exact value requires paper data histogram)")
    return conds


def main():
    print("=" * 60)
    print(" Paper Candidate Design Report Generator")
    print("=" * 60)

    disc  = load_json(DISCOVERY_JSON)
    valid = load_json(VALIDATION_JSON)

    disc_judgement  = disc.get("judgement",  "N/A")
    valid_judgement = valid.get("judgement", "N/A")
    agg = valid.get("aggregate_results", {})

    print(f"[Info] Discovery  : {disc_judgement}")
    print(f"[Info] Validation : {valid_judgement}")

    # ── Feature stats ─────────────────────────────────────────────────────────
    feature_stats = [extract_feature_stats(disc, valid, f) for f in TARGET_FEATURES]

    # ── Best combination from validation ─────────────────────────────────────
    combos = valid.get("feature_combination_results", [])
    best_combo = combos[0] if combos else {}

    # ── Entry condition candidates ────────────────────────────────────────────
    entry_conditions = {}
    for fs in feature_stats:
        entry_conditions[fs["feature"]] = percentile_description(fs)

    # ── Design document ───────────────────────────────────────────────────────
    design = {
        "generated_at":  datetime.now().isoformat(),
        "document_type": "paper_candidate_design",
        "status":        "DESIGN_ONLY — not a confirmed candidate",
        "paper_validated": False,
        "source_files": {
            "discovery":  DISCOVERY_JSON,
            "validation": VALIDATION_JSON,
        },
        "evidence_summary": {
            "discovery_judgement":  disc_judgement,
            "validation_judgement": valid_judgement,
            "valid_markets_count":  agg.get("valid_markets_count", "N/A"),
            "total_snapshots":      agg.get("total_snapshots", "N/A"),
            "timeout_ratio":        agg.get("timeout_ratio", "N/A"),
            "best_combo_features":  best_combo.get("features", TARGET_FEATURES),
            "best_combo_effect_d":  best_combo.get("effect_size", "N/A"),
        },
        "strategy_interpretation": (
            "Short-term sharp price drop + concentrated sell pressure "
            "preceding a potential rebound. Observed as a consistent pattern "
            "across multiple KRW markets. NOT confirmed as profitable after "
            "fees and slippage."
        ),
        "target_features": TARGET_FEATURES,
        "per_feature_evidence": feature_stats,
        "entry_condition_candidates": entry_conditions,
        "entry_logic_note": (
            "All three features should be satisfied simultaneously. "
            "Exact threshold values must be determined from paper-trade data histograms. "
            "Do NOT hardcode these values into a candidate file yet."
        ),
        "exit_parameters_candidates": {
            "take_profit_pct":   TP_CANDIDATES,
            "stop_loss_pct":     SL_CANDIDATES,
            "timeout_seconds":   TIMEOUT_CANDIDATES,
            "note": (
                "These ranges are initial candidates only. "
                "Final values must be tuned against paper-trade outcomes "
                "with realistic fee and slippage assumptions."
            ),
        },
        "cost_model_requirements": {
            "fee_rate_pct":       0.05,
            "slippage_pct":       "0.03–0.10 (market-dependent)",
            "min_net_pnl_target": "> 0 after all costs",
            "note": "Cost model must be fully reflected before any candidate promotion.",
        },
        "next_steps": [
            "1. Run paper simulation with entry_condition_candidates above.",
            "2. Collect at least 30+ paper trades per market.",
            "3. Review per-market win rate, net PnL, and timeout ratio.",
            "4. Only if paper results are positive across >= 5 markets: "
               "consider formal candidate creation (manual, human-approved).",
            "5. DO NOT promote to live or tiny_live without full paper validation.",
        ],
        "prohibited_actions": [
            "Creating or modifying candidate JSON files",
            "Modifying config/config.json or configs/experiments/*.json",
            "Setting live.enabled = true",
            "Calling order placement APIs",
            "Treating this document as a production strategy",
        ],
    }

    # ── Save JSON ─────────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(design, f, ensure_ascii=False, indent=2)

    # ── Save TXT (English only, no Korean to avoid encoding issues) ───────────
    txt_lines = [
        "=" * 72,
        "  Reversal Paper Candidate Design Report",
        "  STATUS: DESIGN ONLY — not a confirmed candidate",
        "=" * 72,
        f"Generated     : {design['generated_at']}",
        f"Paper validated: {design['paper_validated']}",
        "",
        "[ Evidence Summary ]",
        f"  Discovery  : {disc_judgement}",
        f"  Validation : {valid_judgement}",
        f"  Valid mkts : {agg.get('valid_markets_count', 'N/A')}",
        f"  Snapshots  : {agg.get('total_snapshots', 'N/A'):,}" if isinstance(agg.get('total_snapshots'), int) else f"  Snapshots  : {agg.get('total_snapshots', 'N/A')}",
        f"  TO ratio   : {agg.get('timeout_ratio', 0)*100:.1f}%" if isinstance(agg.get('timeout_ratio'), float) else f"  TO ratio   : N/A",
        f"  Best combo : {best_combo.get('features', TARGET_FEATURES)}",
        f"  Best d     : {best_combo.get('effect_size', 'N/A')}",
        "",
        "[ Strategy Interpretation ]",
        "  Short-term sharp price drop + concentrated sell pressure",
        "  preceding a potential rebound.",
        "  Observed consistently across multiple KRW markets.",
        "  NOT confirmed as profitable after fees and slippage.",
        "",
        "[ Target Features ]",
    ]
    for fs in feature_stats:
        d_val = f"{fs['val_d']:+.4f}" if isinstance(fs.get("val_d"), float) else "N/A"
        wm    = f"{fs['win_mean']:.4f}"  if isinstance(fs.get("win_mean"),  float) else "N/A"
        lm    = f"{fs['loss_mean']:.4f}" if isinstance(fs.get("loss_mean"), float) else "N/A"
        cm    = fs.get("consistent_markets", "N/A")
        txt_lines.append(f"  {fs['feature']:<32} d={d_val}  W={wm}  L={lm}  mkts={cm}")

    txt_lines += [
        "",
        "[ Entry Condition Candidates (NOT confirmed thresholds) ]",
    ]
    for feat, cond_list in entry_conditions.items():
        txt_lines.append(f"  {feat}:")
        for c in cond_list:
            txt_lines.append(f"    {c}")

    txt_lines += [
        "",
        "  Logic: ALL three features must be satisfied simultaneously.",
        "  Exact threshold values must come from paper-trade data histograms.",
        "  DO NOT hardcode these into a candidate file yet.",
        "",
        "[ Exit Parameter Candidates (ranges, NOT confirmed) ]",
        f"  Take-profit (%): {TP_CANDIDATES}",
        f"  Stop-loss   (%): {SL_CANDIDATES}",
        f"  Timeout    (s) : {TIMEOUT_CANDIDATES}",
        "  Note: tune against paper-trade outcomes with realistic cost model.",
        "",
        "[ Cost Model Requirements ]",
        "  Fee rate     : 0.05%",
        "  Slippage     : 0.03-0.10% (market-dependent)",
        "  Min net PnL  : > 0 after all costs",
        "  NOTE: Full cost reflection required before any candidate promotion.",
        "",
        "[ Next Steps ]",
    ]
    for step in design["next_steps"]:
        txt_lines.append(f"  {step}")

    txt_lines += [
        "",
        "[ Prohibited Actions ]",
    ]
    for p in design["prohibited_actions"]:
        txt_lines.append(f"  NO  {p}")

    txt_lines += [
        "",
        "=" * 72,
        "  This document is for research review only.",
        "  No config / candidate / live files were created or modified.",
        "=" * 72,
    ]

    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")

    print(f"[Done] JSON : {OUT_JSON}")
    print(f"[Done] TXT  : {OUT_TXT}")
    print("Status: DESIGN_ONLY — no candidate or config file created.")


if __name__ == "__main__":
    main()
