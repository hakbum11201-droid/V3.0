# AGENTS.md

## 1. 문서 우선순위 원칙
작업 전 반드시 `docs/README_DOCS_KR.md`를 먼저 확인한다. 문서 간 내용이 충돌할 경우 아래 순서를 엄격히 따른다.

1. `docs/V3_LIVE_TRADING_MASTER_PLAN_KR.md` (최상위 목표/철학)
2. `docs/DevState.md` (진행 상태)
3. `docs/CURRENT_RESEARCH_STATE_KR.md` (연구/전략 현황)
4. `docs/V3_ROADMAP_KR.md` (작업 순서)
5. `docs/SECURITY_KEY_POLICY_KR.md` (보안/Secret Guard)
6. `docs/V3_UI_DDM_ROADMAP_KR.md` (UI/대시보드 계획)
7. `docs/SAFETY_CHECKLIST_KR.md` (실거래 최종 점검)

---

## 2. 핵심 작업 원칙
- **개발 목표**: 1인 개인이 실사용 가능한 장기 운영 자동매매 시스템 구축.
- **모드 관리**: 기본 모드는 `paper`이며, 실거래(`tiny_live`)는 철저한 검증 후에만 수동 전환한다.
- **코드 무결성**: 한 번에 하나의 기능만 수정하며, 기존 파일명과 함수명은 함부로 변경하지 않는다.
- **안전 검증**: 작업 전후 아래 명령으로 시스템 상태를 상시 검증한다.

### 안전 검증 명령 (PowerShell)
```powershell
# 1. 환경 설정 및 컴파일 체크
$env:PYTHONPATH = "$PWD\src"
python -m compileall src tests

# 2. 단위 테스트 실행
python -m unittest discover -s tests -p "test_*.py"

# 3. 설정 파일 유효성 검사
python -m coinb.main validate-config --config config/config.json

# 4. 보안 및 API Key 유출 검사
python tools/secret_guard.py
```

---

## 3. 세부 설계 지침
### UI / DDM 원칙
- 모든 대시보드 및 관제 UI 계획은 `docs/V3_UI_DDM_ROADMAP_KR.md`를 따른다.
- Drawdown 발생 시 신규 진입을 자동으로 차단하는 DDM 로직의 무결성을 최우선으로 한다.

### 보안 지침
- API Key, GitHub 공개 저장소 관리 기준은 `docs/SECURITY_KEY_POLICY_KR.md`를 준수한다.
- `secret_guard.py` 검증을 통과하지 못한 코드는 커밋하지 않는다.