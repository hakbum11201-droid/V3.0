# COST_AWARE_FORWARD_LABEL_MINING_PLAN_KR

## 1. 개요 및 목적
기존의 휴리스틱(사람이 설정한) 조건들은 실제 시장의 수수료와 슬리피지(0.05% * 2 = 0.10%) 장벽을 넘지 못했습니다. 본 탐색은 이 한계를 극복하기 위해 **"먼저 미래에 수익이 나는(Label Positive) 구간을 식별하고, 그 직전의 Feature 조합을 역으로 찾아내는 Forward Label Mining"** 기법을 적용합니다. 

단, 과최적화를 완벽히 통제하기 위해 데이터를 시간순으로 분리(Train/Test)하며, Train에서 찾은 규칙을 Test에서 검증하여 생존하는 조합만을 추출합니다.

## 2. 데이터 처리 및 분할
- **시간순 분할**: 전체 Band(20개) 중 앞 70%는 Train, 뒤 30%는 Test로 할당합니다.
- **Embargo**: Train과 Test 경계에 600초의 공백을 두어 미래 참조(Look-ahead) 오염을 방지합니다.
- **추출 크기 제한**: 연산량 폭발을 막기 위해 10초 간격으로 마켓당 최대 5,000개의 스냅샷을 고르게 추출합니다.

## 3. Feature Space (탐색 대상 변수)
24종의 미시 구조 및 체결 지표를 대상으로 합니다.
- **수익률 (Returns)**: 5s, 10s, 30s, 60s, 120s
- **매수/매도 압력 (Pressure)**: spr_10s, spr_30s, bpr_10s, bpr_30s, pressure_delta_30s
- **거래량 (Volume)**: vol_10s, vol_30s, volume_spike_30s
- **호가 불균형 (Imbalance)**: ob_imb, imb_delta_30s
- **스프레드 및 뎁스 (Liquidity)**: spread_pct, spread_delta_30s, bid_depth_change, ask_depth_change, depth_recovery_score, liquidity_vacuum_score
- **모멘텀**: micro_momentum_score

## 4. Forward Label 생성 및 Exit Grid
각 스냅샷 시점마다 아래의 Exit 조합 전체(180개)를 시뮬레이션하여 실제 수수료+슬리피지 차감 후 Net PnL을 미리 계산합니다.
- **TP**: 0.20%, 0.30%, 0.40%, 0.50%, 0.70%, 1.00%
- **SL**: -0.08%, -0.10%, -0.15%, -0.20%, -0.30%
- **TO**: 120s, 180s, 300s, 450s, 600s, 900s

## 5. 마이닝 알고리즘 (Rule Extraction)
1. **1-Feature 룰 평가**: 24개 Feature 각각에 대해 주요 Percentile(1~99)을 기준으로 `<=`, `>=` 조건을 생성하여 모든 Exit 조합의 평균 성과를 측정합니다.
2. **조합 확장**: 우수한 단일 룰을 결합하여 2-Feature, 3-Feature 룰을 동적으로 생성합니다.
3. **Train 조건 필터링**: Train Set에서 `Net PnL > 0` 이고 `Profit Factor >= 1.1`, 최소 거래수 >= 50 인 룰만 선별합니다.
4. **Test 검증**: 선별된 룰과 해당 룰의 Best Exit 조합을 그대로 Test Set에 적용합니다.

## 6. 최종 통과 기준
- Test Net PnL slip 0.05% > 0
- Test Profit Factor >= 1.2
- Test Trades >= 30
- Viable Markets >= 2
- Top1 Market Share < 50%
- Max Consecutive Losses <= 8
- Timeout Ratio <= 40%

## 7. 판정 분류 (Judgement)
- `FORWARD_LABEL_EDGE_FOUND`: 위 모든 조건을 통과하는 강한 엣지 발견
- `WEAK_EDGE_FOUND`: 생존은 했으나 기준에 미달하는 경우
- `OVERFIT_ONLY`: Train은 양수이나 Test에서 음수로 붕괴
- `MARKET_SPECIFIC_ONLY`: 1개 마켓에만 편중되어 이익 발생
- `COST_BARRIER_NOT_CLEARED`: 비용 장벽을 넘지 못함
- `REJECT_CURRENT_FEATURE_SPACE`: 모든 조합이 실패한 경우 새로운 지표 설계 필요
