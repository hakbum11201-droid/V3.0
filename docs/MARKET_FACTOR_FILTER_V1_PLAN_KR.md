# Market Factor Filter v1 실험 설계 문서

## 1. 문제 정의
- **오더플로우 지표의 한계**: 단순히 `imbalance`나 `price_chg` 점수만으로는 0.20%의 거래 비용을 극복할 수 있는 수익 구간을 정밀하게 골라내지 못함.
- **최적화 실패**: 11만 개의 가중치 조합을 탐색했음에도 불구하고, 모든 시장 조건에서 일관된 Net PnL 양수를 기록하는 설정은 존재하지 않음.
- **진단 결과**: `market-factor-diagnostics` 분석 결과, 수익 기회는 특정 장세(고변동성, 강한 불균형 지속, 호가 지지)에만 집중되어 있음.
- **결론**: 거래 전략을 고도화하기 전, **"거래할 장세와 쉬어야 할 장세"**를 먼저 구분하는 상위 필터링 계층이 필수적임.

## 2. Market Factor Filter v1 목적
- **활성 장세 선별**: `volatility_300s`, `imbalance_300s` 등을 기준으로 가격 움직임의 잠재력이 충분한 장세만 통과시킴.
- **노이즈 제거**: 승률이 극히 낮은 저변동성/횡보 구간을 원천 차단하여 불필요한 비용 발생(Churn)을 방지.
- **상위 게이트**: 이 필터는 개별 진입 신호가 아니라, 현재 시장이 "거래할 준비가 되었는지"를 판단하는 최상위 의사결정 계층임.

## 3. 핵심 후보 Factor (지표)
- **volatility_300s**: 최근 5분간의 변동성. 기회 발생의 최소 동력 확인.
- **imbalance_300s**: 최근 5분간의 누적 체결 불균형. 추세 지속 가능성 확인.
- **bid_ask_depth_ratio_5**: 상위 5호가 매수/매수 잔량 비율. 하단 지지 및 상방 돌파 유동성 확인.
- **spread_pct / avg_spread_60s**: 진입/청산 비용 및 시장 안정성 확인.
- **volume_spike_ratio_60s**: 단기 거래량 폭발 여부.

## 4. Market Factor Filter v1 구조
### 1단계: Hard Block (기본 차단)
- DDM 데이터 오류 및 진입 제한
- 데이터 지연 및 거래소 점검
- 스프레드가 목표 수익을 초과하거나 출구 유동성이 부족한 경우
- 일일 손실 한도 등 리스크 관리 임계치 도달

### 2단계: Market Factor Pass (장세 필터)
- `volatility_300s`가 최소 기준(0.05%) 이상인가?
- `imbalance_300s`가 양수이며 일정 기준(0.10) 이상인가?
- `depth_ratio`가 충분한 지지(1.50)를 보이고 있는가?
- `spread_pct`가 과도하지 않은가?

## 5. v1 후보 기준 (Candidate Thresholds)
- **min_volatility_300s_pct**: 0.05 (저변동성 장세 0% 승률 구간 차단)
- **min_imbalance_300s**: 0.10 (추세 동력 확인)
- **min_bid_ask_depth_ratio_5**: 1.50 (매수세 우위 확인)
- **max_spread_pct**: 0.12 (비용 통제)
- **require_btc_alignment**: false (개별 종목 모멘텀 우선)

## 6. 결합 구조
Market Factor Filter v1을 통과한 시점에서만 다음 로직을 수행함:
1. **Short-Term Trend Score** 계산 (가중치 적용)
2. **Net Edge Gate** 확인 (실효 기대값 검증)
3. **DDM Gate** 확인 (데이터 동적 안정성 검증)
4. 최종 **Paper Entry** 후보 평가

## 7. 실험 절차
1. 기존 3시간 로그를 대상으로 `market-factor-diagnostics`에서 도출된 임계값을 적용하여 "Filter Pass" 구간을 정의.
2. Filter Pass 구간 내에서만 Short-Term Trend 백테스트 재실행.
3. 필터 적용 전/후의 **Net PnL 개선율** 및 **Winner Rate** 증가폭 분석.
4. 결과가 긍정적일 경우 Paper Trading 모드에 장세 필터 로직 결합 검토.

## 8. 금지 및 주의 원칙
- **자동 반영 금지**: 본 설정은 실험용이며 실전 `config.json`에 즉시 적용하지 않음.
- **실거래 반영 금지**: 수익성 개선이 백테스트로 입증된 후에도 장시간의 Paper Trading 검증이 선행되어야 함.
- **코드 수정 금지**: `orderflow_paper.py`의 핵심 주문 로직을 임의로 변경하지 않음.
