"""
run_reversal_paper_simulation_with_costs.py
Reversal Paper Simulation with Cost Model

Uses raw_feature_distributions from the validation JSON to filter
snapshots by entry conditions and compute WIN/LOSS/TIMEOUT outcomes
with fee and slippage cost scenarios applied.

IMPORTANT:
  - This is a PRELIMINARY SIMULATION ONLY.
  - No orders are placed. No candidate or config files are created.
  - Results are label-based estimates, not actual price-path backtests.
  - Do NOT treat positive results as confirmed strategy profitability.
"""
import json
import os
import numpy as np
from datetime import datetime

# ─── Input paths ──────────────────────────────────────────────────────────────
VALIDATION_JSON  = "reports/experiments/cross_market_validation_latest.json"
HISTOGRAM_JSON   = "reports/experiments/reversal_threshold_histograms_latest.json"

# ─── Output paths ─────────────────────────────────────────────────────────────
OUT_DIR  = "reports/experiments"
OUT_JSON = os.path.join(OUT_DIR, "reversal_paper_simulation_with_costs_latest.json")
OUT_TXT  = os.path.join(OUT_DIR, "reversal_paper_simulation_with_costs_latest.txt")

# ─── Entry condition sets ─────────────────────────────────────────────────────
# Based on full_dataset_banded validation best combo (d=0.6884)
CONDITION_SETS = {
    "standard": {
        "recent_return_30s":       ("<=", -0.3891),   # WIN p10 aggregate
        "sell_pressure_ratio_10s": (">=",  0.9929),   # WIN p75 aggregate
        "note": "Standard: WIN p10 return + WIN p75 sell_pressure",
    },
    "conservative": {
        "recent_return_30s":       ("<=", -0.5952),   # WIN p5 aggregate
        "sell_pressure_ratio_10s": (">=",  1.0000),   # WIN p85 aggregate (capped)
        "note": "Conservative: WIN p5 return + WIN p85 sell_pressure",
    },
}

# ─── Cost model ───────────────────────────────────────────────────────────────
UPBIT_FEE_PCT   = 0.05   # Upbit maker/taker fee (one-way)
SLIPPAGE_SCENARIOS = [0.03, 0.05, 0.10]   # % one-way slippage candidates

# Round-trip cost = (fee + slippage) × 2
def round_trip_cost(slippage_pct):
    return (UPBIT_FEE_PCT + slippage_pct) * 2

# ─── Label-based outcome estimates ───────────────────────────────────────────
# Based on labeling thresholds used in validation:
#   WIN:     TP_300_PCT=0.20% or TP_600_PCT=0.30% achieved before SL
#   LOSS:    SL_PCT=-0.20% hit first
#   TIMEOUT: neither hit within 600s → estimated 0% gross
GROSS_RETURN_ESTIMATE = {
    "WIN":     0.25,   # midpoint between 0.20 and 0.30
    "LOSS":   -0.20,
    "TIMEOUT": 0.00,
}


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Could not load {path}: {e}")
        return None


def _passes(val, op, threshold):
    """Check a single feature condition."""
    if val is None:
        return False
    return val <= threshold if op == "<=" else val >= threshold


