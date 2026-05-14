# Master Dataset + Independent Holdout Validation + HTF Regime Gate Analysis 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략이 현재 수집된 약 80시간(36h + OOS 20h + Paper 24h 등)의 데이터에 대해 수익성을 입증하더라도, 이 데이터 전체를 묶어 조건을 조정한 경우(Overfitting), 새로운 데이터에서는 성과가 무너질 수 있습니다.

따라서 본 도구군은 다음 세 가지 목적을 달성하기 위해 설계되었습니다.
1. **Master Dataset Builder**: 흩어진 실험/Paper 데이터를 모아 하나의 통합된 데이터셋과 완전히 독립된 Holdout 데이터셋으로 분리합니다.
2. **Independent Holdout Validation**: 조건(Candidate)을 변경하지 않고, 오직 미래의 독립된 데이터(Holdout)에서만 백테스트를 재수행하여 과최적화를 검증합니다.
3. **HTF Regime Gate Analysis**: 다양한 검증 도구(Cost, Degradation, Holdout)의 결과와 상위 타임프레임(HTF) 시장 상황을 종합하여, 현재 전략의 실거래 진입 허용/차단 여부(Gate)를 분석용으로 진단합니다.

## 2. 파일 구성 및 진단 로직

| 도구 스크립트 | 역할 |
|---|---|
| `tools/build_master_validation_dataset.py` | 기존 Raw 데이터를 파싱. `timestamp` 단일 키의 한계를 극복하기 위해 `source_file`, `line_index`, `event_type`, `market`, `price`, `volume` 및 `line_hash`를 결합한 초정밀 중복 제거(Deduplication)를 수행하며, `orderbook_sample` 등의 변형 이벤트를 정규화합니다. |
| `tools/run_independent_holdout_validation.py` | Master와 Holdout 각각 백테스트를 돌려 PnL 및 승률 갭을 산출하고 검증 결과를 진단 |
| `tools/run_htf_regime_gate_analysis.py` | 각 검증 도구들의 Json 리포트를 종합하여 종합적인 Gate(ALLOW, RESTRICTED, BLOCK 등) 상태 판별 |

각각에 대응하는 `.bat` 실행 파일과 결과물이 저장될 `reports/experiments/` 리포트 파일들이 존재합니다.

## 3. 핵심 규칙 및 제약사항

1. **절대적 분리**: 사용자는 향후 수집할 72시간 등 별도의 데이터 파일명에 `holdout` 또는 `72h`를 포함시켜야 하며, 이는 Master 데이터셋과 섞이지 않아야 합니다.
2. **수정 불가 원칙**: Holdout 검증(`FAILS_HOLDOUT`) 결과가 나쁘게 나오더라도, 이를 개선하기 위해 전략 조건(Candidate)이나 파라미터를 다시 수정해서는 안 됩니다. (Holdout이 오염됨)
3. **Gate는 분석 전용**: HTF Regime Gate Analysis에서 산출된 `BLOCK`이나 `ALLOW` 판단은 오직 사람의 의사결정을 돕기 위한 분석용 지표이며, 시스템이 자동으로 `Paper Runner`를 강제 종료하거나 `live.enabled`를 조작하지 않습니다.

## 4. HTF Regime Gate 판별 로직

게이트 진단은 기본적으로 HTF Regime 상태(BULL, RANGE, BEAR, CRASH)에 기반하여 1차 판단을 내린 뒤, 여러 Risk 요인을 곱하여 최종 등급을 하향(Downgrade)하는 방식으로 동작합니다.

### 1차 판단 (Base Gate)
- `BULL` → ALLOW
- `RANGE` → ALLOW_PREFERRED
- `BEAR` → RESTRICTED
- `CRASH` → BLOCK

### 2차 하향 (Downgrade Modifiers)
- **비용 민감도 (Cost Fragility)**: `FAILED` 또는 `FRAGILE_EDGE`일 경우 Base Gate에서 최소 1~2단계 하향.
- **성과 악화 (Degradation)**: `DEGRADED` 또는 `RISK_DEGRADED`일 경우 `RESTRICTED` 또는 `BLOCK`으로 강제 하향.
- **독립 검증 실패 (Holdout Failure)**: `FAILS_HOLDOUT`일 경우 즉각 `BLOCK` 처리.

## 5. 설계 안전 원칙

1. 본 파이프라인의 모든 작업은 기존 코드(`src/`) 및 설정을 전혀 건드리지 않고 Subprocess로 백테스트 엔진만 호출합니다.
2. 실거래 진입을 막기 위한 목적이더라도, 코드가 스스로 `live.enabled=false`를 풀거나 잠그지 않으며 오직 읽기 전용으로 시뮬레이션합니다.
3. 생성된 데이터셋은 `logs/experiments/master/` 디렉토리에만 국한되며 원본 Raw 데이터들을 훼손하지 않습니다.
