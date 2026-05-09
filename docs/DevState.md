# DevState

## 현재 버전

coinB PRO v3.1.2 (UI & DDM Foundation 완료)

## 기준선 상태 (확인 완료)

- python -m compileall src tests → 통과
- python -m unittest discover -s tests -p "test_*.py" → Ran 40 tests OK
- python -m coinb.main validate-config → ok=true, mode=paper, live.enabled=false
- paper-review, paper-config-candidates 및 loss-analysis 연동 완료
- 모든 리포트 및 터미널 출력 UTF-8 정규화(한글 깨짐 해결) 완료
- **Streamlit UI(한국어) 및 백그라운드 paper_engine 구동 확인**
- **DDM(Drawdown Defense Manager) 상태 계산 및 UI 시각화 완료**
- **DDM Gate를 통한 Paper 신규 진입 차단 기능 연동 완료**

## 실행 파일

- START_COINB.bat : Windows 메뉴 실행기
- RUN_PAPER_LOOP_1H.bat : 1시간 Paper Loop 검증기
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

v3.1: 개인용 관제 UI(Streamlit) + DDM(Drawdown Defense Manager) 및 계좌 추적 연동
- 세부 로드맵: `docs/V3_UI_DDM_ROADMAP_KR.md` 참조