def simulate_condition_set(cond_name, conditions, raw_dist, warnings):
    """
    Filter raw_feature_distributions by entry conditions and compute outcomes.
    raw_dist structure: { "aggregate": { label: { feat: [vals] } },
                          "by_market": { market: { label: { feat: [vals] } } } }
    The lists within (label, market) groups are parallel (same snapshot order).
    """
    # Safely parse condition values from multiple possible formats:
    #   ("<=", -0.3891)  |  ["<=", -0.3891]
    #   {"op": "<=", "threshold": -0.3891}  |  {"operator": "<=", "value": -0.3891}
    NON_FEAT_KEYS = {"note"}
    feat_ops = {}
    for f, v in conditions.items():
        if f in NON_FEAT_KEYS:
            continue
        try:
            if isinstance(v, (tuple, list)) and len(v) == 2:
                op, th = v[0], v[1]
            elif isinstance(v, dict):
                op = v.get("op") or v.get("operator", "<=")
                th = v.get("threshold") if "threshold" in v else v.get("value", 0.0)
            else:
                warnings.append(
                    f"{cond_name}: unrecognised condition format for '{f}': {v!r}. Skipped."
                )
                continue
            feat_ops[f] = (str(op), float(th))
        except Exception as e:
            warnings.append(f"{cond_name}: failed to parse condition '{f}': {e}. Skipped.")


    by_market_dist = raw_dist.get("by_market", {})
    if not by_market_dist:
        warnings.append(f"{cond_name}: by_market distributions empty")
        return None

    all_pass = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0}
    all_total = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0}
    per_market = {}
    missing_features = set()

    for market, label_data in by_market_dist.items():
        m_pass = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0}
        m_total = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0}

        for lbl in ["WIN", "LOSS", "TIMEOUT"]:
            feat_data = label_data.get(lbl, {})

            # Check all required features are present
            for f in feat_ops:
                if f not in feat_data:
                    missing_features.add(f)

            # Find length of the shortest feature list (parallel arrays)
            lengths = [len(feat_data.get(f, [])) for f in feat_ops]
            if not lengths or min(lengths) == 0:
                continue
            n = min(lengths)

            feat_arrays = {f: feat_data[f] for f in feat_ops if f in feat_data}

            for i in range(n):
                m_total[lbl] += 1
                all_total[lbl] += 1
                passed = all(
                    _passes(feat_arrays[f][i], op, th)
                    for f, (op, th) in feat_ops.items()
                    if f in feat_arrays
                )
                if passed:
                    m_pass[lbl] += 1
                    all_pass[lbl] += 1

        trades = sum(m_pass.values())
        per_market[market] = {
            "trades":   trades,
            "WIN":      m_pass["WIN"],
            "LOSS":     m_pass["LOSS"],
            "TIMEOUT":  m_pass["TIMEOUT"],
            "total_evaluated": sum(m_total.values()),
            "pass_rate": trades / max(sum(m_total.values()), 1),
        }

    if missing_features:
        warnings.append(
            f"{cond_name}: features missing from raw_dist: {missing_features}. "
            "Re-run run_cross_market_reversal_validation.py to include them."
        )

    total_trades = sum(all_pass.values())
    total_evaluated = sum(all_total.values())

    if total_trades == 0:
        warnings.append(f"{cond_name}: 0 trades passed entry conditions.")
        return {
            "condition_set":   cond_name,
            "conditions":      {f: f"{op}{th}" for f, (op, th) in feat_ops.items()},
            "note":            conditions.get("note", ""),
            "trades":          0,
            "total_evaluated": total_evaluated,
            "pass_rate":       0.0,
            "judgement":       "NO_TRADES",
            "per_market":      per_market,
        }

    win_c   = all_pass["WIN"]
    loss_c  = all_pass["LOSS"]
    to_c    = all_pass["TIMEOUT"]
    win_rate    = win_c / total_trades
    loss_rate   = loss_c / total_trades
    timeout_rate = to_c / total_trades

    # Gross estimated return (label-based, no actual price path)
    gross_est = (
        win_rate  * GROSS_RETURN_ESTIMATE["WIN"] +
        loss_rate * GROSS_RETURN_ESTIMATE["LOSS"] +
        timeout_rate * GROSS_RETURN_ESTIMATE["TIMEOUT"]
    )

    # Per-cost-scenario net result
    cost_scenarios = {}
    for sl in SLIPPAGE_SCENARIOS:
        rt_cost = round_trip_cost(sl)
        net_est = gross_est - rt_cost
        cost_scenarios[f"slip_{sl:.2f}pct"] = {
            "slippage_pct":    sl,
            "fee_pct":         UPBIT_FEE_PCT,
            "round_trip_cost": round(rt_cost, 4),
            "gross_est_pct":   round(gross_est, 4),
            "net_est_pct":     round(net_est, 4),
            "positive":        net_est > 0,
        }

    # Market bias check
    market_bias_warning = None
    if per_market and total_trades > 0:
        top_m  = max(per_market, key=lambda m: per_market[m]["trades"])
        top_share = per_market[top_m]["trades"] / total_trades
        if top_share > 0.60:
            market_bias_warning = (
                f"{top_m} contributes {top_share:.0%} of trades. "
                "Result may not generalise across markets."
            )
            warnings.append(f"{cond_name}: {market_bias_warning}")

    return {
        "condition_set":     cond_name,
        "conditions":        {f: f"{op}{th}" for f, (op, th) in feat_ops.items()},
        "note":              conditions.get("note", ""),
        "trades":            total_trades,
        "win_count":         win_c,
        "loss_count":        loss_c,
        "timeout_count":     to_c,
        "total_evaluated":   total_evaluated,
        "pass_rate":         round(total_trades / max(total_evaluated, 1), 6),
        "win_rate":          round(win_rate,     4),
        "loss_rate":         round(loss_rate,    4),
        "timeout_rate":      round(timeout_rate, 4),
        "gross_est_pct":     round(gross_est, 4),
        "cost_scenario_results": cost_scenarios,
        "market_bias_warning":   market_bias_warning,
        "per_market":        per_market,
        "label_estimate_note": (
            "Gross return estimated from WIN/LOSS/TIMEOUT label thresholds only. "
            "Actual price paths not available. This is NOT a backtested PnL."
        ),
    }


