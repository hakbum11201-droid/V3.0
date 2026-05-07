# coinB PRO v3.0

운영형 자동매매 연구 프레임워크입니다. 기본값은 **paper/backtest**이며, 실거래 주문은 기본 차단되어 있습니다.

## 핵심 기능

- 멀티팩터 전략: EMA 추세, 돌파, RSI 과열 방지, ATR 변동성, 거래량 참여도
- 시장 국면 필터: BTC 기준 risk-on / neutral / risk-off 분기
- 손실 패턴 차단: 연속 손실, 특정 마켓 쿨다운, 최근 성과 악화 차단
- 리스크 관리: 최소 주문금액, 포지션 한도, 일 손실, 총 손실, 최대 동시 포지션
- 페이퍼 브로커: 수수료, 슬리피지, 손절, 익절, ATR 트레일링 반영
- 성과 분석: 승률, 손익비, 기대값, MDD, 연속 손실, 마켓별 성과
- 자동 튜너: 파라미터 그리드 탐색 후 성과 요약 생성
- Windows BAT 실행 파일 포함
- 테스트 코드 포함

## 실행

```bat
run_all_check.bat
```

개별 실행:

```bat
run_tests.bat
run_backtest.bat
run_report.bat
run_tuner.bat
```

## 산출물

- `logs/trades.jsonl` : 가상 거래 로그
- `logs/decisions.jsonl` : 진입/비진입 판단 로그
- `runtime/state.json` : 상태 저장
- `reports/performance_summary.json` : 성과 분석
- `reports/tuner_summary.json` : 튜너 결과

## 실거래 관련

이 패키지는 실거래 주문 기능을 기본 제공하지 않습니다. 실거래 전에는 다음이 먼저 필요합니다.

1. 최소 2~4주 페이퍼 로그 축적
2. 승률보다 기대값(EV), MDD, 연속 손실 확인
3. 슬리피지/부분체결/주문 실패 모델 보강
4. API Key 보안 저장
5. 주문 테스트 API 및 소액 실거래 검증

## 주의

이 프로그램은 수익을 보장하지 않습니다. 가상자산 거래는 원금 손실 가능성이 큽니다.
