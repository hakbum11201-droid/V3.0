# AGENTS.md

## 작업 원칙

- 기본 모드는 paper/backtest입니다.
- 실거래 주문 코드는 v3.x에 추가하지 않습니다.
- 한 번에 하나의 기능만 수정합니다.
- 기존 파일명과 함수명을 확인한 뒤 수정합니다.
- 작업 전후 검증은 아래 명령으로 수행합니다 (PowerShell 기준):

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m compileall src tests
python -m unittest discover -s tests -p "test_*.py"
python -m coinb.main validate-config --config config/config.json
```

- START_COINB.bat [1] Basic Check 로도 동일하게 검증할 수 있습니다.
- 자동 튜너는 코드를 수정하지 않고 설정 후보만 생성합니다.
- live.enabled=false 및 default_mode=paper는 변경 금지입니다.

## 향후 UI 및 DDM 개발 원칙 (v3.1)

- UI는 Streamlit 기반의 로컬 관제용(개인용)으로만 구축합니다.
- UI에서 실거래 기능을 켜거나 활성화하는 버튼은 만들지 않습니다.
- DDM(Drawdown Defense Manager)은 "손실 방어 및 신규 진입 차단"을 최우선 목표로 하며 청산 로직은 차단하지 않습니다.
- 실제 계좌 조회 기능 연동 시, 주문 권한이 없는 '조회 전용' API Key만 사용하며 .env 파일로 격리합니다.
