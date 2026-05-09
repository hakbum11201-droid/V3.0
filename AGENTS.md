# AGENTS.md

## 작업 원칙

- **목표:** 단순 프로토타입이 아닌, 1인 개인이 실사용 가능한 장기 운영 자동매매 시스템 구축.
- **모드 관리:** 기본 모드는 `paper`이며, 실거래 전환은 철저한 검증(tiny_live) 후에만 진행한다.
- **코드 무결성:** 한 번에 하나의 기능만 수정하며, 기존 파일명과 함수명은 함부로 변경하지 않는다.
- **안전 검증:** 작업 전후 아래 명령으로 시스템 상태를 상시 검증한다.
```powershell
$env:PYTHONPATH = "$PWD\src"
python -m compileall src tests
python -m unittest discover -s tests -p "test_*.py"
python -m coinb.main validate-config --config config/config.json
```
- **제한:** `live.enabled=false` 및 `default_mode=paper` 설정은 별도 승인 전까지 변경을 엄격히 금지한다.
- **전략 방향:** 후행성 차트 지표가 아닌, 업비트 WebSocket 실시간 체결/호가 기반의 **주문흐름 스캘핑(Orderflow Scalping)** 시스템 구축을 최우선으로 한다.
- **Net Edge 원칙:** 모든 거래 성과는 수수료, 스프레드, 슬리피지를 차감한 **순이익(Net PnL)** 기준으로 판단하며, 기대값이 확실한 거래만 선별한다.
- **실험 원칙:** 거래 횟수를 늘리기 위해 무리하게 조건을 완화하지 않으며, Conservative -> Moderate 순서의 실험을 통해 시장 현실에 맞는 최적의 기준점을 찾는다.

## UI 및 DDM 개발 원칙 (V3.1+)

- **UI 언어:** 대시보드 및 리포트 요약 등 사용자가 보는 UI는 한국어를 기본으로 한다. (내부 데이터 구조는 영어 유지)
- **DDM 우선:** DDM(Drawdown Defense Manager)은 손실 방어 및 신규 진입 차단을 최우선 목표로 하며, 위험 감지 시 `should_block_new_entry`를 통해 시스템을 보호한다.
- **보안:** 실제 계좌 연동 시 자산 조회 전용(Read-Only) API Key만 사용하며, `.env` 파일로 철저히 격리한다. 주문 권한이 있는 Key는 별도의 실거래 단계(tiny_live) 진입 시에만 제한적으로 사용한다.
- **수동 개입:** 설정값(Config)은 시스템이 제안한 후보를 사람이 직접 검토한 후 수동으로 반영하는 것을 원칙으로 한다.
