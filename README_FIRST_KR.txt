coinB PRO v3.0 사용 순서

1) 이 ZIP 안의 내용물을 coinB 저장소 루트에 그대로 복사합니다.
   - 정상: coinB\src, coinB\config, coinB\run_all_check.bat 가 바로 보임
   - 비정상: coinB\coinB_PRO_V3_0_ROOT_READY\src 처럼 한 단계 더 들어감

2) 먼저 전체 점검 실행:
   run_all_check.bat

3) 결과 확인:
   - logs/trades.jsonl
   - logs/decisions.jsonl
   - reports/performance_summary.json
   - reports/tuner_summary.json

4) GitHub 반영:
   git add .
   git commit -m "release: add coinB pro v3.0 baseline"
   git push

중요:
- 기본값은 paper/backtest입니다.
- 실거래 주문은 기본 차단되어 있습니다.
- API Key를 코드에 넣지 마세요.
- 승률/수익은 보장하지 않습니다. 반드시 장기 페이퍼 검증 후 판단해야 합니다.
