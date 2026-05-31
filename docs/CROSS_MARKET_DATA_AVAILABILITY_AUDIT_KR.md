# Cross-Market Data Availability Audit

## 1. 목적
Upbit 단일 마켓 기반의 전략이 수수료 및 슬리피지(총 0.05%~0.10%) 장벽을 안정적으로 넘기 어렵다는 결론에 도달함에 따라, 향후 연구 방향으로 Binance 등 글로벌 대형 거래소의 선행 정보(Lead-Lag)를 활용한 크로스 마켓 엣지 탐색을 기획한다.
본 감사는 새로운 코드를 작성하기에 앞서 현재 데이터베이스와 인프라에 Binance 데이터가 이미 확보되어 있는지, 퍼블릭 API를 사용해 데이터를 수집할 수 있는지를 진단하는 과정이다.

## 2. 핵심 점검 사항
1. **SQLite 내부 Binance 데이터 존재 여부**: `events` 테이블의 `market` 혹은 `raw_json` 내에 USDT/BTCUSDT 마켓 정보가 있는지 확인.
2. **Upbit-Binance 마켓 매핑 가능성**: `KRW-BTC -> BTCUSDT` 형식의 Base Symbol 매핑이 성립하는 마켓 수.
3. **Binance Public API 연결 테스트**: API Key 발급 및 인증 없이 Public Endpoint(ticker, depth)에서 실시간 조회가 가능한지 테스트.

## 3. 결과 (스크립트 실행 후 갱신)
- `tools/audit_cross_market_data_availability.py`의 리포트 결과 참조.
- `NO_CROSS_MARKET_DATA_FOUND` 상태에서 API가 정상 동작한다면, `BINANCE_PUBLIC_COLLECTOR_NEEDED`로 판정하여 데이터 수집기를 새롭게 기획해야 한다.
