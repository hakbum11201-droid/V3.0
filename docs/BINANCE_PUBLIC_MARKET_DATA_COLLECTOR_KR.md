# Binance Public Market Data Collector

## 1. 목적
Cross-Market Lead-Lag 전략 연구의 첫 번째 인프라 단계로, Binance 글로벌 마켓의 공개 시세/호가 데이터를 수집하여 Upbit KRW 마켓과의 선행 관계를 분석하기 위한 기반 데이터를 확보한다.

> **API Key 불필요.** Binance Public WebSocket 및 REST Public Endpoint만 사용한다.  
> **주문/실거래 기능 없음.** 순수 시장 데이터 수집 전용 도구다.

---

## 2. 수집 방식

| 모드 | 설명 |
|------|------|
| `ws` (WebSocket) | `wss://stream.binance.com:9443/stream?streams=` 를 통해 trade + bookTicker 스트림 수신 |
| `rest` (REST 폴링) | `GET /api/v3/ticker/bookTicker` 를 주기적으로 호출 |
| `auto` (기본값) | WebSocket 우선 시도 → 실패 시 REST fallback |

---

## 3. 저장 구조

**DB 경로:** `logs/experiments/cross_market/binance_public_market_data.sqlite`

### `binance_events` 테이블
| 컬럼 | 설명 |
|------|------|
| `received_ts` | 로컬 수신 타임스탬프 (Unix epoch float) |
| `event_ts` | Binance 이벤트 원본 타임스탬프 |
| `symbol` | 예: `BTCUSDT` |
| `event_type` | `trade`, `bookTicker`, `bookTicker_rest` 등 |
| `price` | 체결가 (trade 이벤트) |
| `qty` | 체결량 (trade 이벤트) |
| `side` | `BUY` / `SELL` |
| `best_bid` | 최우선 매수호가 |
| `best_ask` | 최우선 매도호가 |
| `raw_json` | 원본 JSON 페이로드 |

### `collector_runs` 테이블
각 수집 세션의 요약 정보를 기록한다.

---

## 4. 사용법

```powershell
# 기본 실행 (60초, 기본 5개 심볼, auto 모드)
python tools/collect_binance_public_market_data.py

# 심볼 지정, 300초 수집
python tools/collect_binance_public_market_data.py --symbols BTCUSDT,SOLUSDT --duration-sec 300

# REST 전용 모드
python tools/collect_binance_public_market_data.py --mode rest --duration-sec 120

# WebSocket 전용 모드
python tools/collect_binance_public_market_data.py --mode ws --duration-sec 600
```

---

## 5. 의존성

```
websocket-client   # WebSocket 모드용 (없으면 REST fallback)
requests           # REST 모드용
```

```powershell
pip install websocket-client requests
```

---

## 6. 보안 원칙

- API Key / Secret **절대 사용하지 않음**
- 주문/체결/잔고 조회 엔드포인트 **없음**
- `.gitignore`에 의해 `logs/experiments/cross_market/*.sqlite`는 커밋되지 않음

---

## 7. 다음 단계

1. 수집기를 일정 시간(예: 1~7일) 백그라운드로 구동하여 데이터 확보
2. Upbit KRW 마켓 데이터와 타임스탬프 정렬 (`received_ts` 기준 ±5초 이내)
3. Cross-Market Lead-Lag 분석 도구 (`analyze_cross_market_lead_lag.py`) 작성
