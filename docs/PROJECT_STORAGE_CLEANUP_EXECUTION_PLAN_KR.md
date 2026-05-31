# Project Storage Cleanup Execution Plan

## 1. 개요
본 도구(`tools/execute_project_storage_cleanup.py`)는 앞서 분석된 스토리지 감사 결과를 바탕으로 불필요한 파일을 안전하게 삭제(`SAFE_DELETE`)하거나, 대용량 과거 데이터를 외장/분리된 드라이브로 이동(`ARCHIVE`)하기 위해 사용된다.
안전장치를 극대화하여 **DRY-RUN(모의 실행)을 기본값**으로 동작하며, 명시적인 실행 트리거(`--apply`) 및 토큰(`CLEANUP_EXECUTE`) 없이는 절대 실제 디스크에 변경을 가하지 않는다.

## 2. 보안 및 안전장치
1. **Critical/Tracked 차단**: `src`, `tools`, `docs` 등의 핵심 소스코드나 git에 추적 중인 파일은 어떤 조건에서도 삭제되거나 이동되지 않는다.
2. **핵심 DB 유지**: `reversal_edge_master_dataset.sqlite` 등 필수적인 백테스트/연구 DB는 필터링에서 완전 제외된다.
3. **명시적 토큰 요구**: 실제 파일 처리를 위해서는 `--apply` 플래그와 더불어 `--confirm-token CLEANUP_EXECUTE` 인자를 전달해야 한다.
4. **Archive 경로 확인**: 아카이브 목적지(기본값: `D:\coinB_data_archive`)가 현재 프로젝트 디렉토리 내부라면 경고를 띄운다.

## 3. 분류 기준
- **SAFE_DELETE**:
  - `__pycache__` 디렉토리, `*.pyc` 파일
  - 임시 찌꺼기 파일 (`*.tmp`, `*.bak`, `*.old`)
  - 0바이트 빈 파일
  - 격리 폴더 (`_cleanup_quarantine`) 및 구형 리뷰 스냅샷 폴더 (`_review_snapshot_*`)
- **ARCHIVE**:
  - jsonl 형식의 거대 실험 로그 파일
  - 지난 walk_forward 및 top10_krw_72h_chunks 관련 대용량 청크 파일
  - 지정한 최소 크기(`--min-size-mb`) 이상의 과거 로그 파일 (`*.log`)

## 4. 실행 방법

### 모의 실행 (Dry-Run, 권장)
```powershell
# 실제 삭제 없이 분류 결과와 대상 파일만 리포트로 출력
python tools/execute_project_storage_cleanup.py --dry-run --archive-root D:\coinB_data_archive --delete-safe --move-archive --include-quarantine
```

### 실제 실행 (위험, 주의 요망)
```powershell
# 안전 삭제 및 아카이브 이동을 실제 디스크에 적용
python tools/execute_project_storage_cleanup.py --apply --confirm-token CLEANUP_EXECUTE --delete-safe --move-archive --include-quarantine --archive-root D:\coinB_data_archive
```

## 5. 리포트 출력
실행(모의 및 실제) 후에는 `reports/experiments/project_storage_cleanup_dry_run_latest.txt` 및 `.json`에 다음과 같은 요약이 기록된다:
- 스캔된 총 파일 수 및 크기
- `SAFE_DELETE` 예상(또는 적용) 개수 및 크기
- `ARCHIVE` 예상(또는 적용) 개수 및 크기
- 보호된 파일(`KEEP_CRITICAL`, `BLOCKED_GIT_TRACKED`) 통계
- 실제 적용을 위해 필요한 정확한 명령어 문자열
