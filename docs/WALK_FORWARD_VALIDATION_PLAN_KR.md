# Walk-forward Validation 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략 후보(`configs/experiments/reversal_edge_candidate_v2_from_36h.json`)가 과거 특정 OOS(Out-of-Sample) 20시간 구간이나 특정 시장 상황(Regime)에만 과최적화(Overfitting)되어 수익이 나는 것인지, 아니면 시간이 지남에 따라 안정적으로 수익을 내는 패턴인지 검증해야 한다.

이를 위해 전체 시계열 데이터를 훈련/검증(Train/Test) 구조로 분할하고, 윈도우를 시간 순서대로 롤링하며 반복 백테스트를 수행하는 **Walk-forward Validation(WFV)** 도구를 구축한다. (본 시스템에서는 전략 최적화가 자동화되어 있지 않으므로, 고정된 후보를 다양한 시계열 Test 구간에서 평가하는 "Rolling OOS Test" 방식으로 구동한다.)

## 2. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/run_walk_forward_validation.py` | 누적된 이력 데이터(jsonl)를 불러와 Fold 단위로 쪼개고 `reversal-edge-backtest`를 반복 실행하는 스크립트 |
| `RUN_WALK_FORWARD_VALIDATION.bat` | Windows 전용 일괄 실행 배치 파일 |
| `docs/WALK_FORWARD_VALIDATION_PLAN_KR.md` | 도구 구조 및 평가 기준 가이드라인 (현재 파일) |
| `logs/experiments/walk_forward/` | 각 Fold별 추출된 테스트 데이터(`fold_XXXX_test.jsonl`) 저장 폴더 |
| `reports/experiments/walk_forward_validation_latest.json/txt` | 전체 Fold 백테스트 결과를 집계한 기계/사람용 보고서 |

## 3. 평가 방식

1. **입력 데이터 결합 및 정렬 (우선순위 순)**:
   - `logs/experiments/master/reversal_edge_master_dataset.jsonl` (1순위)
   - `logs/paper/reversal_edge_v2_paper_24h_events.jsonl` (2순위)
   - `logs/experiments/reversal_oos_chunks_merged.jsonl` (3순위)
   - `logs/experiments/reversal_oos_chunks_test_merged.jsonl` (4순위)
   - `logs/paper/reversal_edge_v2_paper_events.jsonl` (5순위)
   
   위 파일들 중 존재하는 가장 높은 우선순위의 파일 하나를 읽어들여 시계열(Timeline)을 구성하고 시간(ts)순으로 정렬한다.

2. **Fold (검증 구간) 분할**:
   - `Train Window = 36시간`, `Test Window = 24시간`, `Step = 24시간`
   - 처음 시작(min_ts)부터 36시간을 건너뛴 후, 24시간 동안을 1번 Fold의 Test Set으로 구성. 24시간씩 이동하며 데이터를 끝(max_ts)까지 계속 분할한다.
   - 부족한 경우 생성되지 않거나 `NEED_MORE_DATA`로 판별.

3. **반복 백테스트**:
   - 각각의 Test jsonl에 대해 기존 `coinb.main reversal-edge-backtest` 커맨드를 호출하여 개별 PnL 및 승률을 측정한다.

## 4. 최종 판별 기준 (Final Judgement)

전체 Fold 결과를 종합하여 하나의 판정 라벨을 부여한다.

| 판정 라벨 | 조건 (기준) | 행동 지침 |
|---|---|---|
| **NEED_MORE_DATA** | 전체 Fold가 0개이거나, 이벤트/거래 수 부족으로 절반 이상의 Fold가 실패한 경우 | OOS/Paper 구동을 통해 시계열 데이터 추가 수집 |
| **FAILED** | 전체 평균 Net PnL이 0보다 작은 경우 | 전략 엣지 소멸 의심. Candidate 전면 재조정 필요 |
| **UNSTABLE** | 평균 PnL은 양수이나 PASS/FAIL 비율 차이가 2 이하(절반은 수익, 절반은 손실)로 편차가 너무 큰 경우 | 특정 구간 과최적화 의심. 파라미터 미세 조정 및 원인 분석 |
| **PROMISING_BUT_MORE_DATA_REQUIRED** | 평균 Net PnL 양수 및 절반 이상의 Fold가 수익(PASS)을 달성한 경우 | 일관성 증명. 24~72H Paper 추가 구동 권장 |

## 5. 설계 안전 원칙

1. **완전 격리 실행**: 본 도구는 기존 코드(`src/`) 및 설정을 전혀 수정하지 않고 Subprocess로 백테스트 엔진만 호출한다.
2. **Read-Only**: 누적된 로그 파일의 데이터를 읽기만 하며 원본은 삭제/수정하지 않는다.
3. **실거래 보호**: 결과가 압도적으로 좋더라도 도구가 사람을 대신해 `live.enabled`를 조작할 수 없다. 모든 승격(Promotion)은 사람의 책임하에 수동으로 진행된다.
