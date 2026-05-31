# Cross-Market Payload Quality Audit

## 1. 목적
이전 단계의 감사에서 SQLite 데이터베이스의 `events` 테이블 `raw_json` 컬럼 내부에 Binance 및 USDT 관련 문자열 흔적이 존재함(`Has Binance Keywords: True`)을 확인했다.
이번 감사의 목적은 해당 흔적이 **실제 바이낸스 시장 데이터(호가/체결/티커)**인지, 아니면 단순한 텍스트 멘션이나 메타데이터에 불과한지 분석하여, 기존 DB만으로 Cross-Market Lead-Lag 전략 연구가 가능한지 판단하는 것이다.

## 2. 핵심 점검 사항
1. **raw_json 내부 샘플 추출**: `BINANCE`, `BTCUSDT`, `USDT` 등의 키워드가 포함된 row를 최대 200건 추출.
2. **구조 분석 및 분류**: JSON 파싱 후 필드 구조(`bids`, `asks`, `orderbook_units`, `lastUpdateId` 등)를 통해 실제 Binance 데이터 포맷인지 판별.
3. **분류 항목**: 
   - `REAL_BINANCE_TICKER`
   - `REAL_BINANCE_ORDERBOOK`
   - `REAL_BINANCE_TRADE`
   - `UPBIT_ONLY`
   - `METADATA_ONLY`
   - `TEXT_MENTION_ONLY`
4. **밀도 및 정합성 검토**: 실제 데이터일 경우, 심볼(BTCUSDT 등) 존재 여부와 Upbit KRW 마켓과의 타임스탬프 겹침 여부를 확인.

## 3. 결과 (스크립트 실행 후 갱신)
- 결과 리포트: `reports/experiments/cross_market_payload_quality_audit_latest.txt`
- 판정(Judgement)이 `BINANCE_COLLECTOR_REQUIRED` 이거나 `ONLY_TEXT_MENTION_FOUND`일 경우, Binance 전용 실시간 데이터 수집기를 새롭게 구현하여 백그라운드로 가동하는 단계로 넘어가야 한다.
