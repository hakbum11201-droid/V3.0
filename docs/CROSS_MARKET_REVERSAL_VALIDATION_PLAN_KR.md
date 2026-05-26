# Cross-Market Reversal Edge Validation Plan

## 1. 개요 및 목적
- 본 검증은 **전체 마켓(ALL MARKETS)**에서 통용되는 Reversal Edge 공통 조건을 찾는 것이 목적이다.
- 특정 코인(예: KRW-SOL) 1개에만 과최적화된 결과를 찾아내는 작업이 아님을 명확히 한다.
- 특정 코인 1개의 최적값이 아니라, 전체 시장의 하락 후 반등(Rebound) 공통 패턴을 캡처해야 한다.

## 2. 검증 주요 원칙
1. **전체 마켓 통합 평가**: 마켓별 최적화가 아닌 전체 마켓 1순위 평가
2. **SOL_ONLY 결과 제외**: 기존 실험에서 SOL에 편중된 결과를 보였으므로, SOL_ONLY 결과는 최종 유망 후보 판정(UNIVERSAL_PROMISING)에서 제외한다.
3. **단일 Top Exit 기준 판정 금지**: rankings 전체를 확인하며, 가장 일관적인 조건을 채택한다.
4. **수익처럼 보이게 만드는 Cost 조작 금지**: `cost_floor`를 낮춰 억지로 수익이 나는 것처럼 보이게 한 결과는 진정한 전략 개선(Edge)이 아니라고 판단한다.

## 3. 핵심 판정 기준 (UNIVERSAL_PROMISING)
아래의 모든 조건을 만족해야 범용 엣지(UNIVERSAL_PROMISING)로 인정한다.
1. 전체 평가된 거래 수(Evaluated Trades) >= 100건
2. 유효 거래가 발생한 마켓 수 >= 3개
3. 특정 1개 마켓의 거래 비중 <= 50%
4. 전체 Avg Net PnL (cost 0.20% 기준) > 0
5. Fold(시간 단위 분할) 분석 시 과반수 이상의 Fold에서 Net PnL > 0

## 4. 데이터 셋 활용 방안
- Master Dataset(약 416만 rows) 활용
- Fold 분할 (24h 단위) 진행으로 시간대별 일관성(Inconsistency by fold) 판별

## 5. 제약 및 안전 수칙 (Safety Checks)
- 기존 candidate 덮어쓰기 금지 (`reversal_edge_candidate_v2_from_36h.json`)
- 시스템 config 수정 금지
- 실거래 자동 전환(live.enabled) 엄격히 금지
- 결과가 저조할 경우 "억지 후보" 채택 대신 "공통 엣지 없음"으로 명확히 보고할 것.
