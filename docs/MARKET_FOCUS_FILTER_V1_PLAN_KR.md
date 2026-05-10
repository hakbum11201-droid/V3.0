# Market Focus Filter v1 실험 설계 문서

## 1. 문제 정의
- **장세 필터의 한계**: `Market Factor Filter v1`은 변동성이 있는 장세를 고르는 데 성공했으나, 해당 장세 내에서도 종목별 성과 차이가 극명함.
- **마켓 집중 현상**: 최근 3시간 진단 결과, 모든 Winner가 `KRW-SOL`에 집중됨. 이는 특정 시점에 시장의 에너지가 특정 종목으로 쏠리는 현상을 반영함.
- **거래량 품질(Volume Quality)**: 단순히 거래량이 많은 것이 아니라, `buy_trade_value_10s` 기준 상위 25%(`Overheated` 구간)의 강한 매수세가 실린 종목에서만 수익 기회가 발생함.
- **결론**: 장세 필터 통과 후, 현재 시장의 **"주도 종목(Leader)"**과 **"고품질 거래량(Volume Quality)"**을 선별하는 2차 필터링이 필요함.

## 2. Market Focus Filter v1 목적
- **주도 마켓 선별**: 현재 시장에서 가장 강한 모멘텀과 거래량을 점유하고 있는 마켓을 동적으로 선택.
- **자원 집중**: 승률이 낮은 비주도 마켓(이번 샘플의 경우 BTC, XRP)에서의 노이즈 진입을 원천 차단.
- **거래량 품질 검증**: 최소 거래량 기준 및 상대적 거래량 점유율을 통해 실효성 있는 움직임만 선별.
- **2단계 게이트**: `Market Factor Filter`를 통과한 시점에서만 작동하는 세부 필터링 계층.

## 3. 핵심 후보 Factor (지표)
- **market_leadership_score**: 시세 분출 및 거래량 점유율 기반 주도성 점수.
- **buy_trade_value_10s / 60s**: 절대적 매수 거래량 규모.
- **relative_volume_share**: 전체 감시 종목 중 해당 종목의 거래량 비중.
- **volume_quality_bucket**: 거래량 수준별 구간(Low, Mid, High, Overheated).
- **winner_rate_by_market**: 백테스트 기반 마켓별 실효 승률.

## 4. Market Focus Filter v1 후보 기준 (Candidate Thresholds)
- **market_focus_mode**: `dynamic_leader` (동적 주도 마켓 선정)
- **static_focus_markets**: `["KRW-SOL"]` (실험 초기 고정 타겟으로 검증)
- **min_buy_trade_value_10s**: 1,000,000 KRW (최소 실행 유동성 확보)
- **require_overheated_volume_bucket**: true (상위 25% 거래량 구간 필수)
- **min_relative_volume_share**: 0.30 (전체 거래량의 30% 이상 점유)
- **max_focus_markets**: 1 (가장 강한 1개 종목에만 집중)

## 5. 필터 구조
Market Factor Filter 통과 후:
1. **Market Focus Filter** 작동: 현재 주도 마켓 여부 및 거래량 품질 검사.
2. 통과된 마켓에 대해서만 **Short-Term Trend Score** 계산.
3. **Net Edge Gate** 및 **DDM Gate** 최종 검증.
4. **Paper Entry** 후보 평가.

## 6. 주의 및 금지 원칙
- **영구 Whitelist 금지**: 이번 샘플에서 SOL이 강했으나, 이를 고정 종목으로 확정하지 않음. 시장 주도주는 언제든 바뀔 수 있음.
- **동적 구조 설계**: 특정 종목이 아닌, "현재 시장을 주도하는 1등 종목"을 찾는 로직으로 설계함.
- **충분한 검증**: 실거래 반영 전 최소 3~7일간의 Paper Trading을 통해 주도주 전환 시 대응력을 확인해야 함.

## 7. 실험 절차
1. 기존 3시간 로그에 `Market Factor Filter`와 `Market Focus Filter`를 순차 적용.
2. `SOL-only` 고정 모드와 `Dynamic Leader` 모드의 성과(Net PnL, Win Rate) 비교.
3. 필터 적용으로 인해 수익 기회를 놓치는 "Missed Winner" 비율 측정.
4. 최종 Net PnL이 0% 이상으로 전환되는 조합을 도출하여 Paper 전략 반영 여부 결정.

## 8. 금지 원칙
- **자동 config 반영 금지**: 실험적 설정이며 `config.json`에 즉시 적용하지 않음.
- **실거래 반영 금지**: 수익성 개선 입증 전까지는 `live.enabled=false` 유지.
- **수정 제한**: `orderflow_paper.py` 소스 코드를 본 문서 작업과 동시에 수정하지 않음.
