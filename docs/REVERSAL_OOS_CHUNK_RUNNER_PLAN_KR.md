# Reversal Edge v2 OOS Chunk Runner 설계안

## 1. 배경 및 목적

기존 72시간 OOS 수집은 단일 WebSocket 세션으로 장시간 실행되어 중간 끊김 발생 시
전체 데이터를 다시 수집해야 하는 문제가 있었다.

이를 해결하기 위해 **30분 단위 chunk** 수집 방식으로 전환한다.

- 각 chunk는 독립된 파일에 저장되어 중단 후 재시작해도 기존 chunk는 보존된다.
- chunk별 성공/실패를 manifest에 기록하여 재실행 시 이미 성공한 chunk를 건너뛴다.

## 2. 파일 구성

| 파일 | 역할 |
|------|------|
| `tools/run_reversal_oos_chunk_runner.py` | 핵심 수집 로직 |
| `RUN_REVERSAL_EDGE_V2_OOS_CHUNK_24H.bat` | Windows 실행 스크립트 |
| `logs/experiments/chunks/reversal_oos_chunk_NNNN.jsonl` | 각 chunk 수집 데이터 |
| `logs/experiments/chunks/reversal_oos_chunk_manifest.jsonl` | chunk별 성공/실패 기록 |
| `reports/experiments/reversal_oos_chunk_runner_summary.json` | 최종 요약 (JSON) |
| `reports/experiments/reversal_oos_chunk_runner_summary.txt` | 최종 요약 (TXT) |

## 3. 동작 흐름

```
START
  │
  ├─ 총 duration / chunk_sec = N개 chunk 계획
  │
  └─ for chunk_id in 1..N:
       ├─ manifest 확인 → 이미 success면 SKIP
       ├─ collect-ws 실행 (최대 3회 재시도, 실패 시 10초 대기)
       ├─ 성공: chunk_NNNN.jsonl 저장 + manifest 기록
       └─ 실패: manifest에 failed 기록 (파일은 보존)
  │
  └─ 최종 summary.json / summary.txt 작성
```

## 4. 실행 인자

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--duration-sec` | 86400 | 총 수집 시간 (초) |
| `--chunk-sec` | 1800 | chunk당 수집 시간 (초) |
| `--output-dir` | `logs/experiments/chunks` | chunk 저장 디렉토리 |
| `--summary-json` | `reports/experiments/...` | 최종 요약 JSON 경로 |
| `--summary-txt` | `reports/experiments/...` | 최종 요약 TXT 경로 |

## 5. 재시작 안전성

- manifest에서 `status == "success"` 인 chunk는 수집을 건너뛴다.
- 중단 후 재실행해도 이미 성공한 chunk 파일은 덮어쓰지 않는다.
- 실패한 chunk는 재시도 횟수를 manifest에 기록하여 추적한다.

## 6. 다음 단계 (이번 단계에서 미포함)

- chunk 병합: 성공한 chunk들을 하나의 jsonl로 병합
- 백테스트 연동: 병합 데이터를 Reversal Edge v2 백테스터에 입력
- OOS 성과 리포트: 병합 결과 기반 Net PnL / Win Rate 분석

## 7. 안전 원칙

- **실거래 주문 없음**: collect-ws는 데이터 수집 전용이며 주문을 발생시키지 않는다.
- **API Key 없음**: 공개 WebSocket만 사용한다.
- **config 자동 반영 없음**: 수집 결과는 반드시 별도 분석 단계를 거쳐야 한다.
- **live.enabled=false 유지**: 이 도구는 live 설정에 영향을 주지 않는다.

## 8. 짧은 테스트 명령

```powershell
$env:PYTHONPATH="$PWD\src"
python tools/run_reversal_oos_chunk_runner.py `
  --duration-sec 60 `
  --chunk-sec 30 `
  --output-dir logs/experiments/chunks_test `
  --summary-json reports/experiments/reversal_oos_chunk_runner_test_summary.json `
  --summary-txt  reports/experiments/reversal_oos_chunk_runner_test_summary.txt
```
