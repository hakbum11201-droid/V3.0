# EXECUTION_AWARE_FORWARD_LABEL_MINING_PLAN_KR

## 1. 개요 및 목적
이전 단계의 OOS 검증 결과, 강력해 보였던 엣지가 실제 체결 현실성 필터(Spread Filter)를 거치자 단 한 건도 체결되지 않는 "허수 엣지(Paper Edge)"로 판명되었습니다.
이에 따라, 아예 처음부터 **체결 가능성(Execution Quality)**을 강제하고 **실제 호가(Ask/Bid)** 기준으로 PnL을 산정하는 **Execution-Aware Forward Label Mining**을 수행합니다.

## 2. 데이터 스트림 및 체결 모델
- **Orderbook Stream & Trade Stream 분리**: 체결 가격을 Mid Price로 가정하지 않습니다.
- **Entry Price**: 시그널 발생 시점의 `Best Ask Price` (Long 진입 기준)
- **Exit Price**: 미래 가격 도달 시점의 `Best Bid Price`
- **Fallback**: Orderbook 데이터가 빈약할 경우 Trade Price로 Fallback 하되, 이 비율(fallback_rate)이 높은 후보는 실전 신뢰도가 낮으므로 감점 처리합니다.

## 3. Execution Filter 강제
모든 전략 후보는 무조건 아래 체결 현실성 피처 중 최소 1개 이상의 필터 조건을 포함해야 합니다.
- `spread_pct`
- `ask_size`
- `bid_size`
- `orderbook_imbalance`
이를 통해, 호가가 얇거나 스프레드가 찢어진 "Liquidity Vacuum" 상태에서만 터지는 가짜 시그널을 원천 차단합니다.

## 4. 비용 모델 및 라벨
- **수수료 및 슬리피지**: Upbit One-way 0.05% 수수료 + 슬리피지(0.03%, 0.05%, 0.10%)
- **핵심 통과 라벨**: Round Trip 0.20% (slip 0.05%) 비용 차감 후에도 순수익(Net PnL)이 양수여야 합니다.

## 5. 탐색 및 검증 방법 (Train/Test Split)
- **Train (70%)**: 시간순 앞부분. 피처별 Percentile(p1~p99)을 계산하고, 이 임계값을 바탕으로 양수 라벨을 묶어내는 조건(단일, 2-조합, 3-조합)을 탐색합니다.
- **Test (30%)**: 시간순 뒷부분. Train에서 결정된 임계값과 Exit(TP/SL/TO) 구성을 그대로 적용해 미래 성과를 평가합니다.

## 6. 평가 및 판정 기준 (Judgement)
- **강한 통과**: Test Net > +0.03%, PF >= 1.3, Trades >= 50, Viable Markets >= 3, Top1 Share < 45%, Fallback Rate < 20%
- **약한 통과**: Test Net > 0, PF >= 1.15, Trades >= 30, Viable Markets >= 2, Fallback Rate < 30%
- **실패**: Test Net 음수, Spread Filter 강제 시 Trades 부족, Fallback Rate 과다, 1개 마켓에 극단적 편중(60% 이상)

**판정 분류**:
- `EXECUTION_AWARE_EDGE_FOUND`
- `WEAK_EXECUTION_EDGE_FOUND`
- `OVERFIT_ONLY`
- `MARKET_SPECIFIC_ONLY`
- `EXECUTION_FILTER_NO_TRADES`
- `COST_BARRIER_NOT_CLEARED`
- `NEED_MORE_DATA`
- `REJECT_CURRENT_FEATURE_SPACE`
