# COST_AWARE_SIGNAL_SEARCH_PLAN_KR

## 1. 개요 및 목적
기존의 Multi-Signal 비교 결과, 어떠한 신호군도 0.05% 슬리피지 기준을 통과하지 못했습니다. 이에 따라 보다 **엄격한(Strict) 조건들의 조합을 탐색**하여, 수수료와 슬리피지(왕복 0.20%)를 극복할 수 있는 실전 가능한 신호가 존재하는지 검증합니다.
과최적화(Overfitting)를 막기 위해, 시간 기반의 Train(70%) / Test(30%) 분할 검증을 필수적으로 도입합니다.

## 2. Train / Test Split 구조
- **데이터소스**: 120분 단위 20개 Band (전체 마켓 대상)
- **Train Set**: 앞쪽 70% Band (약 14개)
- **Test Set**: 뒤쪽 30% Band (약 6개)
- **Feature Percentile 산출**: 오직 **Train Set**의 데이터를 기반으로 산출하여 Look-ahead 편향을 원천 차단합니다.
- **조합 최적화**: Train Set에서 가장 좋은 성과(Net PnL slip 0.05% 기준)를 낸 Exit 조합(TP/SL/TO)을 선택합니다.
- **최종 평가**: Train에서 선택된 조건과 Exit 조합을 Test Set에 적용한 성과를 기준으로 최종 생존 여부를 판정합니다.

## 3. 탐색할 조건 조합 (Signal Families & Parameter Grids)

### A. strict_reversal
- `recent_return_30s <= p3, p5, p10`
- `sell_pressure_ratio_10s >= p85, p90, p95`
- `orderbook_imbalance >= p55, p60, p65`

### B. absorption_quality
- `sell_pressure_ratio_30s >= p85, p90`
- `recent_return_30s >= p25, p35`
- `orderbook_imbalance >= p60, p70`
- `spread_pct <= p60`

### C. sweep_recovery_quality
- `recent_return_60s <= p5, p10, p15`
- `recent_return_10s >= p55, p60, p65`
- `bid_depth_change_30s >= p60, p70`
- `orderbook_imbalance >= p60`

### D. continuation_quality
- `recent_return_30s >= p85, p90`
- `buy_pressure_ratio_10s >= p75, p85`
- `orderbook_imbalance >= p60, p70`
- `spread_pct <= p60`

### E. failed_breakdown_quality
- `recent_return_60s <= p10, p15`
- `recent_return_10s >= p50, p60`
- `sell_pressure_ratio_10s <= p70`
- `imbalance_delta_30s >= p55`

## 4. Price-Path 판정 (Exit 후보군)
- **TP**: +0.20%, +0.25%, +0.30%, +0.40%, +0.50%, +0.70%
- **SL**: -0.08%, -0.10%, -0.15%, -0.20%, -0.30%
- **Timeout**: 120s, 180s, 300s, 450s, 600s, 900s

## 5. 비용 모델 및 통과 기준 (Gate)
- **비용**: 1회 매매(왕복) 시 Upbit 수수료(0.10%) + 슬리피지(0.10% = 한 방향 0.05%) = 총 0.20% 적용
- **핵심 통과 기준**:
  - Test Set의 **slip 0.05% Avg Net PnL > 0**
  - Test Set Profit Factor >= 1.2
  - Viable Markets >= 3
  - Top 1 마켓 비중 < 40%, Top 2 마켓 비중 < 70%

## 6. Judgement 분류
- `COST_AWARE_EDGE_FOUND`: 모든 기준을 통과한 강력한 엣지 발견.
- `OVERFIT_ONLY`: Train은 양수이나 Test에서 음수인 경우.
- `MARKET_SPECIFIC_ONLY`: 엣지는 있으나 특정 1~2개 마켓에 편중됨.
- `COST_BARRIER_NOT_CLEARED`: Train/Test 모두 0.05% 슬리피지를 넘지 못함.
- `REJECT_CURRENT_SIGNAL_SPACE`: 전멸 수준. 새로운 지표 및 접근 방식 필요.
