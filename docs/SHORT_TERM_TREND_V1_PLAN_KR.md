# Short-Term Trend v1 실험 설계 문서

## 1. 문제 정의
- **초단타의 한계**: 5~60초 보유 초단타 스캘핑은 현재 시장 변동성에서 거래 비용(수수료+스프레드+슬리피지 합산 약 0.20%)을 극복할 확률이 극히 낮음.
- **분석 결과**: `market-excursion-diagnostics` 결과, 30~60초 구간의 0.20% 돌파율은 0.01% 미만이나, 5~10분 구간에서는 1.28%~2.11%로 유의미하게 증가함.
- **전략 실패 원인**: Soft Score v1은 신호 발생 빈도는 늘렸으나, 보유 시간이 너무 짧아 비용을 이길 만큼 큰 움직임을 잡아내지 못함.

## 2. 전략 전환 원칙
- **패러다임 전환**: Orderflow Scalping(초단타) -> **Orderflow Short-Term Trend(단기추세)** 전환.
- **수익성 중심**: 거래 빈도를 높이는 것보다, 0.20% 비용을 초과하는 양수 기대값(net_pnl)을 가진 구간을 선별하는 것에 집중.
- **검증 필수**: 모든 전략 변경은 실거래 반영 전 Paper Trading 및 심층 백테스트를 통해 검증되어야 함.

## 3. 핵심 선행 지표 (Short-Term Trend v1)
- **imbalance_10s**: 10초간의 체결 불균형. 단기 추세 형성의 가장 강력한 지표로 판명.
- **price_chg_10s**: 10초간의 가격 변화율. 모멘텀의 시작을 알리는 지표.
- **buy/sell_trade_value_10s**: 절대적인 거래 대금 유입량.
- **spread_pct / depth_ratio**: 진입 비용 및 호가창 견고함 확인.
- **continuation / absorption_score**: 기존 주문흐름의 연장성 및 흡수 현상 활용.

## 4. Hard Block (강력 차단 항목)
- DDM DATA_ERROR / BLOCK_NEW_ENTRY
- BTC 급락 (BTC_CRASH)
- 데이터 지연 (DATA_STALE)
- 스프레드가 목표 수익을 초과하는 경우
- 출구 유동성 부족 (Exit Liquidity)
- 유의/주의 종목 및 거래소 경고
- 일일 손실 한도 / MDD 한도 / 연속 손실 한도 초과

## 5. Short-Term Trend v1 후보 구조
- **보유 시간**: 300초(5분) 및 600초(10분)
- **목표 MFE**: 최소 0.20% 이상
- **비용 산정**: 0.20% (수수료 0.1% + 슬리피지/스프레드 0.1% 가정)
- **가중치 설계**: `sweep` 비중을 0으로 제거하고, `imbalance`와 `price_chg`, `continuation` 비중을 대폭 상향.

## 6. 가중치 후보 (Weight Candidates)
- **imbalance_10s_score**: 30
- **price_chg_10s_score**: 25
- **volume_10s_score**: 20
- **spread_score**: 15
- **depth_score**: 10
- **absorption_score**: 10
- **continuation_score**: 20
- **sweep_score**: 0
- **총점**: 130점 (Entry Threshold: 85점)

## 7. 실험 절차
1. 기존 3시간 로그를 기반으로 Short-Term Trend v1 가중치를 적용한 백테스트 수행.
2. 300초/600초 보유 시의 net_pnl 비교 분석.
3. Threshold 후보군(75, 85, 95)에 대한 민감도 분석.
4. 마켓별(BTC/XRP/SOL) 성과 차이 진단.
5. 분석 결과가 양수 기대값을 안정적으로 유지할 때만 Paper Trading 적용 고려.

## 8. 금지 및 주의 원칙
- **자동 반영 금지**: 실험 후보 설정을 본체 `config/config.json`에 즉시 반영하지 말 것.
- **실거래 활성화 금지**: Tiny Live 등 실거래 모드 활성화 절대 금지.
- **코드 수정 금지**: `orderflow_paper.py` 등 핵심 로직을 임의로 수정하지 말 것.
- **수익성 우선**: 거래 횟수만을 늘리기 위한 가중치 조정 금지.
