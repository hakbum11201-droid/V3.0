# Reversal Edge v2 OOS Chunk Merge 설계안

## 1. 배경 및 목적

`run_reversal_oos_chunk_runner.py`를 통해 생성된 30분 단위의 수많은 chunk jsonl 파일들을
백테스팅 및 분석에 사용할 수 있도록 단일 파일로 병합(Merge)해야 한다.

이 병합 과정에서 중복 데이터 제거, 파싱 오류 데이터 무시, 그리고 시간순 정렬을 수행하여 
깔끔한 OOS(Out of Sample) 데이터셋을 구축한다.

## 2. 파일 구성

| 파일 | 역할 |
|------|------|
| `tools/merge_ws_chunks.py` | 병합 도구 파이썬 스크립트 |
| `RUN_MERGE_REVERSAL_OOS_CHUNKS.bat` | Windows 실행 배치 스크립트 |
| `logs/experiments/reversal_oos_chunks_merged.jsonl` | 병합된 최종 결과물 (JSONL) |
| `reports/experiments/reversal_oos_chunk_merge_summary.json` | 병합 결과 요약 (JSON) |
| `reports/experiments/reversal_oos_chunk_merge_summary.txt` | 병합 결과 요약 (TXT) |

## 3. 병합 처리 로직

1. **Chunk 탐색**: `reversal_oos_chunk_manifest.jsonl`에서 `status == "success"`인 파일을 추출. (manifest가 없을 시 패턴 매칭으로 직접 탐색)
2. **데이터 로드 및 파싱 검증**: 각 chunk 파일을 한 줄씩 읽으며 `json.loads` 수행. 파싱에 실패하는 깨진 줄은 버리고 카운트(`parse_errors`) 증가.
3. **중복 제거 (Deduplication)**:
    - 이벤트의 키 조합 `(market, type, timestamp, price, volume)` 또는 `(market, type, timestamp, total_ask_size, total_bid_size)`을 해싱하여 중복 여부를 판단.
    - 조합이 불가능한 구조의 데이터일 경우 전체 데이터의 정렬된 JSON 문자열 해시를 사용하여 중복을 제거.
4. **시간순 정렬 (Sorting)**: 메모리에 적재된 이벤트를 `timestamp` 혹은 `trade_timestamp` 기준으로 오름차순 정렬.
5. **결과 출력**: 병합/정렬 완료된 데이터를 단일 `.jsonl` 파일로 기록하고, 상세 요약(summary) 파일을 생성.

## 4. 실행 인자 (tools/merge_ws_chunks.py)

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--input-dir` | `logs/experiments/chunks` | chunk 파일들이 위치한 디렉토리 |
| `--manifest` | `logs/experiments/chunks/reversal_oos_chunk_manifest.jsonl` | manifest 파일 경로 |
| `--output` | `logs/experiments/reversal_oos_chunks_merged.jsonl` | 병합된 최종 출력 파일 경로 |
| `--summary-json` | `reports/experiments/reversal_oos_chunk_merge_summary.json` | 요약 JSON 파일 경로 |
| `--summary-txt` | `reports/experiments/reversal_oos_chunk_merge_summary.txt` | 요약 TXT 파일 경로 |

## 5. 안전 원칙

- **실거래 관련 기능 전면 배제**: 병합 도구는 오로지 로컬 로그 데이터만 조작한다.
- **원본 데이터 보존**: 원본 chunk 파일들은 수정/삭제되지 않는다.
- **예외 처리 내재화**: 디코딩 에러, JSON 구조 오류, 파일 누락 등을 안전하게 건너뛰도록 처리하여 프로그램 크래시를 방지한다.