def determine_judgement(sim_results, warnings):
    """Overall judgement across all condition sets."""
    if not sim_results:
        return "PAPER_SIM_FAILED"

    any_price_path_missing = any(
        r.get("trades", 0) == 0 for r in sim_results if r
    )
    if any_price_path_missing and all(
        not r or r.get("trades", 0) == 0 for r in sim_results
    ):
        return "PAPER_SIM_FAILED"

    # Check if at least one cost scenario is positive for at least one condition set
    any_positive = False
    for r in sim_results:
        if not r:
            continue
        for sc in r.get("cost_scenario_results", {}).values():
            if sc.get("positive"):
                any_positive = True
                break

    # Check market bias
    bias_warned = any("contribute" in w for w in warnings)

    if any_positive and not bias_warned:
        return "PAPER_SIM_POSITIVE_PRELIMINARY"
    elif any_positive and bias_warned:
        return "PAPER_SIM_WEAK"
    else:
        return "PAPER_SIM_WEAK"


def _build_txt(report):
    j = report.get("judgement", "UNKNOWN")
    lines = [
        "=" * 72,
        "  Reversal Paper Simulation with Cost Model",
        "  STATUS: PRELIMINARY SIMULATION — not a confirmed strategy",
        "=" * 72,
        f"Generated   : {report.get('generated_at', 'N/A')}",
        f"Judgement   : {j}",
        "",
        "[ Cost Model ]",
        f"  Upbit fee     : {UPBIT_FEE_PCT}%  (one-way)",
        f"  Slippage opts : {SLIPPAGE_SCENARIOS} % (one-way)",
        f"  Round-trip    : (fee + slippage) x 2",
        "",
        "[ Label-based Gross Estimate (per trade) ]",
        f"  WIN outcome est   : +{GROSS_RETURN_ESTIMATE['WIN']}%",
        f"  LOSS outcome est  : {GROSS_RETURN_ESTIMATE['LOSS']}%",
        f"  TIMEOUT outcome   : {GROSS_RETURN_ESTIMATE['TIMEOUT']}%",
        "  NOTE: These are label-threshold estimates. No actual price paths used.",
    ]

    for r in report.get("simulation_results", []):
        if not r:
            continue
        lines += [
            "",
            f"[ Condition Set: {r['condition_set']} ]",
            f"  Note       : {r.get('note', '')}",
        ]
        for feat, cond_str in r.get("conditions", {}).items():
            lines.append(f"  Entry cond : {feat} {cond_str}")

        lines += [
            f"  Trades     : {r.get('trades', 0):,}  (from {r.get('total_evaluated',0):,} evaluated)",
            f"  Pass rate  : {r.get('pass_rate', 0):.4%}",
            f"  WIN rate   : {r.get('win_rate', 0):.2%}",
            f"  LOSS rate  : {r.get('loss_rate', 0):.2%}",
            f"  TO rate    : {r.get('timeout_rate', 0):.2%}",
            f"  Gross est  : {r.get('gross_est_pct', 0):+.4f}%",
            "",
            "  [ Cost Scenario Results ]",
            f"  {'Scenario':<18} {'RT_cost':>8} {'Gross':>8} {'Net':>8} {'Positive':>10}",
            "  " + "-" * 54,
        ]
        for sc_name, sc in r.get("cost_scenario_results", {}).items():
            lines.append(
                f"  {sc_name:<18} {sc['round_trip_cost']:>8.4f} "
                f"{sc['gross_est_pct']:>8.4f} {sc['net_est_pct']:>8.4f} "
                f"{'YES' if sc['positive'] else 'NO':>10}"
            )

        bias_w = r.get("market_bias_warning")
        if bias_w:
            lines.append(f"  ! Market bias: {bias_w}")

        # Per-market top 5
        pm = r.get("per_market", {})
        if pm:
            lines += ["", "  [ Per-Market Trades (top 5) ]"]
            sorted_pm = sorted(pm.items(), key=lambda x: x[1]["trades"], reverse=True)
            for m, md in sorted_pm[:5]:
                lines.append(
                    f"    {m:<14} trades={md['trades']:>5}  "
                    f"W={md['WIN']:>4} L={md['LOSS']:>4} TO={md['TIMEOUT']:>4}  "
                    f"pass={md['pass_rate']:.3%}"
                )

    if report.get("warnings"):
        lines += ["", "[ Warnings ]"] + [f"  ! {w}" for w in report["warnings"][:8]]

    lines += [
        "",
        "=" * 72,
        "  PRELIMINARY PAPER SIMULATION ONLY.",
        "  No orders placed. No candidate or config files created.",
        "  Positive net_est does NOT confirm strategy profitability.",
        "  Full paper simulation with live price data is required next.",
        "=" * 72,
    ]
    return lines


