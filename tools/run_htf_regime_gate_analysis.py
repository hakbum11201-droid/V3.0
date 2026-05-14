"""
run_htf_regime_gate_analysis.py

HTF Regime Gate Analysis
여러 분석 결과를 종합하여 최종적인 진입 허용/차단(Gate) 여부를 판단합니다.
이 스크립트는 분석용이며 실제 Paper Runner의 실행을 막지 않습니다.
"""

import os
import json
from datetime import datetime

REPORTS_DIR = "reports/experiments"

def load_json(filename):
    filepath = os.path.join(REPORTS_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def main():
    print("============================================================")
    print(" HTF Regime Gate Analysis")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 1. Load dependencies
    htf = load_json("htf_regime_diagnostics_latest.json")
    holdout = load_json("independent_holdout_validation_latest.json")
    cost = load_json("cost_randomization_test_latest.json")
    deg = load_json("strategy_degradation_tracking_latest.json")
    
    # Extract values
    regime = htf.get("regime", "UNKNOWN")
    base_permission = htf.get("permission", "CAUTION")
    
    holdout_j = holdout.get("judgement", "NEED_MORE_DATA")
    cost_j = cost.get("final_judgement", "NEED_MORE_DATA")
    deg_j = deg.get("judgement", "NEED_MORE_DATA")
    
    # 2. Determine Base Gate from Regime
    if regime == "BULL":
        gate = "ALLOW"
    elif regime == "RANGE":
        gate = "ALLOW_PREFERRED"
    elif regime == "BEAR":
        gate = "RESTRICTED"
    elif regime == "CRASH":
        gate = "BLOCK"
    else:
        gate = "CAUTION"
        
    reason = [f"Base regime is {regime} -> {gate}"]
    
    # 3. Apply Modifiers
    # Cost Modifier
    if cost_j in ("FAILED", "FRAGILE_EDGE"):
        if gate == "ALLOW": gate = "ALLOW_PREFERRED"
        elif gate == "ALLOW_PREFERRED": gate = "RESTRICTED"
        elif gate in ("RESTRICTED", "CAUTION"): gate = "BLOCK"
        reason.append(f"Downgraded due to Cost Fragility ({cost_j})")
        
    # Degradation Modifier
    if deg_j in ("DEGRADED", "RISK_DEGRADED"):
        if gate in ("ALLOW", "ALLOW_PREFERRED", "CAUTION"):
            gate = "RESTRICTED"
        elif gate == "RESTRICTED":
            gate = "BLOCK"
        reason.append(f"Downgraded due to Strategy Degradation ({deg_j})")
        
    # Holdout Modifier
    if holdout_j == "FAILS_HOLDOUT":
        gate = "BLOCK"
        reason.append("BLOCKED due to failing Independent Holdout Validation")
    elif holdout_j == "PASSES_INDEPENDENT_HOLDOUT" and regime in ("RANGE", "BULL"):
        # Keep it or upgrade slightly if it was downgraded, but safely let's just note it
        if gate in ("RESTRICTED", "BLOCK"):
            gate = "ALLOW_PREFERRED" # restore
            reason.append("Restored to ALLOW_PREFERRED due to passing Holdout in favorable regime")
        else:
            reason.append("Holdout passed, maintaining favorable gate.")
            
    # Check if we lack too much data
    if holdout_j == "NEED_MORE_DATA" and cost_j == "NEED_MORE_DATA" and deg_j == "NEED_MORE_DATA":
        gate = "NEED_MORE_DATA"
        reason.append("Insufficient data across all validation steps.")
        
    # 4. Output Final Decision
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "htf_regime": regime,
        "htf_permission": base_permission,
        "holdout_judgement": holdout_j,
        "cost_judgement": cost_j,
        "degradation_judgement": deg_j,
        "final_gate": gate,
        "reason": " | ".join(reason),
        "safety_note": "이 결과는 실거래 승인이 아님. live.enabled=false 유지."
    }
    
    json_path = os.path.join(REPORTS_DIR, "htf_regime_gate_analysis_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "htf_regime_gate_analysis_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    txt_lines = [
        "============================================================",
        "  HTF Regime Gate Analysis Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[현재 시장 상태 및 기반 판단]",
        f" - HTF Regime: {regime}",
        f" - 기본 허용 수준: {base_permission}",
        "",
        "[다중 검증 도구 진단 결과]",
        f" - 독립 Holdout 결과 : {holdout_j}",
        f" - 비용 내성 결과    : {cost_j}",
        f" - 성과 악화 결과    : {deg_j}",
        "",
        "[최종 판단]",
        f" 🚪 최종 Gate 판단: {gate}",
        f" 📝 결정 사유: {final_summary['reason']}",
        "",
        "[다음 행동 제안]",
    ]
    
    if gate == "ALLOW":
        txt_lines.append(" - 안전합니다. 모든 시스템이 정상적으로 엣지를 포착할 수 있습니다.")
    elif gate == "ALLOW_PREFERRED":
        txt_lines.append(" - 양호합니다. 타임아웃 및 부분 손실에 유의하며 진행하십시오.")
    elif gate == "RESTRICTED":
        txt_lines.append(" - 제한적 허용 상태. 위험 관리에 집중하고 신규 진입 조건을 더 까다롭게 적용할 필요가 있습니다.")
    elif gate == "BLOCK":
        txt_lines.append(" - 진입 차단. 엣지가 붕괴되었거나 극단적인 하락장입니다. Paper 시스템의 로직을 전면 재점검하십시오.")
    elif gate == "CAUTION":
        txt_lines.append(" - 주의 상태. 시장의 방향성이 불확실하거나 데이터가 일부 누락되었습니다.")
    else:
        txt_lines.append(" - 데이터를 더 수집하십시오 (NEED_MORE_DATA).")
        
    txt_lines.extend([
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 이 결과는 분석용일 뿐, 실거래 승인이 아닙니다.",
        " 🚫 config 자동 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 사람 승인 전 tiny_live 금지",
        "------------------------------------------------------------"
    ])
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print(f"\n[Done] Final Gate: {gate}")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
