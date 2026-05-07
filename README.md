# coinB PRO v3.0.1

운영형 자동매매 연구 프레임워크입니다. 기본값은 `paper/backtest`이며, 실거래 주문은 차단되어 있습니다.

## 실행 순서

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

## 핵심 출력

- `logs/trades.jsonl`
- `logs/decisions.jsonl`
- `reports/backtest_result.json`
- `reports/performance_summary.json`
- `reports/tuner_summary.json`

## 중요

이 버전은 실거래용이 아닙니다.  
v4 단계에서 tiny_live를 별도 구현하기 전까지 API 실주문 코드는 넣지 않습니다.
