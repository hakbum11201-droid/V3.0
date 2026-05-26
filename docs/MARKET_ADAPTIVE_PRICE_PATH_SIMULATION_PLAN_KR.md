# Market-Adaptive Price-Path Paper Simulation Plan

## 1. 목적
기존의 DOGE-only 및 단일 고정 임계값(Static Threshold) 전략에서 벗어나, Upbit KRW Top 10 마켓 전체를 대상으로 **주문흐름 기반 반전 신호(Reversal Edge)** 가 수수료 및 슬리피지(왕복 0.10% 이상) 차감 후에도 생존할 수 있는지 검증한다.

## 2. 핵심 목표
이 프로그램의 최종 목적은 개별 코인(DOGE 등) 단기 전략이 아니다. 다양한 변동성을 가진 마켓 환경에서 적응형(Market-Adaptive) 조건이 공통 고정 조건보다 얼마나 더 견고하게 작동하는지를 파악하고, Top 10 마켓 전반에서 엣지가 유지되는지 평가한다.

## 3. 평가 전략 3가지
본 시뮬레이션에서는 3가지 형태의 진입 조건을 비교 검증한다.
1. **Common Static (기존)**
   - `recent_return_30s <= -0.3891`
   - `sell_pressure_ratio_10s >= 0.9929`
2. **Per-Market Percentile (마켓별 분포 기준)**
   - `recent_return_30s <= 마켓별 하위 10% (p10)`
   - `sell_pressure_ratio_10s >= 마켓별 상위 25% (p75)`
3. **Volatility Scaled (변동성 정규화 기준)**
   - `recent_return_30s <= 마켓별 Mean - (1.5 * StdDev)`
   - `sell_pressure_ratio_10s >= 마켓별 상위 30% (p70)`

## 4. 시뮬레이션 환경 (Price-Path)
- **대상 마켓**: KRW-BTC, KRW-DOGE, KRW-ETH, KRW-HP, KRW-ONDO, KRW-PIEVERSE, KRW-SAHARA, KRW-SOL, KRW-UP2, KRW-XRP
- **데이터 소스**: `logs/experiments/master/reversal_edge_master_dataset.sqlite`
- **TP/SL/Timeout 후보군**:
  - TP: +0.20%, +0.25%, +0.30%
  - SL: -0.10%, -0.15%, -0.20%
  - Timeout: 180s, 300s, 450s
- **판정 기준**:
  - Orderbook mid_price 우선 적용 (존재하지 않을 경우 trade_price Fallback)
  - TP와 SL 중 선도달 기준, 미도달 시 TIMEOUT으로 처리

## 5. 비용 및 성과 판정 (Cost Model)
- **비용**: 기본 수수료(0.05%) + 슬리피지 (0.03%, 0.05%, 0.10%)
- **왕복 비용**: `(0.05% + Slippage) * 2`
- **최종 생존 판정 (Key Gate)**: `Slippage 0.05%` 상황에서도 **순수익(Net PnL)이 양수**인지 여부.

## 6. 출력 지표 및 경고 시스템
각 조건 세트별로 다음 지표를 출력한다:
- 전체 거래 수, 승률, 타임아웃 비율
- Gross PnL 및 Slippage별 Net PnL 추정치
- Profit Factor 및 최대 연속 손실 (Max Consecutive Losses)
- 특정 마켓 의존도 (Market Concentration, DOGE/UP2 등) 및 대형 마켓 거래 비중 (Large Market Coverage)
- 마켓별 성과 및 취약 마켓 (Weak Market Candidates)

## 7. 판정(Judgement) 후보
- **MARKET_ADAPTIVE_SURVIVES_COSTS**: 변동성/분포 기반 전략이 슬리피지 0.05%에서도 견고함.
- **COST_SENSITIVE_WEAK**: 슬리피지 0.03%는 넘기나 0.05%에서 손실로 전환됨.
- **MARKET_SPECIFIC_ONLY**: 1~2개 마켓에만 편중되어 있음.
- **REJECT_COMMON_STATIC**: 공통 조건은 기각됨.
- **NEED_MORE_DATA**: 데이터가 부족하거나 거래 수가 너무 적음.
- **MARKET_ADAPTIVE_FAILED**: 적응형 전략조차 비용을 극복하지 못함.

---
> **[주의/Warning]** 
> - 본 시뮬레이션은 NOT PRODUCTION READY 상태의 사전 검증 도구입니다.
> - NO CANDIDATE CREATED, NO CONFIG MODIFIED.
> - 실거래 전환 및 Config 변경에 직접적으로 관여하지 않습니다.
