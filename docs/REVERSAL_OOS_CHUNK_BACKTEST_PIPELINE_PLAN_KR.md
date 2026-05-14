# Reversal Edge v2 OOS Chunk Backtest Pipeline 설계안

## 1. 배경 및 목적

앞서 설계한 30분 단위 OOS Chunk 수집기(`run_reversal_oos_chunk_runner.py`)와 병합 도구(`merge_ws_chunks.py`)를 기반으로, 데이터 준비 단계부터 성과 분석(Backtest) 단계까지 한 번에 실행하는 자동화 파이프라인이 필요하다. 

이 파이프라인은 수집된 다수의 chunk들을 단일 `.jsonl`로 병합하고, 이를 지정된 전략 파라미터(`candidate`)로 백테스트하여 최종적으로 실전 투입(Paper 단계 승급) 여부에 대한 가이드라인을 제시한다.

## 2. 파일 구성

| 파일 | 역할 |
|------|------|
| `tools/run_reversal_oos_chunk_backtest_pipeline.py` | 파이프라인 실행용 파이썬 스크립트 |
| `RUN_REVERSAL_OOS_CHUNK_BACKTEST_PIPELINE.bat` | Windows 환경에서 파이프라인을 구동하는 배치 스크립트 |
| `reports/experiments/reversal_oos_chunk_pipeline_summary.json` | 파이프라인 통합 실행 결과 및 최종 판단 (JSON) |
| `reports/experiments/reversal_oos_chunk_pipeline_summary.txt` | 파이프라인 통합 실행 결과 및 최종 판단 (TXT) |

## 3. 파이프라인 동작 흐름

1. **사전 검증**: 지정된 `candidate` 파일의 존재 여부 및 필수 입력 경로 검증
2. **STEP 1: Merge (병합)**
   - `tools/merge_ws_chunks.py`를 서브프로세스로 실행하여 chunk 병합
   - 실패 시 파이프라인 즉시 중단 (Backtest 실행 안 함)
3. **STEP 2: Backtest (백테스트)**
   - `coinb.main reversal-edge-backtest` 모듈을 실행
   - 병합된 데이터(`--ws`)와 전략 파일(`--candidate`) 제공
4. **STEP 3: 평가 (Evaluation)**
   - 백테스트 결과 요약(`backtest_summary.json`) 파일 분석
   - `trades` 개수 및 `net_pnl_pct` 등의 지표를 기반으로 최종 판단 등급 부여
5. **결과 출력**: 파이프라인 요약(Summary) 파일 생성

## 4. 최종 판단 (Final Judgement) 기준

- `FAILED`: 백테스트 요약 파일을 찾지 못했거나 병합 실패 등 치명적인 에러 발생 시
- `NEED_MORE_DATA`: `trades` 수가 0개이거나 분석 가능한 조건이 형성되지 않았을 때
- `PROMISING_BUT_PAPER_REQUIRED`: `Net PnL`이 양수(+)인 경우. 실거래 가능성이 보이나 최소 72시간 이상의 Paper 검증이 필요함
- `HOLD_AND_ANALYZE_FAILURES`: `Net PnL`이 음수(-)인 경우. 전략/파라미터 보완 및 손실 원인 분석 요망

## 5. 실행 인자 (tools/run_reversal_oos_chunk_backtest_pipeline.py)

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--input-dir` | `logs/experiments/chunks` | Chunk 데이터 폴더 |
| `--manifest` | `logs/experiments/chunks/reversal_oos_chunk_manifest.jsonl` | Chunk 매니페스트 파일 |
| `--candidate` | `configs/experiments/reversal_edge_candidate_v2_from_36h.json` | 적용할 후보 Config |
| `--merged-output` | `logs/experiments/reversal_oos_chunks_merged.jsonl` | 병합 결과 데이터 |
| `--merge-summary-*` | `reports/experiments/reversal_oos_chunk_merge_summary.*` | 병합 요약 출력 경로 |
| `--backtest-summary-*` | `reports/experiments/reversal_oos_chunk_backtest_summary.*` | 백테스트 결과 출력 경로 |
| `--pipeline-summary-*` | `reports/experiments/reversal_oos_chunk_pipeline_summary.*` | 파이프라인 최종 결과 출력 경로 |

## 6. 안전 원칙

- **실거래 반영 금지**: OOS 결과가 우수(`PROMISING`)하더라도 시스템 자동 승격(live.enabled 자동화)은 절대 불가하다.
- **원본 데이터 보존**: 기존에 수집된 chunk, logs, reports 데이터는 덮어쓰거나 지우지 않는 방향으로 실행된다.
- **예외 발생 시 Fail-Fast**: 하위 프로세스 에러 발생 시 진행을 안전하게 중단하고 로그를 기록한다.
