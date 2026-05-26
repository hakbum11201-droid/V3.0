# FORWARD_LABEL_CANDIDATE_ROBUSTNESS_PLAN_KR

## 1. 개요 및 목적
Forward Label Mining을 통해 발견된 조건(`micro_momentum_score <= p1 AND recent_return_60s <= p3 AND recent_return_30s <= p3`)이 수수료 장벽(0.05% 슬리피지 기준 Net +0.1366%)을 넘었으나, 특정 마켓(Top1 Share 55.77%)에 수익이 편중된 현상(Market Bias)이 발견되었습니다.
본 검증(Robustness Retest)은 이 후보가 과최적화된 가짜 엣지가 아니라 실전에서도 견딜 수 있는 엣지인지 다각도로 스트레스 테스트(Market Cap, 제척, Walk-forward)하는 것이 목적입니다.

## 2. 검증 대상 후보
- **Raw Condition**:
  1. `micro_momentum_score <= p1`
  2. `recent_return_60s <= p3`
  3. `recent_return_30s <= p3`
- 위 3개 조건은 순서와 무관하게 완전히 동일한 하나의 교집합 규칙(Deduplicated Condition)으로 취급합니다.

## 3. 검증 방법론 (4가지 스트레스 테스트)
기존의 고정된 Train(70%)/Test(30%) 환경에서 아래 테스트를 수행합니다.

### A. Raw Unconstrained
- 기존과 동일하게 모든 마켓의 시그널을 제한 없이 진입하여 베이스라인 재현성을 확인합니다.

### B. Equal Market Cap
- 마켓별 진입 횟수에 상한(Cap)을 두어, 소수 마켓에 이익이 과도하게 편중되는 것을 막습니다.
- 후보군의 총 Test 진입 수가 적으므로(약 50건), 캡 기준을 `Max 5건, Max 10건, Max 20건` 등으로 두어 편중이 완화된 후에도 Net PnL이 양수인지 확인합니다.

### C. Top1 Market Removed
- A 결과에서 Test 진입/이익 비중이 가장 높은 1위 마켓을 통째로 제외한 뒤, 나머지 9개 마켓만으로 Net PnL을 재평가합니다. 엣지가 특정 마켓 고유의 현상인지 판별합니다.

### D. Weak Market Removed
- **Train 구간**에서 Net PnL 성과가 가장 나빴던(음수) 마켓들을 필터링한 뒤, **Test 구간**에서 해당 마켓들을 제외하고 평가합니다. (미래 참조 방지)

## 4. Walk-Forward 검증
시간순으로 구간이 이동하는 3개의 Fold를 생성하여, 특정 시기에만 우연히 맞은 엣지가 아님을 증명합니다.
- **Fold 1**: Train(Band 0~9), Test(Band 10~14)
- **Fold 2**: Train(Band 2~11), Test(Band 12~16)
- **Fold 3**: Train(Band 4~13), Test(Band 14~19)
*각 Fold마다 Train 데이터에서 Feature의 Percentile(p1, p3)을 **재계산**하여 Test에 적용합니다.*

## 5. 비용 및 Exit 조건
- **비용**: 1회 왕복 수수료+슬리피지 0.20% 적용 (slip 0.05% 기준)
- **Exit Base**: TP +0.7%, SL -0.3%, Timeout 300s
- **Exit Sensitivity**: TP(+0.5%, +1.0%), SL(-0.2%), TO(600s) 등의 주변부 조건에서도 성과가 무너지지 않는지 평가합니다.

## 6. 통과 기준 및 Judgement
- **강한 통과**: Test Net slip 0.05% > +0.03%, Profit Factor >= 1.3, Fold 3개 중 2개 이상 양수, Top1 Market Share < 40%.
- **약한 통과**: Test Net > 0, Profit Factor >= 1.15, Fold 3개 중 2개 이상 양수.
- **실패**: Market Cap 또는 Top1 제거 후 수익이 음수로 붕괴되거나, Fold 대부분이 음수이면 과최적화로 간주합니다.

**판정 분류**:
- `ROBUST_EDGE_CONFIRMED`: 모든 스트레스 테스트 방어 성공
- `WEAK_EDGE_NEEDS_MORE_DATA`: 일부 기준 미달이나 생존
- `MARKET_BIAS_ONLY`: 특정 마켓 제외 시 성과 붕괴
- `FOLD_UNSTABLE`: 특정 기간에만 작동
- `OVERFIT_REJECTED`: 기준 미달 및 전면 실패
