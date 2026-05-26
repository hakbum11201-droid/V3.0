"""
plan_top10_market_collection.py
Market Coverage Audit 결과를 바탕으로 Top 10 KRW 마켓의 데이터 수집 계획을 설계합니다.
"""
import os
import json
from datetime import datetime

import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

AUDIT_JSON = "reports/experiments/market_coverage_audit_latest.json"
OUT_DIR = "reports/experiments"
JSON_REPORT = os.path.join(OUT_DIR, "top10_market_collection_plan_latest.json")
TXT_REPORT = os.path.join(OUT_DIR, "top10_market_collection_plan_latest.txt")

# 수집 계획 기준
COLLECT_MARKETS_COUNT = 10
TARGET_HOURS = 72
CHUNK_MINUTES = 30
CHUNKS_PER_MARKET = int((TARGET_HOURS * 60) / CHUNK_MINUTES)
TOTAL_CHUNKS = COLLECT_MARKETS_COUNT * CHUNKS_PER_MARKET

def main():
    print("=" * 60)
    print(" Top 10 KRW Market Collection Plan Generator")
    print("=" * 60)

    if not os.path.exists(AUDIT_JSON):
        print(f"[Error] Audit result not found at {AUDIT_JSON}. Run RUN_AUDIT_MARKET_COVERAGE.bat first.")
        return

    with open(AUDIT_JSON, "r", encoding="utf-8") as f:
        audit = json.load(f)

    good_count = audit.get("good_count", 0)
    audit_judgement = audit.get("judgement", "UNKNOWN")

    # 판정
    if good_count >= 5:
        judgement = "READY_FOR_FEATURE_DISCOVERY"
    elif good_count >= 3:
        # 그래도 약간 부족할 수 있으므로 72시간 수집 제안
        judgement = "NEED_TOP10_72H_COLLECTION"
    else:
        # 심각하게 부족하므로 7일 제안할 수도 있지만 기본은 72시간으로 시작하고 확장 가능성을 열어둠
        judgement = "RECOMMEND_7D_COLLECTION"

    # 수집 목표
    target_hrs = 24 * 7 if judgement == "RECOMMEND_7D_COLLECTION" else TARGET_HOURS
    total_chk = COLLECT_MARKETS_COUNT * int((target_hrs * 60) / CHUNK_MINUTES)

    plan = {
        "generated_at": datetime.now().isoformat(),
        "audit_judgement": audit_judgement,
        "good_markets_count": good_count,
        "judgement": judgement,
        "collection_target": {
            "markets_count": COLLECT_MARKETS_COUNT,
            "target_hours": target_hrs,
            "chunk_minutes": CHUNK_MINUTES,
            "total_chunks": total_chk,
            "method": "chunk_based_with_resume"
        },
        "post_collection_steps": [
            "RUN_BUILD_MASTER_VALIDATION_DATASET.bat",
            "RUN_BUILD_MASTER_DATASET_CACHE.bat",
            "RUN_AUDIT_MARKET_COVERAGE.bat",
            "RUN_DISCOVER_CROSS_MARKET_REVERSAL_FEATURES.bat",
            "RUN_CROSS_MARKET_REVERSAL_VALIDATION.bat",
            "RUN_AUTO_RESEARCH_REPORT.bat"
        ]
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_REPORT, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    lines = [
        "=" * 72,
        " Top 10 KRW Market Collection Plan Report",
        "=" * 72,
        f"생성 시각  : {datetime.now().isoformat()}",
        f"현재 상태  : {audit_judgement} (GOOD 마켓: {good_count}개)",
        f"최종 판정  : {judgement}",
        "",
        "[ 권장 수집 스펙 (Data Collection Target) ]",
        f"- 수집 마켓 수 : 상위 {COLLECT_MARKETS_COUNT}개 KRW 마켓 (수집 시작 시점 Top 10 고정)",
        f"- 권장 수집 시간: {target_hrs}시간",
        f"- Chunk 단위   : {CHUNK_MINUTES}분",
        f"- 총 Chunk 개수: {total_chk}개 (실패 시 해당 Chunk만 재시도)",
        f"- 예상 산출물  : data/raw/chunked/ (각 Chunk별 jsonl 저장 권장)",
        "",
        "[ 수집 완료 후 실행 프로세스 (Post-Collection Pipeline) ]",
        "1. RUN_BUILD_MASTER_VALIDATION_DATASET.bat (Master Dataset 생성)",
        "2. RUN_BUILD_MASTER_DATASET_CACHE.bat (SQLite 캐시 업데이트)",
        "3. RUN_AUDIT_MARKET_COVERAGE.bat (새로운 데이터 커버리지 감사)",
        "4. RUN_DISCOVER_CROSS_MARKET_REVERSAL_FEATURES.bat (공통 피처 재탐색)",
        "5. RUN_CROSS_MARKET_REVERSAL_VALIDATION.bat (전략 공통 엣지 재검증)",
        "6. RUN_AUTO_RESEARCH_REPORT.bat (최종 리포트 생성)",
        "",
        "⚠️ 경고 (Warning)",
        "위 파이프라인에서 '공통 피처'가 최종 확인되기 전까지는 절대 config.json을 수정하거나",
        "실거래(live.enabled=true)를 활성화해서는 안 됩니다. 기존 candidate 파일도 덮어쓰지 마십시오."
    ]

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[Done] JSON: {JSON_REPORT}")
    print(f"[Done] TXT: {TXT_REPORT}")
    print(f"Judgement: {judgement}")

if __name__ == "__main__":
    main()
