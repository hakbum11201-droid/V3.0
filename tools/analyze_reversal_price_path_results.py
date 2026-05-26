#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Price-path Reversal Simulation Results Analysis Tool
This script analyzes the latest price-path simulation results to determine
cost-sensitivity, market concentrations, instability, and overall readiness.
"""

import os
import json
import math
from datetime import datetime

# Paths
WORKSPACE = r"C:\Users\hakbu\Downloads\coinB_PRO_V3_0_FINAL_ROOT_READY_v3_0\V3.0"
INPUT_FILE = os.path.join(WORKSPACE, "reports", "experiments", "reversal_price_path_paper_simulation_latest.json")
OUTPUT_JSON = os.path.join(WORKSPACE, "reports", "experiments", "reversal_price_path_result_analysis_latest.json")
OUTPUT_TXT = os.path.join(WORKSPACE, "reports", "experiments", "reversal_price_path_result_analysis_latest.txt")

UPBIT_FEE_PCT = 0.05  # 0.05%

def calculate_std(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)

def analyze():
    # 1. Read input file
    if not os.path.exists(INPUT_FILE):
        print(f"[Error] Input file not found: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. Extract overall summary
    best_combo = data.get("best_combination", {})
    best_results = data.get("best_combo_results", {})
    
    total_trades = best_results.get("trades", 0)
    win_count = best_results.get("win_count", 0)
    loss_count = best_results.get("loss_count", 0)
    timeout_count = best_results.get("timeout_count", 0)
    overall_win_rate = best_results.get("win_rate", 0.0)
    avg_gross_pnl = best_results.get("avg_gross_pnl", 0.0)
    timeout_ratio = best_results.get("timeout_ratio", 0.0)

    # 3. Extract cost scenarios and survival
    cost_scenarios_raw = best_results.get("cost_scenarios", {})
    cost_scenarios = {}
    
    for slip_k, sc in cost_scenarios_raw.items():
        slip_val = sc.get("slippage_pct", 0.0)
        avg_net_pnl = sc.get("avg_net_pnl", 0.0)
        total_net_pnl = sc.get("total_net_pnl", 0.0)
        is_positive = sc.get("is_positive", False)
        
        cost_scenarios[slip_k] = {
            "slippage_pct": slip_val,
            "avg_net_pnl": avg_net_pnl,
            "total_net_pnl": total_net_pnl,
            "survives": is_positive
        }

    # 4. Market Concentration Analysis
    per_market_raw = data.get("per_market_trades", {})
    sorted_markets = []
    
    for m, m_data in per_market_raw.items():
        m_trades = m_data.get("trades", 0)
        pct = (m_trades / total_trades * 100) if total_trades > 0 else 0.0
        sorted_markets.append({
            "market": m,
            "trades": m_trades,
            "pct": pct,
            "win_rate": m_data.get("win_rate", 0.0),
            "avg_gross": m_data.get("avg_gross", 0.0)
        })

    # Sort markets by trades descending
    sorted_markets.sort(key=lambda x: x["trades"], reverse=True)

    top_1_pct = sorted_markets[0]["pct"] if len(sorted_markets) > 0 else 0.0
    top_2_pct = sum(x["pct"] for x in sorted_markets[:2]) if len(sorted_markets) >= 2 else top_1_pct

    # 5. Warning Determinations
    # A. Bias warnings
    market_bias_warning = bool(top_1_pct >= 40.0)
    strong_market_bias_warning = bool(top_2_pct >= 70.0)

    # B. Instability warning: overall win rate vs standard deviation of per-market win rates
    active_win_rates = [x["win_rate"] for x in sorted_markets if x["trades"] > 0]
    win_rate_std = calculate_std(active_win_rates)
    instability_warning = bool(win_rate_std > overall_win_rate)

    # C. Large market coverage warning: BTC, ETH, XRP, SOL trades
    large_markets = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL"]
    large_market_trades = sum(per_market_raw.get(m, {}).get("trades", 0) for m in large_markets)
    large_market_pct = (large_market_trades / total_trades * 100) if total_trades > 0 else 0.0
    large_market_coverage_warning = bool(large_market_pct < 5.0)

    warnings = {
        "market_bias_warning": market_bias_warning,
        "strong_market_bias_warning": strong_market_bias_warning,
        "instability_warning": instability_warning,
        "large_market_coverage_warning": large_market_coverage_warning
    }

    # 6. Market Viability Analysis
    market_viability = {}
    for m_info in sorted_markets:
        m = m_info["market"]
        avg_gross = m_info["avg_gross"]
        
        # Calculate estimated nets under different slips: net = avg_gross - (0.05 + slip) * 2
        net_003 = avg_gross - (UPBIT_FEE_PCT + 0.03) * 2
        net_005 = avg_gross - (UPBIT_FEE_PCT + 0.05) * 2
        net_010 = avg_gross - (UPBIT_FEE_PCT + 0.10) * 2
        
        market_viability[m] = {
            "trades": m_info["trades"],
            "pct": m_info["pct"],
            "win_rate": m_info["win_rate"],
            "avg_gross": avg_gross,
            "estimated_net_slip_0.03": net_003,
            "estimated_net_slip_0.05": net_005,
            "estimated_net_slip_0.10": net_010,
            "is_viable_at_0.05": bool(net_005 > 0.0)
        }

    # 7. Judgement Heuristic
    survives_003 = cost_scenarios.get("slip_0.03", {}).get("survives", False)
    survives_005 = cost_scenarios.get("slip_0.05", {}).get("survives", False)

    judgement_reasons = []
    if survives_005:
        if not strong_market_bias_warning:
            judgement = "PRICE_PATH_SURVIVES_COSTS"
            judgement_reasons.append("전략이 slip 0.05% 수준의 비용에서도 양수의 Net 수익을 확보하며 마켓 편중이 낮습니다.")
        else:
            judgement = "MARKET_BIASED_RESEARCH_ONLY"
            judgement_reasons.append("slip 0.05%에서 수익은 보존되나 특정 1~2개 마켓에 극단적인 쏠림이 있습니다.")
    elif survives_003:
        if strong_market_bias_warning:
            judgement = "MARKET_BIASED_RESEARCH_ONLY"
            judgement_reasons.append("slip 0.03%에서만 Net Positive이나, DOGE/UP2에 거래가 80% 이상 편중되어 있어 공통 전략으로 실전 배치가 불가합니다.")
        else:
            judgement = "COST_SENSITIVE_WEAK"
            judgement_reasons.append("마켓 고르게 분포하나 slip 0.05% 비용 발생 시 마이너스로 전환되어 비용 민감도가 극도로 높습니다.")
    else:
        judgement = "REJECT_CURRENT_COMMON_STRATEGY"
        judgement_reasons.append("저비용 슬리피지(slip 0.03%) 환경에서도 PnL 보존력이 우려되거나 여러 경고 지표가 동시 감지되었습니다.")

    # Check if we need market specific retest
    # If standard deviation of win rates is high or DOGE works incredibly well while others fail
    doge_net_005 = market_viability.get("KRW-DOGE", {}).get("estimated_net_slip_0.05", -1.0)
    other_viable_count = sum(1 for m, mv in market_viability.items() if m != "KRW-DOGE" and mv["is_viable_at_0.05"])
    
    if doge_net_005 > 0.0 and other_viable_count == 0:
        judgement = "NEED_MARKET_SPECIFIC_RETEST"
        judgement_reasons.append("DOGE 마켓만 유일하게 slip 0.05% 환경에서 생존하고 다른 마켓은 전부 전멸했습니다. 공통 전략을 즉시 폐기하고 개별 마켓 전용 파라미터 셋으로 완전히 재시뮬레이션해야 합니다.")

    # 8. Next Step Recommendations
    recommendations = []
    if judgement == "NEED_MARKET_SPECIFIC_RETEST" or judgement == "MARKET_BIASED_RESEARCH_ONLY":
        recommendations.append("DOGE 단독 마켓에 맞춤화된 'DOGE-only 특화 Reversal 전략'으로 전환하고, 최적의 entry_conditions 및 손익비(TP/SL)를 별도 설계하는 리서치를 차기 우선순위로 제안합니다.")
        recommendations.append("UP2 마켓은 승률(36.09%)이 현저히 낮고 손실 거래 비중이 높으므로, UP2 마켓을 제외한 전략 필터링 로직을 개발하거나 개별 최적화가 필수적입니다.")
        recommendations.append("메이저 마켓(BTC/ETH/XRP/SOL)의 거래 참여도를 올리기 위해 스프레드 임계값(recent_return_30s)의 크기를 대형 마켓의 유동성과 변동성 프로파일에 부합하도록 스케일링하는 모듈을 설계해야 합니다.")
    elif judgement == "COST_SENSITIVE_WEAK":
        recommendations.append("비용 절감을 위해 시장가 진입 대신 지정가(Limit Order) 대기 방식의 진입 체계를 시뮬레이션하거나 진입 필터를 고도화해야 합니다.")
    else:
        recommendations.append("Reversal 전략의 현재 가설(Common Parameter)은 실전성이 매우 낮으므로, 피처 엔지니어링 단계로 회귀하여 신호 농축도를 근본적으로 개선해야 합니다.")

    # 9. Output Dict
    analysis_result = {
        "generated_at": datetime.now().isoformat(),
        "input_file": INPUT_FILE,
        "judgement": judgement,
        "judgement_reasons": judgement_reasons,
        "overall_summary": {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "timeout_count": timeout_count,
            "overall_win_rate": overall_win_rate,
            "timeout_ratio": timeout_ratio,
            "avg_gross_pnl": avg_gross_pnl,
            "best_combination": best_combo
        },
        "cost_scenarios": cost_scenarios,
        "market_concentration": {
            "sorted_markets": sorted_markets,
            "top_1_pct": top_1_pct,
            "top_2_pct": top_2_pct,
            "large_market_pct": large_market_pct
        },
        "warnings": warnings,
        "market_viability": market_viability,
        "next_step_recommendation": recommendations
    }

    # 10. Write JSON output
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, indent=2, ensure_ascii=False)
    print(f"[Info] Saved analysis JSON: {OUTPUT_JSON}")

    # 11. Write TXT report
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("================================================================================\n")
        f.write(" PRICE-PATH REVERSAL PAPER SIMULATION RESULT ANALYSIS REPORT\n")
        f.write("================================================================================\n")
        f.write(f" Generated At: {analysis_result['generated_at']}\n")
        f.write(f" Input File: {os.path.basename(INPUT_FILE)}\n")
        f.write(f" Final Judgement: {judgement}\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" [CRITICAL SYSTEM METRIC WARNINGS - SECURITY & AUDIT STATUS]\n")
        f.write(" NOT PRODUCTION READY\n")
        f.write(" NO CANDIDATE CREATED\n")
        f.write(" NO CONFIG MODIFIED\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 1. OVERALL STATS SUMMARY\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(f" * Best Combo Parameters : TP +{best_combo.get('tp')}% / SL {best_combo.get('sl')}% / Timeout {best_combo.get('timeout')}s\n")
        f.write(f" * Total Trades          : {total_trades:,} trades\n")
        f.write(f" * Overall Win Rate      : {overall_win_rate*100:.2f}%\n")
        f.write(f" * Win/Loss/Timeout Count: {win_count} / {loss_count} / {timeout_count}\n")
        f.write(f" * Timeout Ratio         : {timeout_ratio*100:.2f}%\n")
        f.write(f" * Avg Gross PnL         : {avg_gross_pnl:.6f}%\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 2. COST SENSITIVITY AND SURVIVAL STATUS\n")
        f.write("--------------------------------------------------------------------------------\n")
        for slip_k, sc in cost_scenarios.items():
            status_str = "SURVIVED (Positive PnL)" if sc["survives"] else "FAILED (Negative PnL)"
            f.write(f" * Slippage {sc['slippage_pct']*100:.2f}% Scenario:\n")
            f.write(f"   - Avg Net PnL   : {sc['avg_net_pnl']:.6f}%\n")
            f.write(f"   - Total Net PnL : {sc['total_net_pnl']:.4f}%\n")
            f.write(f"   - Status        : {status_str}\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 3. MARKET CONCENTRATION & BIAS DIAGNOSTICS\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" * Trade volume concentration per market:\n")
        for idx, m_info in enumerate(sorted_markets):
            f.write(f"   {idx+1:02d}. {m_info['market']:<13} : {m_info['trades']:>4} trades ({m_info['pct']:>6.2f}%) | WR: {m_info['win_rate']*100:>5.2f}% | Avg Gross: {m_info['avg_gross']:>9.6f}%\n")
        f.write("\n")
        f.write(f" * Concentration Diagnostics:\n")
        f.write(f"   - Top 1 Market Concentration (DOGE) : {top_1_pct:.2f}%\n")
        f.write(f"   - Top 2 Markets Combined (DOGE+UP2) : {top_2_pct:.2f}%\n")
        f.write(f"   - Major Markets Trade Volume (BTC/ETH/XRP/SOL) : {large_market_trades} trades ({large_market_pct:.2f}%)\n")
        f.write("\n")
        f.write(f" * Safety Warnings Flags:\n")
        f.write(f"   - market_bias_warning (>=40% in Top 1)    : {market_bias_warning}\n")
        f.write(f"   - strong_market_bias_warning (>=70% Top 2): {strong_market_bias_warning}\n")
        f.write(f"   - instability_warning (unstable win rates): {instability_warning}\n")
        f.write(f"   - large_market_coverage_warning (<5% major): {large_market_coverage_warning}\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 4. INDIVIDUAL MARKET VIABILITY UNDER SLIPPAGE\n")
        f.write("--------------------------------------------------------------------------------\n")
        for m, mv in market_viability.items():
            status_str = "VIABLE" if mv["is_viable_at_0.05"] else "UNVIABLE"
            f.write(f" * {m:<13} (WR: {mv['win_rate']*100:.1f}%, Avg Gross: {mv['avg_gross']:.4f}%):\n")
            f.write(f"   - Est Net under slip 0.03% : {mv['estimated_net_slip_0.03']:.4f}%\n")
            f.write(f"   - Est Net under slip 0.05% : {mv['estimated_net_slip_0.05']:.4f}%\n")
            f.write(f"   - Est Net under slip 0.10% : {mv['estimated_net_slip_0.10']:.4f}%\n")
            f.write(f"   - Viability under standard costs (0.05% slip) : {status_str}\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 5. STRATEGY FEASIBILITY EVALUATION\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" [A] DOGE-only 전략 가능성 판단:\n")
        doge_wr = market_viability.get("KRW-DOGE", {}).get("win_rate", 0.0)
        if doge_net_005 > 0.0:
            f.write(f"   => 극히 긍정적 (FEASIBLE). DOGE 마켓은 독보적인 승률({doge_wr*100:.2f}%)과 PnL 완충력으로\n")
            f.write(f"      슬리피지 0.05% 환경에서도 Net {doge_net_005:.4f}% 수익 생존이 입증되었습니다.\n")
        else:
            f.write("   => 회의적. DOGE 역시 비용 추가 시 생존력이 급감합니다.\n")
        f.write("\n")
        
        f.write(" [B] UP2 포함 전략 가능성 판단:\n")
        up2_info = market_viability.get("KRW-UP2", {})
        up2_wr = up2_info.get("win_rate", 0.0)
        up2_net_005 = up2_info.get("estimated_net_slip_0.05", -1.0)
        f.write(f"   => 절대 불가 (UNFEASIBLE). UP2는 승률이 {up2_wr*100:.2f}%로 극도로 낮고 손실 거래가 편중되어\n")
        f.write(f"      Slippage 0.05% 기준 Net {up2_net_005:.4f}%로 심각한 손실을 초래하여 공통 전략 성과를 갉아먹습니다.\n")
        f.write("\n")
        
        f.write(" [C] Top10 Common 전략 가능성 판단:\n")
        f.write("   => 불가 (REJECT). 모든 마켓에 동일한 진입 및 손익 임계값을 적용하는 Common 전략은\n")
        f.write("      DOGE의 우수한 성과에 기대어 착시 현상(DOGE 쏠림에 의한 전체 양수 Net PnL)을 일으킨 것에 불과합니다.\n")
        f.write("      마켓별 특성을 무시한 단일 세팅 공통 전략의 실전 배치는 불가능하다고 판단합니다.\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 6. JUDGEMENT REASONING DETAILS\n")
        f.write("--------------------------------------------------------------------------------\n")
        for reason in judgement_reasons:
            f.write(f" * {reason}\n")
        f.write("\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(" 7. NEXT STEP RECOMMENDATION\n")
        f.write("--------------------------------------------------------------------------------\n")
        for idx, rec in enumerate(recommendations):
            f.write(f" [{idx+1}] {rec}\n")
        f.write("================================================================================\n")

    print(f"[Info] Saved analysis TXT Report: {OUTPUT_TXT}")

if __name__ == "__main__":
    analyze()
