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
