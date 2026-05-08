# DevState

## 현재 버전

coinB PRO v3.0.1

## 기준선 상태 (확인 완료)

- python -m compileall src tests → 통과 (25개 파일, 오류 없음)
- python -m unittest discover -s tests -p "test_*.py" → Ran 40 tests OK
- python -m coinb.main validate-config → ok=true, mode=paper, live.enabled=false
- regime.py 이중 중복 코드 제거 완료
- 모든 .py 파일 LF 정규화 완료
- 모든 .bat 파일 CRLF 정규화 완료
- __pycache__ / .pyc 제거 완료

## 실행 파일

- START_COINB.bat : Windows 메뉴 실행기 (검증/paper/tuner 포함)
- PowerShell 검증 명령:
  $env:PYTHONPATH = "$PWD\src"
  python -m compileall src tests
  python -m unittest discover -s tests -p "test_*.py"
  python -m coinb.main validate-config --config config/config.json

## 제한 사항

- live.enabled=false 고정 (config_loader.py에서 코드로 차단)
- 실거래 주문 코드 없음
- API Key 없음
- paper/backtest/tune/report 모드만 동작

## 다음 단계

v3.1: 실전형 가상매매 엔진 고도화 (승인 후 별도 브랜치)
