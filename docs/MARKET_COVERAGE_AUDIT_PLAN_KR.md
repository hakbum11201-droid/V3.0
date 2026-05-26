# Market Coverage Audit Plan

## 1. 개요 및 목적
기존의 Cross-Market Feature Discovery 작업 결과, 통계적 유의성을 검증할 수 있는 수준의 데이터(WIN/LOSS 라벨 각각 50개 이상)를 확보한 마켓이 KRW-SOL, KRW-XRP, KRW-BTC 등 3개뿐이었습니다. 
이러한 상태로는 "업비트 KRW 마켓 전체 공통 엣지"라고 결론 내릴 수 없으므로, 현재 Master Dataset에 포함된 모든 마켓의 커버리지(데이터 량, 기간, 라벨 수)를 정확히 감사(Audit)하여 향후 수집 계획을 세우는 것이 목적입니다.

## 2. 검증 항목
1. **Row Count**: 마켓별 누적 데이터 행 수 (Trade 및 Orderbook)
2. **Duration**: 첫 기록부터 마지막 기록까지의 시간 차이(시간 단위)
3. **Snapshot Count**: 10초 단위로 쪼갰을 때 생성 가능한 유효 스냅샷 수
4. **Label Distribution**: 300초/600초 기준 성공(WIN), 실패(LOSS), 시간초과(TIMEOUT) 발생 빈도

## 3. 평가 등급 (Status)
- `GOOD`: 총 row 10,000 이상, 기간 12시간 이상, WIN/LOSS 최소 1회 이상 발생, 스냅샷 1,000개 이상.
- `WEAK`: 데이터는 있으나 GOOD 기준 중 하나 이상을 충족하지 못함 (주로 시간 부족 또는 라벨 부족).
- `UNUSABLE`: 총 row 1,000 미만이거나 Trade/Orderbook 중 하나가 100개 미만으로 분석 불가능.
- `MISSING`: SQLite 캐시에 해당 마켓 데이터가 아예 없음.

## 4. 최종 판정 (Judgement)
전체 마켓 공통 피처를 찾으려면 최소 5개 이상의 `GOOD` 마켓이 필요합니다.
- `COVERAGE_OK`: `GOOD` 마켓 5개 이상
- `COVERAGE_WEAK`: `GOOD` 마켓 3~4개 (특정 테마 코인에 편중될 위험 존재)
- `COVERAGE_INSUFFICIENT`: `GOOD` 마켓 1~2개
- `NEED_TOP10_COLLECTION`: 0개 (기능을 제대로 검증하기 위해 전면 수집 필요)

## 5. 제약 사항
본 Audit은 감사(Read-only) 도구일 뿐, 데이터를 조작하거나 필터를 고의로 낮춰 `GOOD` 마켓 개수를 늘리지 않습니다. 있는 그대로의 데이터를 평가합니다.
