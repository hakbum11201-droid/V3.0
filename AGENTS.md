# AGENTS.md

## 문서 우선순위

작업 전 반드시 `docs/README_DOCS_KR.md`를 먼저 확인한다.

문서 간 내용이 충돌할 경우 우선순위는 다음과 같다.

1. `docs/V3_LIVE_TRADING_MASTER_PLAN_KR.md`
2. `docs/DevState.md`
3. `docs/V3_ROADMAP_KR.md`
4. `docs/SECURITY_KEY_POLICY_KR.md`
5. `docs/V3_UI_DDM_ROADMAP_KR.md`
6. `docs/SAFETY_CHECKLIST_KR.md`

최종 목표, 전략 철학, 실거래 전환 기준은 항상 `docs/V3_LIVE_TRADING_MASTER_PLAN_KR.md`를 따른다.

현재 진행 상태는 항상 `docs/DevState.md`를 따른다.

작업 순서는 항상 `docs/V3_ROADMAP_KR.md`를 따른다.

API Key, GitHub 공개 저장소, 해킹 방어, secret_guard 관련 기준은 항상 `docs/SECURITY_KEY_POLICY_KR.md`를 따른다.

UI, DDM, 대시보드 관련 세부 계획은 `docs/V3_UI_DDM_ROADMAP_KR.md`를 따른다.

실거래 전 최종 점검은 `docs/SAFETY_CHECKLIST_KR.md`를 따른다.

문서 간 충돌이 있으면 상위 문서를 우선하고, 임의로 판단하지 않는다.

---

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
python tools/secret_guard.py