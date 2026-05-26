# Cross-Market Reversal Feature Discovery Plan

## 1. 개요 및 목적
본 작업은 특정 코인에만 종속되는 과최적화된 파라미터를 찾는 것을 배제하고, "업비트 KRW 전체 마켓"에 보편적으로 작용하는 Reversal(급락 후 반등) 엣지 피처(Feature)를 발굴하는 것을 목적으로 합니다. 
성공적인 반등과 실패한 반등을 사후적으로 라벨링하고, 진입 직전의 주문흐름(Orderflow) 및 호가창(Orderbook) 피처 간의 통계적 유의성(Effect Size)을 비교합니다.

## 2. 데이터 활용
- **입력**: `logs/experiments/master/reversal_edge_master_dataset.sqlite` (416만 건 규모)
- **방식**: SQLite 캐시를 직접 읽어들여 마켓별로 그룹화하고, 10초 단위로 스냅샷을 생성하여 미래 결과를 라벨링합니다.

## 3. 라벨링 기준 (미래 수익률 기반)
1. **WIN_300**: 300초 내 목표 상승(+0.20%) 도달 (사전 하락 -0.20% 터치 없음)
2. **WIN_600**: 600초 내 목표 상승(+0.30%) 도달 (사전 하락 -0.20% 터치 없음)
3. **LOSS**: 상승 도달 전 -0.20% 손절 터치
4. **TIMEOUT**: 제한시간 내 목표 변동 미도달

## 4. 탐색 피처 (Features)
- 단기 가격 변화율 (`recent_return_10s`, `recent_return_30s`, `recent_return_60s`)
- 단기 거래량 (`trade_volume_10s`, `trade_volume_30s`)
- 매도 압력 비율 (`sell_pressure_ratio_10s`, `sell_pressure_ratio_30s`)
- 매수 회복력 (`buy_recovery_ratio_10s`)
- 호가창 뎁스 변화 (`bid_depth_change`, `ask_depth_change`)
- 호가창 불균형 (`orderbook_imbalance`)
- 스프레드 및 회복률 (`spread_pct`, `spread_recovery`)
- 60초 변동성 (`volatility_60s`)

## 5. 판정 및 제약 조건
1. **마켓 편중 방지**: 피처의 통계적 유의성(Cohen's d)이 최소 3개 이상의 마켓에서 일관된 방향성으로 나타나야 합니다. 특정 1개 마켓에서만 나타난 피처는 배제합니다.
2. **후보군 채택 보수화**: Effect size의 절대값이 0.2를 넘지 못하는 약한 피처는 범용 엣지로 채택하지 않습니다.
3. **Candidate 자동 생성 금지**: 본 작업은 "탐색(Discovery)" 단계이며, 도출된 결과가 아무리 좋아도 자동으로 candidate나 config를 수정하지 않습니다.

## 6. 최종 판정 라벨
- `CROSS_MARKET_FEATURE_FOUND`: 3개 이상 마켓에서 공통된 유의미한 피처 발견
- `MARKET_CONCENTRATED`: 1~2개 마켓에 피처 효과가 편중됨
- `WEAK_FEATURES`: 유의미한 효과를 내는 피처 없음
- `NEED_MORE_DATA`: 표본(WIN/LOSS가 각 50건 이상인 마켓) 부족
