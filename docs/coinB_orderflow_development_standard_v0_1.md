# coinB 주문흐름 기반 자동매매 개발 기준서 v0.1

## 0. 문서 목적

이 문서는 `coinB / V3.0` 프로젝트의 향후 개발 기준을 고정하기 위한 문서다.

기존의 후행성 차트 지표 중심 전략에서 벗어나, 업비트 KRW 마켓의 실시간 체결·호가 데이터를 기반으로 주문흐름을 분석하고, 가매수·가매도 데이터를 축적하여 점진적으로 전략을 개선하는 것을 목표로 한다.

핵심 방향은 다음과 같다.

```text
Upbit KRW 마켓 기준
→ 실시간 체결/호가 수집
→ 주문흐름 특징값 계산
→ 가매수/가매도
→ 로그 축적
→ 성과 분석
→ config 후보 자동 튜닝
→ 충분한 paper 검증
→ tiny_live 소액 실거래
```

---

## 1. 최상위 원칙

### 1.1 거래소 기준

```text
거래소: Upbit
마켓: KRW 마켓
실전 매매: Upbit
가매수/가매도: Upbit 시세 기준
데이터 축적: Upbit 체결/호가/티커 기준
```

외부 거래소 데이터는 보조 필터로만 사용한다.

예:

```text
Binance Futures Open Interest
Funding Rate
Long/Short Ratio
Taker Buy/Sell Volume
```

단, 매매 실행과 가매매 기준은 항상 Upbit KRW 마켓이다.

---

## 2. 전략 철학

### 2.1 후행성 지표 의존 최소화

아래 지표들은 중심 전략이 아니라 보조 참고용으로만 사용한다.

```text
EMA
RSI
MACD
Bollinger Band
ATR
이동평균선
일반 매물대
과거 지지선/저항선
```

이 지표들은 대부분 가격이 움직인 뒤 계산되는 후행성 지표다.  
따라서 최종 전략의 핵심 신호가 되어서는 안 된다.

---

## 3. 중심 매매 구조

최종 전략의 중심은 다음 네 가지다.

```text
Order Flow Imbalance
+ Liquidity Sweep
+ Absorption
+ Continuation Confirmation
```

즉, 차트 모양이 아니라 실제 돈이 들어오고 빠지는 흐름을 본다.

---

## 4. 핵심 개념

### 4.1 Order Flow Imbalance, OFI

짧은 시간 동안 시장가 매수와 시장가 매도 중 어느 쪽이 우세한지 계산한다.

예시:

```text
최근 3초 시장가 매수 체결금액 = 180,000,000 KRW
최근 3초 시장가 매도 체결금액 = 60,000,000 KRW
매수 우위 비율 = 3.0
```

주요 특징값:

```text
buy_trade_value_1s
sell_trade_value_1s
buy_trade_value_3s
sell_trade_value_3s
buy_sell_imbalance_3s
trade_count_per_second
large_trade_count
avg_trade_value
```

---

### 4.2 Orderbook Imbalance

상위 호가의 매수 잔량과 매도 잔량 불균형을 본다.

예시:

```text
상위 5호가 매수 잔량 / 상위 5호가 매도 잔량 >= 1.7
```

주요 특징값:

```text
bid_depth_1
ask_depth_1
bid_depth_5
ask_depth_5
bid_ask_depth_ratio_5
spread_tick
spread_pct
ask_wall_change_pct
bid_wall_change_pct
```

---

### 4.3 Liquidity Sweep

짧은 시간 안에 여러 호가가 연속으로 먹히는 움직임을 감지한다.

예시:

```text
0.8초 안에 가격 4틱 상승
동시에 시장가 매수 체결 급증
상위 매도호가 잔량 급감
```

주요 특징값:

```text
price_tick_move_1s
price_tick_move_3s
ask_depth_drop_pct
buy_trade_burst_score
sweep_score
```

---

### 4.4 Absorption

강한 시장가 매도가 나왔는데도 가격이 잘 밀리지 않으면 흡수로 본다.

예시:

```text
시장가 매도 체결금액 급증
하지만 가격 하락폭은 작음
매수호가가 계속 보충됨
```

주요 특징값:

```text
sell_trade_value_3s
price_drop_pct_3s
bid_replenish_score
absorption_score
```

---

### 4.5 Continuation Confirmation

Sweep 또는 Absorption만으로 바로 진입하지 않는다.  
마지막으로 흐름이 이어지는지 확인한다.

확인 조건 예시:

```text
매수 체결 우위 유지
스프레드 과도하게 벌어지지 않음
상단 매도벽 감소
가격이 직전 체결 고점 위에서 유지
```

---

## 5. 최종 프로그램 구조

최종 구조는 다음 방향으로 확장한다.

