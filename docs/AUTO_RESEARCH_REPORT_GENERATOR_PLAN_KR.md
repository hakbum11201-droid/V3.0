# Auto Research Report Generator 설계안

## 1. 배경 및 목적

Reversal Edge v2 전략의 백테스트, OOS Chunk 검증, Paper Runner 검증 등의 결과들이 개별 파일(`.json`, `.txt`)로 흩어져 있어, 작업자(또는 AI)가 다음 단계를 판단하기 위해 여러 파일을 직접 열어보고 비교 분석해야 하는 번거로움이 있었다.

이러한 수동 검증 단계를 줄이고자, **가용 가능한 모든 검증 결과(Summary) 파일을 단일 프로세스로 읽어 들여, 사람이 이해하기 쉬운 최종 종합 리포트를 자동 생성**하는 도구를 설계한다.

## 2. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/generate_auto_research_report.py` | 주요 파이썬 스크립트. 각 Summary를 스캔하고 종합 판단을 수행 |
| `RUN_AUTO_RESEARCH_REPORT.bat` | Windows용 배치 파일 (원클릭 자동 생성 목적) |
| `reports/experiments/auto_research_report_latest.json` | 기계가 읽기 쉬운 구조화된 출력 결과물 |
| `reports/experiments/auto_research_report_latest.txt` | 사람이 읽기 쉬운 한국어 텍스트 포맷 결과물 |

## 3. 읽어들이는 데이터 목록

스크립트는 다음 순서와 패턴으로 요약(summary) 파일을 탐색하며, 없을 시 건너뛴다.

1. **Paper Summary**: 24H 페이퍼 런 최신 결과 (e.g. `reports/paper/reversal_edge_v2_paper_24h_summary.json` 및 `reports/experiments/reversal_edge_v2_paper_run_summary_*.json`)
2. **OOS Chunk Runner**: Chunk 수집 로그 요약 (e.g. `...oos_chunk_runner_summary.json` 또는 `...test_summary.json`)
3. **OOS Chunk Merge**: 중복 제거 및 시간 정렬 요약 (e.g. `...oos_chunk_merge_summary.json`)
4. **OOS Pipeline**: 백테스트 결과를 포함한 파이프라인 최종 요약 (e.g. `...oos_chunk_pipeline_summary.json`)
5. **Walk-forward Validation**: 시간별 롤링 검증 결과 (e.g. `reports/experiments/walk_forward_validation_latest.json`)
6. **Cost Randomization Test**: 거래 비용 랜덤화 시나리오 테스트 결과 (e.g. `reports/experiments/cost_randomization_test_latest.json`)
7. **Master Dataset Builder**: 데이터 파이프라인 중복제거/수집 결과 (e.g. `reports/experiments/master_dataset_builder_latest.json`)
8. **Independent Holdout Validation**: OOS와 독립적인 최종 홀드아웃 결과 (e.g. `reports/experiments/independent_holdout_validation_latest.json`)
9. **HTF Regime Gate Analysis**: 다중 타임프레임 시장 상황 종합 게이트 결과 (e.g. `reports/experiments/htf_regime_gate_analysis_latest.json`)
10. **Reversal Entry Funnel Diagnostics**: 진입 0회 등 조건 병목 진단 결과 (e.g. `reports/experiments/reversal_entry_funnel_diagnostics_latest.json`)
11. **Candidate Schema Inspection**: 스키마 파라미터 심층 탐색 결과 (e.g. `reports/experiments/candidate_schema_inspection_latest.json`)

## 4. Promotion Guard 동작 조건 (다음 행동)

읽어들인 데이터 기반으로 현재 전략의 안전성과 승격(Promotion) 가능 여부를 판단한다.

| 판단 키워드 | 발생 조건 | 의미/조치 |
|---|---|---|
| `WAIT_FOR_PAPER_RESULT` | Paper 데이터가 전혀 없는 경우 | 아직 24H 검증이 진행 중이므로 결과가 나올 때까지 대기 |
| `NEED_MORE_PAPER_OR_CONDITION_REVIEW` | Paper 거래 수(trades) == 0 | 시장 변동성이 낮았거나 조건이 너무 타이트하므로, 추가 구동 혹은 파라미터 점검 |
| `NEED_MORE_DATA` | Paper 거래 수(trades) < 5 | 표본이 너무 적음. 데이터 누적을 위해 24H~72H 추가 Paper 구동 필요 |
| `HOLD_AND_ANALYZE_FAILURES` | Paper Net PnL < 0 (음수) | 손실 전략. 오류 원인과 시장 상황(Regime) 분석 요망 |
| `RISK_REVIEW_REQUIRED` | trades 대비 SL 발생 비율이 60%를 초과할 때 | 높은 리스크 상태. 진입 타점이나 손절 라인 재설정 필수 |
| `RUN_MORE_OOS_CHUNKS` | OOS 파이프라인 판단이 `NEED_MORE_DATA`일 때 | 추가적인 OOS 데이터 세트 수집 권장 |
| `PROMISING_RUN_3D_PAPER` | trades >= 10 이면서 Net PnL > 0 | 전략 유망. 단, **실거래 즉시 투입 불가**, 3일 이상(72H) 추가 Paper 검증 요망 |
| `CONTINUE_MONITORING` | 그 외 정상적인 동작 중인 경우 | 현재 모니터링 체제 유지 |

## 5. 설계 안전 원칙

1. **모든 데이터는 Read-Only**: `config`, `logs`, `reports` 파일들은 절대 수정/삭제하지 않고 오직 파싱만 수행한다.
2. **실거래 무조건 금지**: 분석 결과가 압도적으로 긍정적이더라도 `live.enabled=true` 변경을 스크립트나 AI가 자동으로 수행하지 못한다.
3. **안전 경고 문구 하드코딩**: 생성된 TXT 파일 하단에 항상 사람 승인 전 실거래 전환 및 자동 적용을 금지하는 경고문을 포함한다.
4. **예외 처리 강화**: 특정 JSON의 key가 없거나, 파일 디코딩에서 에러가 발생해도 전체 리포트 생성 프로세스가 죽지 않도록 방어 로직(`try-except`, `load_txt_tail` 등)을 철저히 둔다.