def main():
    print("=" * 60)
    print(" Reversal Paper Simulation with Cost Model")
    print("=" * 60)

    valid = load_json(VALIDATION_JSON)
    if valid is None:
        print(f"[Error] Validation JSON not found: {VALIDATION_JSON}")
        _save_failed("Validation JSON missing")
        return

    raw_dist = valid.get("raw_feature_distributions")
    if not raw_dist or not raw_dist.get("by_market"):
        print("[Error] raw_feature_distributions.by_market not found.")
        print("        Re-run run_cross_market_reversal_validation.py first.")
        _save_failed("raw_feature_distributions missing — re-run validation")
        return

    hist = load_json(HISTOGRAM_JSON)   # optional, for context only
    warnings = []
    sim_results = []

    for cond_name, conditions in CONDITION_SETS.items():
        print(f"\n[Simulating] {cond_name} ...")
        r = simulate_condition_set(cond_name, conditions, raw_dist, warnings)
        sim_results.append(r)
        if r:
            print(f"  Trades: {r.get('trades', 0):,}  "
                  f"WIN={r.get('win_rate', 0):.1%}  "
                  f"LOSS={r.get('loss_rate', 0):.1%}")

    judgement = determine_judgement(sim_results, warnings)
    print(f"\nJudgement: {judgement}")

    report = {
        "generated_at":      datetime.now().isoformat(),
        "judgement":         judgement,
        "status":            "PRELIMINARY_SIMULATION_ONLY",
        "cost_model": {
            "upbit_fee_pct":    UPBIT_FEE_PCT,
            "slippage_options": SLIPPAGE_SCENARIOS,
            "round_trip_formula": "(fee + slippage) * 2",
        },
        "label_estimate_assumptions": {
            "WIN_gross_pct":     GROSS_RETURN_ESTIMATE["WIN"],
            "LOSS_gross_pct":    GROSS_RETURN_ESTIMATE["LOSS"],
            "TIMEOUT_gross_pct": GROSS_RETURN_ESTIMATE["TIMEOUT"],
            "note": (
                "Gross returns estimated from label thresholds "
                "(TP=0.20-0.30%, SL=-0.20%), NOT from actual price paths."
            ),
        },
        "simulation_results": sim_results,
        "warnings":          warnings,
        "note": (
            "PRELIMINARY PAPER SIMULATION ONLY. "
            "No orders placed. No candidate or config files were created or modified. "
            "Positive net_est does NOT confirm strategy profitability. "
            "Full paper simulation with actual price data is required."
        ),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(_build_txt(report)) + "\n")

    print(f"[Done] JSON : {OUT_JSON}")
    print(f"[Done] TXT  : {OUT_TXT}")


def _save_failed(reason):
    os.makedirs(OUT_DIR, exist_ok=True)
    result = {
        "generated_at": datetime.now().isoformat(),
        "judgement": "PAPER_SIM_FAILED",
        "reason": reason,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(f"Judgement: PAPER_SIM_FAILED\nReason: {reason}\n")
    print(f"[Error] PAPER_SIM_FAILED: {reason}")


if __name__ == "__main__":
    main()