```text
1. Upbit WebSocket Collector
   - trade 수집
   - orderbook 수집
   - ticker 수집

2. Microstructure Feature Engine
   - 최근 1초/3초/10초 체결금액
   - 시장가 매수/매도 비율
   - 호가 불균형
   - 호가벽 생성/소멸
   - 스프레드
   - 가격 충격
   - 체결 속도

3. Signal Engine
   - OFI 감지
   - Sweep 감지
   - Absorption 감지
   - Continuation 감지
   - Fake move 차단

4. Paper Execution Engine
   - Upbit 호가 기준 가매수
   - Upbit 호가 기준 가매도
   - 수수료 반영
   - 슬리피지 반영
   - 체결 가능성 점수 반영

5. Learning Logger
   - 진입 당시 체결/호가 상태 저장
   - 진입 후 10초/30초/1분/3분 결과 저장
   - 실패 패턴 저장

6. Auto Tuner
   - 체결강도 기준 자동 조정
   - 호가 불균형 기준 자동 조정
   - 손실 패턴 자동 차단
   - config 후보 생성
```

---

## 6. 현재 V3.0과 목표 구조의 차이

현재 V3.0은 기본적으로 다음 구조다.

```text
CSV 캔들
→ EMA / RSI / ATR / 돌파
→ 가매수 / 가매도
→ 성과 분석
```

목표 구조는 다음이다.

```text
Upbit 실시간 체결/호가
→ 주문흐름 특징값 계산
→ 선행성 신호 감지
→ 가매수 / 가매도
→ 결과 로그 축적
→ 자동 튜닝
```

현재 V3.0은 최종 전략이 아니라 복구용 베이스로 본다.

---

## 7. 필수 로그 항목

가매수·가매도마다 아래 정보를 남긴다.

```text
timestamp
market
mode
entry_signal_type
signal_score
entry_reason
entry_price
virtual_buy_price
qty
fee_krw
slippage_pct
spread_pct
buy_trade_value_1s
sell_trade_value_1s
buy_trade_value_3s
sell_trade_value_3s
buy_sell_imbalance_3s
bid_depth_5
ask_depth_5
bid_ask_depth_ratio_5
ask_wall_change_pct
bid_wall_change_pct
sweep_score
absorption_score
continuation_score
exit_reason
virtual_sell_price
pnl_pct
pnl_krw
max_profit_pct
max_drawdown_pct
holding_seconds
```

---

## 8. 자동 수정 원칙

자동으로 코드를 수정하지 않는다.  
자동으로 바꿔야 하는 것은 `config` 값이다.

예시:

```json
{
  "microstructure": {
    "buy_sell_imbalance_min": 2.2,
    "sweep_score_min": 70,
    "absorption_score_min": 65,
    "continuation_score_min": 65,
    "max_spread_pct": 0.12,
    "min_trade_value_3s": 30000000
  }
}
```

튜너 흐름:

```text
기존 config
→ 가매매 로그 분석
→ 후보 config 생성
→ replay/backtest 검증
→ 성과 나쁘면 폐기
→ 성과 좋으면 config_candidate.json 저장
→ 사용자 승인 후 적용
```

초기 단계에서는 자동 적용 금지.  
후보 생성까지만 자동화한다.

---

## 9. 개발 진행 순서

현재 개발 순서는 다음으로 고정한다.

```text
STEP A. 깨진 V3.0 파일 정상화
STEP B. START_COINB.bat 전체 점검 통과
STEP C. 기존 캔들 기반 paper/backtest 작동 확인
STEP D. Upbit 실시간 trade/orderbook 수집기 추가
STEP E. microstructure feature 계산기 추가
STEP F. 실시간 가매수/가매도 paper loop 추가
STEP G. 학습용 로그 저장 고도화
STEP H. 손실 패턴 분석기 추가
STEP I. config 후보 자동 생성 튜너 추가
STEP J. 장기 paper 검증
STEP K. tiny_live 소액 실거래 검증
```

---

## 10. 코드 수정 원칙

### 10.1 ZIP 일괄 교체 금지

앞으로 ZIP 전체 교체를 하지 않는다.

```text
파일 1개 또는 최대 3개
→ 전체 교체 코드 제공
→ 사용자가 붙여넣기
→ 로컬 실행 확인
→ 커밋/푸시
→ GitHub 기준 재검토
```

---

### 10.2 한 번에 하나의 기능만 수정

좋은 예:

```text
upbit_ws.py 생성만 진행
```

나쁜 예:

```text
upbit_ws + tuner + live trading + UI를 한 번에 추가
```

---

### 10.3 실거래 기본 차단

기본값은 항상 paper다.

```text
paper = 기본
tiny_live = 나중에 명시적으로 허용
live = 초기에는 잠금
```

---

## 11. 금지 사항

```text
승률 보장 문구 금지
실거래 기본 ON 금지
API 키 코드 삽입 금지
손실 제한 제거 금지
최소 주문금액 체크 제거 금지
로그 없이 전략 변경 금지
후행 차트 지표만으로 매수 판단 금지
config 자동 적용을 초기부터 허용 금지
```

---

## 12. 최종 목표

최종 목표는 단순 지표 매매봇이 아니다.

```text
Upbit 실시간 주문흐름을 읽고
가상으로 계속 매수·매도해보고
결과를 저장하고
손실 패턴을 자동으로 줄이고
기대값이 높은 조건만 남기는 프로그램
```

이 문서를 앞으로 `coinB / V3.0` 이후 모든 수정의 기준으로 사용한다.