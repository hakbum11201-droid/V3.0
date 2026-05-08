===== coinB PRO v3.0.1 시작 가이드 =====

1. PowerShell에서 PYTHONPATH를 먼저 설정하세요:
   $env:PYTHONPATH = "$PWD\src"

2. START_COINB.bat을 실행하세요 (메뉴 선택 방식).

3. [1] Basic Check를 먼저 실행하세요.

정상 기준:
  (1) validate-config 통과
  (2) unittest 40개 OK
  (3) backtest 실행 성공
  (4) report 생성 성공
  (5) tuner 후보 생성 성공

오류 발생 시:
  검은 창의 에러 내용을 복사해서 ChatGPT에 붙여넣으세요.

주의:
  이 버전은 paper/backtest 전용입니다.
  live.enabled=false가 코드로 강제됩니다.
  실거래 주문은 실행되지 않습니다.
