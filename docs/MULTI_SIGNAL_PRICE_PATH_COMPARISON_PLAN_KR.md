# MULTI_SIGNAL_PRICE_PATH_COMPARISON_PLAN_KR

## 1. 개요 및 목적
기존의 DOGE-only, Reversal-only 전략 접근법을 확장하여, Top 10 KRW 마켓 전체를 대상으로 **주문흐름 기반의 여러 신호군(Signal Family)**을 동등한 기준에서 비교합니다. 
궁극적인 목표는 수수료 및 슬리피지(왕복 0.10%, 한 방향 0.05%) 차감 후에도 생존할 수 있는 강건한 신호 구조를 발굴하는 Price-Path Edge Discovery입니다.

## 2. 평가 대상 Signal Family
본 비교 도구는 다음과 같은 5가지 신호군을 시장별 동적 Percentile 기반으로 스캔합니다.

### A. reversal_selloff
- **의미**: 급락 + 매도 압력 후 반등 기대 (기존 reversal의 확장)
- **조건**: 
  - `recent_return_30s <= p10`
  - `sell_pressure_ratio_10s >= p75`

### B. absorption_reversal
- **의미**: 매도 체결 압력이 강한데 가격이 덜 밀리는 흡수 패턴
- **조건**: 
  - `sell_pressure_ratio_30s >= p75`
  - `recent_return_30s >= p35`
  - `orderbook_imbalance >= p60`

### C. sweep_recovery
- **의미**: 짧은 급락 후 즉시 회복 시작
- **조건**: 
  - `recent_return_60s <= p15`
  - `recent_return_10s >= max(p55, 0.0)`
  - `bid_depth_change_30s >= p70` (매수벽 두께 회복)

### D. continuation_buy_pressure
- **의미**: 강한 매수 압력 지속 (모멘텀 지속)
- **조건**: 
  - `recent_return_30s >= p85`
  - `buy_pressure_ratio_10s >= p70`
  - `orderbook_imbalance >= p60`

### E. failed_breakdown
- **의미**: 60초 기준 하락했지만 최근 10초 기준 하락 실패 및 반등
- **조건**: 
  - `recent_return_60s <= p15`
  - `recent_return_10s >= p50`
  - `sell_pressure_ratio_10s < p75`

## 3. 평가 방법론 (Price-Path Simulation)
- **데이터소스**: `logs/experiments/master/reversal_edge_master_dataset.sqlite` (과거 120분 Band 20개 추출)
- **특징 추출 (Features)**: Trade 및 Orderbook Stream 분리 후 과거 데이터만 사용하여 스냅샷 단위 Feature 산출 (Forward leakage 절대 금지)
- **동적 임계값 (Adaptive Threshold)**: 산출된 스냅샷 Feature들의 마켓별 자체 분포(Percentile)를 계산하여 신호 판단의 기준으로 사용.
- **Price-Path 판정**:
  - `TP`: +0.15%, +0.20%, +0.25%, +0.30%, +0.40%
  - `SL`: -0.08%, -0.10%, -0.15%, -0.20%
  - `Timeout`: 120s, 180s, 300s, 450s, 600s
- **비용 모델**: Upbit Fee(0.05%) + Slippage(0.03%, 0.05%, 0.10%) 왕복 적용

## 4. 핵심 판정 기준 및 판단(Judgement)
가장 보수적인 기준인 **Slippage 0.05% (왕복 비용 0.20%)** 차감 후의 Net PnL이 0보다 큰지 여부(`slip 0.05% avg net > 0`)를 핵심 관문으로 삼습니다.

- `SIGNAL_FAMILY_SURVIVES_COSTS`: 0.05% 생존 및 마켓 쏠림(Bias) 없음.
- `MARKET_SPECIFIC_ONLY`: 생존 마켓이 3개 미만인 경우.
- `COST_SENSITIVE_WEAK`: 0.03%는 생존하나 0.05%에서 실패.
- `NO_SIGNAL_SURVIVES_COSTS` / `REJECT_CURRENT_SIGNAL_SET`: 모두 실패.

## 5. 단계별 실행 절차
1. `tools/run_multi_signal_price_path_comparison.py` 스크립트 작성
2. `events` 테이블을 통해 Market별 Band 스냅샷 특징 추출 -> Percentile 산출 -> Signal 진입점 스캔.
3. Price-path를 통해 각 신호군의 최적 Exit 조합 도출 및 생존 여부 판정.
4. `multi_signal_price_path_comparison_latest.txt` 및 JSON 리포트 생성.
5. 결과 검토 후 코드와 현재 문서를 Git에 커밋.
