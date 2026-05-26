# FORWARD_LABEL_CANDIDATE_OOS_VALIDATION_PLAN_KR

## 1. 개요 및 목적
Forward Label Mining과 Robustness Test를 거쳐 발견된 수익 후보 엣지(`micro_momentum_score <= p1 AND recent_return_60s <= p3 AND recent_return_30s <= p3`)가 실전 Mock Trading 단계로 넘어가도 될지 최종 점검합니다.
이 과정은 조건을 더 탐색(Mining)하는 것이 아니라, 이미 발견된 엣지를 **확장된 Out-Of-Sample (OOS) 방법론**과 **체결 현실성(Execution Quality) 필터**로 두드려 패는 검증 전용 단계입니다.

## 2. 검증 대상 후보
- **기본 조건**: `micro_momentum_score <= p1`, `recent_return_60s <= p3`, `recent_return_30s <= p3`
- **기본 Exit**: TP +0.7%, SL -0.3%, Timeout 300s
- **비용 기준**: 1회 왕복 수수료+슬리피지 0.20% (slip 0.05%)

## 3. OOS Split 검증 방법론
데이터 전체를 아래 3가지 방식으로 다르게 나누어, 어떤 식으로 잘라도 엣지가 살아있는지 검증합니다.

### A. Rolling OOS (시계열 이동)
- 총 4개의 시간순 Fold를 생성합니다. (각 Fold: Train 약 60%, Test 약 20%)
- Train과 Test 사이에는 600초의 Embargo를 두어 미래 참조를 방지합니다.
- 특정 시점의 시황에만 최적화된 조건이 아님을 증명합니다.

### B. Late Holdout (최근 데이터)
- 앞부분 70%를 Train, 뒷부분 30%를 Test로 나눕니다. (가장 기본적인 검증)
- 이 30% Test 데이터를 기준으로 체결 현실성 필터와 Market Cap 비교를 수행합니다.

### C. Market Holdout (일반화 가능성)
- 각 반복(Fold)마다 1개의 특정 마켓을 완전히 배제(Holdout)하고 나머지 9개 마켓으로 Train(Percentile 계산)합니다.
- 그리고 배제되었던 그 1개 마켓에 대해서만 Test 평가를 수행합니다.
- 10개 마켓을 번갈아가며 진행하며, 특정 코인의 고유 특성이 아니라 마켓 전체에 통용되는 보편적 엣지인지 확인합니다.

## 4. 체결 현실성 필터 (Execution Quality Filter)
단순 과거 시뮬레이션에서는 체결되었다고 가정하지만, 실제로는 호가가 너무 얇거나 스프레드가 넓어 체결되지 않을 수 있습니다.
- **Spread Filtered**: 호가 스프레드가 Train 평균치(p60) 이내인 촘촘한 상태에서만 진입하도록 제한합니다.
- **Market Cap**: 특정 마켓에서만 이익이 펌핑되는 것을 막기 위해 진입 횟수를 마켓당 20개, 50개로 제한합니다.
- **Top1 Removed**: 가장 비중이 큰 1등 마켓을 제외하고 검증합니다.

## 5. 통과 기준 및 Judgement
- **강한 통과**: 4개 OOS Fold 중 3개 이상 양수, Test Net > +0.03%, Profit Factor >= 1.3, Trades >= 80, Top1 비중 < 45%.
- **약한 통과**: Fold 과반 양수, Test Net > 0, Profit Factor >= 1.15, Trades >= 50.
- **실패**: OOS Fold 대부분이 음수, Market Holdout 붕괴, 체결 필터 적용 후 성과 붕괴.

**판정 분류**:
- `OOS_ROBUST_EDGE_CONFIRMED`
- `WEAK_EDGE_NEEDS_MORE_DATA`
- `MARKET_BIAS_ONLY`
- `EXECUTION_FILTER_FAIL`
- `OOS_FAILED`
- `NEED_MORE_DATA`
