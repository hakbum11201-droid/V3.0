# Project Storage Cleanup Audit

## 1. 목적
V3.0 프로젝트가 장기간의 연구 및 백테스트 스냅샷 생성으로 인해 총 150GB 이상으로 커짐에 따라, 향후 진행될 김프/양쪽매매 개선 등의 원활한 연구를 위해 스토리지 다이어트가 필요해졌다.
본 문서는 실제 파일을 삭제하기 전에 프로젝트 전체의 용량 분포를 분석하고, 안전하게 삭제할 수 있는 파일과 백업/보관이 필요한 대용량 데이터를 분류하는 기준을 정의한다.

## 2. 파일 분류 기준

### A. KEEP_CRITICAL (절대 유지)
- `src/`, `config/`, `configs/`, `tests/` 폴더 내의 모든 파일
- `requirements.txt`, `README.md`, `AGENTS.md`
- 핵심 실행 배치 파일 (`START_COINB.bat`, `STOP_COINB_ALL.bat`, `RUN_COINB_ALL.bat`)
- 현재 Git에 추적(Tracked) 중인 `tools/*.py` 및 `docs/*.md`

### B. KEEP_DATA_FOR_RESEARCH (연구용 데이터 유지)
- 최신 마스터 데이터셋 (`reversal_edge_master_dataset.sqlite`)
- Cross-Market 연구용 데이터 (`binance_public_market_data.sqlite`)
- 최근 분석 결과 리포트 (`latest` 태그가 붙은 `.json`, `.txt`)

### C. SAFE_DELETE_CANDIDATE (안전 삭제 후보)
- `__pycache__` 폴더 및 `*.pyc` 파일
- 임시 파일 (`*.tmp`, `*.bak`, `*.old`)
- 내용이 없는 빈 파일 (크기 0 bytes)
- 명백한 실험 스냅샷 복사본 및 오래된 중복 zip 아카이브
- `_cleanup_quarantine` 및 `_review_snapshot_*` 내부의 파일들

### D. QUARANTINE_CANDIDATE (격리/검토 후 삭제 후보)
- 더 이상 사용되지 않는 오래된 `RUN_*.bat` 및 실험 전용 배치 파일
- 현재 `tools/`의 스크립트로 대체된 구형 repair/check 임시 스크립트
- Git에 추적되지 않는 중복 `.md` 문서
- 과거 실험에 생성된 오래된 `reports/`, `logs/`, `*.jsonl` 데이터

### E. REVIEW_MANUALLY (수동 검토 요망)
- 삭제 기준에 명확히 부합하지 않는 문서나 최근 수정된 실험 스크립트
- 이름만으로 용도를 파악하기 어려운 대용량 데이터 파일

## 3. 후속 조치 프로세스
1. 본 Audit 도구(`tools/audit_project_storage_cleanup.py`)를 실행하여 `reports/experiments/project_storage_cleanup_audit_latest.txt` 리포트를 생성한다.
2. 리포트를 통해 `SAFE_DELETE_CANDIDATE` 및 `QUARANTINE_CANDIDATE`의 예상 용량과 파일 수를 확인한다.
3. 확인 후 사용자의 승인을 얻어 실제 삭제 스크립트를 작성하여 정리를 수행한다.
4. `DATA_ARCHIVE` 후보로 분류된 10MB 이상의 대용량 파일은 별도의 외장 스토리지나 압축 아카이브로 이동할지 결정한다.
