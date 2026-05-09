import json
import os
from typing import Any, Dict

def build_config_experiments(
    base_config_path: str,
    diagnostics_path: str,
    output_dir: str
):
    summary_path = "reports/config_experiment_summary.txt"
    
    if not os.path.exists(base_config_path):
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("실패: 기본 설정 파일을 찾을 수 없습니다.\n")
        return

    with open(base_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Check if target key exists
    if "microstructure" not in config or "min_trade_value_3s" not in config["microstructure"]:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("실패: 기준 key(microstructure.min_trade_value_3s) 확인 필요\n")
        return

    os.makedirs(output_dir, exist_ok=True)
    
    experiments = {
        "conservative": 3000000,
        "moderate": 1500000,
        "aggressive": 750000
    }
    
    generated_files = []
    
    for name, value in experiments.items():
        new_config = json.loads(json.dumps(config)) # Deep copy
        new_config["microstructure"]["min_trade_value_3s"] = value
        
        file_path = os.path.join(output_dir, f"config_{name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        generated_files.append((name, value, file_path))

    # Write summary
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=== Config 실험 후보 생성 요약 ===\n\n")
        f.write(f"기본 설정 파일: {base_config_path}\n")
        f.write(f"변경 대상 Key: microstructure.min_trade_value_3s\n")
        f.write(f"기존 설정값: {config['microstructure']['min_trade_value_3s']}\n\n")
        
        f.write("생성된 후보 목록:\n")
        for name, val, path in generated_files:
            f.write(f"- [{name}] {val:,} KRW (경로: {path})\n")
            
        f.write("\n비고: LOW_VOLUME 진단 결과를 바탕으로 거래량 기준을 단계적으로 완화한 설정들입니다.\n")
        f.write("실제 config/config.json은 수정되지 않았으므로, 실험이 필요하면 수동으로 복사하여 사용하십시오.\n")

    return {
        "ok": True,
        "generated_count": len(generated_files),
        "summary_path": summary_path
    }

def run_config_experiment_builder(
    base_config: str,
    diagnostics: str,
    output_dir: str
):
    result = build_config_experiments(base_config, diagnostics, output_dir)
    print(f"Config experiments built. Summary at {result['summary_path']}")
    return result
