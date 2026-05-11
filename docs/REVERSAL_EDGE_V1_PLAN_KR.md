# Reversal Edge v1 실험 설계안

## 1. 문제 정의
- 기존 **Soft Score v1**, **Short-Term Trend v1**, **Combined Filter**, **Exit Simulator**는 모두 평균 Net PnL 양수 전환에 실패했습니다.
- 고정 보유와 TP/SL 청산 시뮬레이션이 모두 수익성 입증에 실패했으므로, 병목은 청산 정책이 아닌 **진입 구조**에 있음이 확인되었습니다.
- 36시간 데이터 진단 결과, Winner(수익 기회)는 상승 추세 추격(Continuation)이 아닌 **매도 압력 이후 반등(Reversal)** 구조에서 더 높은 확률(33.22% vs 15.76%)로 발생했습니다.

## 2. Reversal Edge v1 목적
- 강한 매도 체결이 나온 뒤 가격이 단기 하락했지만, **호가창 방어력이 유지되는 구간(Absorption Rebound / Exhaustion Reversal)**을 찾습니다.
- 매도세가 소진된 후 반등 가능성이 높은 구간만을 진입 후보로 엄격히 평가합니다.
- 모든 장세에서 무분별하게 거래하지 않도록 Market Factor Filter와 결합하여 검증합니다.

## 3. 핵심 후보 지표
- `price_chg_1s`, `price_chg_3s`, `price_chg_10s` (단기 하락 확인)
- `sell_trade_value_3s`, `sell_trade_value_10s`, `sell_trade_value_30s` (매도 압력 확인)
- `buy_trade_value_10s` (매수 지지력)
- `sell_buy_ratio_10s`, `sell_buy_ratio_30s` (단기 체결 불균형)
- `bid_ask_depth_ratio_5` (호가창 방어력)
- `spread_pct` (시장 유동성/비용 안전성)
- `volatility_300s` (기반 변동성)
- `market_sync_score` (비트코인 등 주도주 동조화)

## 4. Reversal Edge v1 후보 조건
- `price_chg_10s` < 0 (10초간 가격 하락)
- `sell_trade_value_10s` > `buy_trade_value_10s` (매도 체결 우위)
- `sell_buy_ratio_10s` >= 1.2 (매도 압력이 1.2배 이상)
- `bid_ask_depth_ratio_5` >= 0.8 (매수 호가잔량 방어)
- `spread_pct` <= 0.12 (좁은 스프레드)
- `volatility_300s` >= 0.04 (최소 변동성 확보)
- `holding_windows_sec`: [300, 600]
- `preferred_holding_window_sec`: 600
- `cost_floor_pct`: 0.20

## 5. Strong Reversal 주의
- 기존 36시간 진단에서 Strong Reversal(강한 하락 후 반등형) 조건은 지나치게 엄격하여 샘플이 0개였습니다. 
- 너무 강한 조건은 후보를 모두 차단할 위험이 있으므로, v1은 **완화된 현실적인 수준의 Reversal 조건**에서 실험을 시작합니다.

## 6. Market Focus
- 이전 진단에서 `KRW-SOL`이 가장 유망(47.97% Winner Rate)했지만, 이는 36시간이라는 특정 표본에 편향되었을 수 있으므로 영구 고정하지 않습니다.
- `static_focus_markets` 후보에는 `KRW-SOL`을 포함하여 진행합니다.
- 단, `DYNAMIC_LEADER` 및 `ALL_MARKETS` 모드와 비교 검증하여 과최적화를 방지합니다.

## 7. Reversal Edge v1 점수 구조
**가중치 배분 (총점 130점 기준):**
- `negative_price_chg_score`: 25점
- `sell_pressure_score`: 25점
- `sell_buy_ratio_score`: 20점
- `bid_depth_support_score`: 20점
- `spread_safety_score`: 15점
- `volatility_score`: 15점
- `market_sync_score`: 10점

**임계값(Threshold) 후보:**
- 70, 80, 90

## 8. 실험 절차
1. 기존 수집된 36시간 로그에 Reversal Edge v1 후보를 적용하여 백테스트를 수행합니다.
2. 300초와 600초 보유 시간에 따른 성과를 비교합니다.
3. 고정 보유와 TP/SL/Timeout 청산 방식의 성과를 교차 비교합니다.
4. `ALL_MARKETS` / `STATIC_SOL_ONLY` / `DYNAMIC_LEADER`를 비교하여 표본 편향 여부를 진단합니다.
5. 평균 Net PnL 양수 조합이 존재하는지 최종 확인합니다.
6. 결과가 양호하고 비용 상쇄가 명확히 입증될 때만 `paper` 전략 실험(Orderflow Paper)으로 이관을 검토합니다.

## 9. 금지 원칙
- **자동 config 반영 절대 금지**
- **실거래(LIVE) 반영 절대 금지**
- `orderflow_paper.py` 즉시 수정 금지
- SOL-only 모드 즉시 확정 금지
- 평균 Net PnL 검증 없는 전략 반영 금지
