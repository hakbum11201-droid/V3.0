# Orderflow Soft Score 전환 및 실험 계획 (v1)

## 1. 개요 및 문제 정의

### 1.1 현황 분석 결과
최근 Moderate Fast 실험(10분, 1초 단위 진단) 결과, 현재의 **Hard Gate** 방식이 시장 기회를 과도하게 차단하고 있음을 확인하였습니다.

*   **진입 기회 발생률**: 약 0.38% (2,363개 샘플 중 9회)
*   **핵심 병목**:
    *   `Sweep Score` 통과율: **0.04%** (P90 변동성이 0.1% 미만인 현재 시장에서 거의 달성 불가능)
    *   `Volume Gate` 통과율: **2.67%** (평시 체결 규모 대비 기준값이 높음)
    *   `Continuation Score` 통과율: **0.08%**

### 1.2 문제 정의
현재 시스템은 **"폭등 직전의 강력한 모멘텀"**만 거래하려고 설계되어 있으나, 실제 시장은 낮은 변동성 속에서도 짧은 주문흐름 불균형과 흡수(Absorption)가 반복되는 구조입니다. 현재의 모든 조건을 만족(AND)해야 하는 Hard Gate 구조는 거래 집행력을 상실하게 만듭니다.

---

## 2. 구조 전환 원칙: Hard Block에서 Soft Score로

거래를 억지로 늘리는 것이 아니라, **"종합적인 주문흐름 품질"**을 점수로 평가하여 유연성을 확보하되, 치명적인 위험은 여전히 Hard Block으로 차단합니다.

### 2.1 Hard Block 유지 항목 (필수 차단)
아래 항목은 점수와 관계없이 진입을 즉시 차단합니다.
*   **DDM 관리**: `DATA_ERROR`, `BLOCK_NEW_ENTRY` 상태
*   **리스크 관리**: 일일 손실 한도 초과, MDD 한도 초과, 연속 손실 제한
*   **시장 위험**: 유의/주의 종목, BTC 급락 상황
*   **비용 방어**: 스프레드가 목표 익절폭보다 큰 경우, 탈출 유동성(Depth) 부족
*   **데이터 무결성**: 데이터 지연(Stale) 또는 오류

### 2.2 Soft Score 평가 항목
기존에 개별적으로 차단하던 항목들을 가중치 기반 점수로 합산합니다.
*   **Volume Score**: `buy_trade_value_3s/10s` (체결 강도)
*   **Spread Score**: `spread_pct` (비용 효율성, 낮을수록 가점)
*   **Imbalance Score**: `bid_ask_depth_ratio_5`, `buy/sell imbalance` (미체결 호가 불균형)
*   **Absorption Score**: `absorption_score` (매도물량 흡수 품질)
*   **Continuation Score**: `price_change_3s/10s_pct`, `continuation_score` (흐름 지속성)
*   **Sweep Score**: `sweep_score` (보조 모멘텀 가점)

---

## 3. Soft Score v1 실험 설계

### 3.1 가중치 후보 (Weights v1)
| 항목 | 가중치 | 선정 이유 |
| :--- | :---: | :--- |
| **Volume Score** | 25 | 주문흐름의 가장 기초적인 신뢰도 지표 |
| **Spread Score** | 20 | 실질 수익성(Net Edge) 확보를 위한 비용 방어 |
| **Imbalance Score** | 20 | 호가창의 선행적 불균형 평가 |
| **Absorption Score** | 20 | 현재 시장에서 가장 빈번하게 발생하는 유의미한 신호 |
| **Continuation Score**| 10 | 가격 지속성은 보조적으로 평가 (현 변동성 반영) |
| **Sweep Score** | 5 | 현재 시장에서 매우 희소하므로 핵심 Gate에서 보조 가점으로 강등 |

### 3.2 진입 허용 기준 (Candidate)
*   **Hard Block**: 해당 없음
*   **Soft Score 합계**: **70점 이상**
*   **Net Edge**: **0 초과** (수수료/슬리피지 차감 후 기대수익 양수)
*   **DDM 상태**: `NORMAL`
*   **포지션**: 없음

---

## 4. 향후 실험 및 검증 절차

1.  **시뮬레이션**: Soft Score v1 로직을 기존 수집된 WS 로그(Conservative/Moderate/Fast)에 적용하여 가상의 `trade_count`와 `net_pnl` 산출.
2.  **비교 분석**: 기존 Hard Gate 방식 대비 MDD 증가폭과 수익성 개선폭을 정밀 비교.
3.  **반영 검토**: 시뮬레이션 결과가 MDD 가이드라인 내에 있고 `net_pnl`이 유의미하게 개선될 경우에만 `orderflow_paper.py` 반영.

---

## 5. 주의사항 (금지 원칙)
*   **자동 적용 금지**: 본 문서는 실험 계획이며, 실제 전략 로직이나 `config/config.json`에 자동으로 반영하지 않습니다.
*   **원금 방어 우선**: 거래 횟수를 늘리기 위해 리스크 관리(Hard Block)를 완화하지 않습니다.
*   **정량적 검증**: 반드시 `net_pnl`과 MDD 데이터가 뒷받침될 때만 구조 전환을 승인합니다.
