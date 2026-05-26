# Top 10 KRW Market Collection Plan

## 1. 개요 및 목적
현재 보유 중인 Master Dataset을 `Market Coverage Audit`으로 감사한 결과, "업비트 KRW 전체 마켓 공통 Reversal Edge"를 도출하고 검증하기에는 유효 데이터(마켓 수, WIN/LOSS 라벨 수 등)가 편중되어 있거나 턱없이 부족함을 확인했습니다. 
따라서, 특정 코인 1~2개에만 과최적화되는 현상을 원천적으로 차단하고, 전체 마켓을 관통하는 보편적 엣지를 찾기 위해, 거래대금 상위 Top 10 마켓에 대한 신규 데이터 수집 프로세스를 설계합니다.

## 2. 수집 대상 원칙
- **Top 10 유지**: 데이터 수집을 시작하는 시점(Start-time)의 업비트 KRW 마켓 거래대금 상위 10개 코인 목록(Manifest)을 확정하고, 전체 수집 기간 동안 이를 고정하여 수집합니다.
- **기존 코인 포함 허용**: 기존에 수집했던 BTC, ETH, SOL, XRP 등이 Top 10에 있다면 그대로 포함하여 연속된 데이터를 확보합니다.

## 3. 안정성 높은 Chunk 기반 수집 설계
단일 스크립트로 72시간을 연속 수집할 경우, 네트워크 장애, API 제한, OS 재부팅 등으로 데이터 전체가 유실될 위험이 큽니다.
- **Chunk 단위 분할**: 30분(또는 1시간) 단위의 Chunk로 분할 수집. (72시간 = 144개 Chunk)
- **독립적 저장**: 각 Chunk는 분리된 `jsonl` 파일로 `data/raw/chunked/` 에 저장됩니다.
- **재개(Resume) 기능**: 스크립트 중단 시, 완료된 Chunk는 Skip하고 실패/미완료 Chunk부터 자동으로 이어서 수집(Resume)합니다.

## 4. 권장 수집 목표 및 판정 연계
- Audit 결과 유효 마켓(GOOD)이 5개 미만인 현재, **기본 72시간 수집**을 제안하며, 엣지 신뢰도가 더욱 필요할 경우 **최장 7일(168시간)**까지 확장 수집을 권장합니다.

## 5. 수집 완료 후 실행 파이프라인
데이터 수집이 완료된 이후에는 반드시 아래 순서대로 스크립트를 재실행하여 시스템 전체에 데이터를 반영해야 합니다.
1. `RUN_BUILD_MASTER_VALIDATION_DATASET.bat` (청크 병합 및 Master Dataset 생성)
2. `RUN_BUILD_MASTER_DATASET_CACHE.bat` (SQLite 캐시 업데이트)
3. `RUN_AUDIT_MARKET_COVERAGE.bat` (수집된 데이터의 Coverage 재감사)
4. `RUN_DISCOVER_CROSS_MARKET_REVERSAL_FEATURES.bat` (전체 마켓 공통 피처 재탐색)
5. `RUN_CROSS_MARKET_REVERSAL_VALIDATION.bat` (공통 피처 기반 엣지 재검증)

## 6. ⚠️ 절대 금지 사항
- **실거래(live.enabled) 전환 금지**: 수집 중이나 완료 직후에도 자동으로 실거래 전환 기능은 추가되지 않습니다.
- **Config/Candidate 수정 보류**: 파이프라인의 5번 항목(`VALIDATION`)까지 모두 성공적으로 통과하여 명확한 "공통 피처"가 입증되기 전까지는 기존 `candidate` 파일이나 `config.json`을 수정해서는 안 됩니다.
