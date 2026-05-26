# Top 10 KRW Chunk Collector Plan

## 1. 개요
본 데이터 수집기는 업비트 공개 WebSocket(Public API)만을 사용하여, "24시간 거래대금 상위 10개 KRW 마켓"에 대한 주문흐름(Orderflow) 및 호가창(Orderbook) 데이터를 수집하기 위해 고안되었습니다. 실거래 연동 및 API Key가 절대 사용되지 않는 순수 연구/검증용 데이터 파이프라인입니다.

## 2. 수집 방식 설계 (Chunk-based)
단일 스크립트로 72시간을 연속 가동할 경우, 네트워크 불안정이나 OS 업데이트 등으로 스크립트가 중단되면 전체 데이터가 유실되는 치명적 문제가 발생합니다. 이를 방지하기 위해 **Chunk 분할 수집**을 도입했습니다.
- **전체 수집 목표**: 72시간 (총 144개 Chunk)
- **Chunk 단위**: 30분
- **단일 파일 동시 저장**: 10개 마켓의 데이터가 1개의 Chunk 파일에 함께 기록됩니다.
- **Manifest 기반 Resume**: `status=="success"`인 Chunk는 재실행 시 건너뛰며(Skip), 실패한 구간부터 이어서 수집합니다. 최대 3회 자동 재시도합니다.

## 3. Top 10 마켓 선정 원칙
수집이 처음 시작되는 시점에 업비트 공개 API(`/v1/ticker`, `/v1/market/all`)를 조회하여 24시간 거래대금(acc_trade_price_24h) 기준 상위 10개 KRW 마켓을 추출합니다.
- **제외 대상**: 스테이블코인 및 환율성 마켓(`KRW-USDT`, `KRW-USDC`, `KRW-DAI`)은 실전 Reversal 전략에 부합하지 않으므로 Top 10 선정에서 제외(`stablecoin_or_fx_like_market_excluded`)합니다.
- 선정된 Top 10 리스트는 `manifest` 파일에 영구 기록(고정)됩니다.
- 수집 진행 중 거래대금 순위가 바뀌더라도 해당 세션(Run)에서는 마켓 목록을 변경하지 않습니다.

## 4. 수집 완료 후 필수 파이프라인 실행 순서
데이터 수집(72h)이 완료된 후, 아래의 스크립트들을 **순서대로** 실행해야만 전체 마켓 공통 피처 검증이 마무리됩니다.

1. `RUN_BUILD_MASTER_VALIDATION_DATASET.bat`
2. `RUN_BUILD_MASTER_DATASET_CACHE.bat`
3. `RUN_AUDIT_MARKET_COVERAGE.bat`
4. `RUN_VALIDATE_TOP10_REVERSAL_FEATURES.bat`
5. `RUN_DISCOVER_CROSS_MARKET_REVERSAL_FEATURES.bat`
6. `RUN_CROSS_MARKET_REVERSAL_VALIDATION.bat`
7. `RUN_AUTO_RESEARCH_REPORT.bat`

## 5. 제약 및 안전 지침
- **실거래(live.enabled) 전환 금지**: 수집 중이나 완료 직후에도 자동으로 실거래가 켜지지 않도록 철저히 차단됩니다.
- **Config / Candidate 수정 보류**: 파이프라인이 전부 통과하기 전까지 기존 `candidate` 파일이나 `config.json`을 수정해서는 안 됩니다.
