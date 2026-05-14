# 거래 비용 랜덤화 테스트 (Cost Randomization Test) 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략의 백테스트나 Paper 단계의 평균 순수익(Net PnL)이 매우 작은 규모(예: `+0.01%` ~ `+0.02%`)이기 때문에, 실거래(live) 시 슬리피지(Slippage)나 호가 변동, 수수료 등의 거래 비용이 미세하게 증가하기만 해도 전략이 완전히 붕괴(Fragile)될 위험이 있다.

따라서 거래 비용을 시나리오별로 가중(Randomization/Scenario) 적용해보고, 수수료 및 슬리피지가 `0.22%` ~ `0.35%` 수준으로 높아져도 여전히 전략의 PnL이 양수를 유지하는지, 즉 **전략의 엣지가 비용(Cost)을 이겨낼 만큼 견고한지(Robust) 사전에 확인하는 방어 도구**를 구축한다.

## 2. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/run_cost_randomization_test.py` | 누적된 이력 데이터(jsonl)로 백테스트를 돌려 Baseline을 산출한 뒤, 비용 시나리오별로 순수익을 차감하여 판별하는 파이썬 스크립트 |
| `RUN_COST_RANDOMIZATION_TEST.bat` | Windows 환경에서 해당 도구를 즉시 실행하기 위한 배치 스크립트 |
| `docs/COST_RANDOMIZATION_TEST_PLAN_KR.md` | 도구 구조 및 평가 기준 가이드라인 (현재 파일) |
| `reports/experiments/cost_randomization_test_latest.json/txt` | 비용 시나리오별 결과 및 최종 진단이 담긴 보고서 |

## 3. 평가 방식

1. **입력 데이터 (Base Test)**:
   - 1순위: `logs/experiments/master/reversal_edge_master_dataset.jsonl`
   - 2순위: `logs/paper/reversal_edge_v2_paper_24h_events.jsonl`
   - 3순위: `logs/experiments/reversal_oos_chunks_merged.jsonl`
   - 4순위: `logs/experiments/reversal_oos_chunks_test_merged.jsonl`
   
   위 파일 중 가장 높은 우선순위의 데이터가 존재하는 것을 찾아 기본 후보(`reversal_edge_candidate_v2_from_36h.json`)와 함께 기존 `reversal-edge-backtest`를 수행한다. 이 결과를 통해 Baseline `trades` 및 `avg_net_pnl_pct`를 확보한다.

2. **비용 시나리오 (Scenarios)**:
   - 현재 시뮬레이션 기본 비용: `0.20%` (Base)
   - 시나리오 1: `0.22%` (Slight Slippage)
   - 시나리오 2: `0.25%` (Moderate Slippage)
   - 시나리오 3: `0.30%` (High Slippage)
   - 시나리오 4: `0.35%` (Extreme Slippage)

3. **시나리오별 PnL 조정**:
   - `백테스트 엔진` 자체에 동적 Cost 오버라이드 기능이 없는 한계를 우회하기 위해, Baseline `avg_net_pnl_pct`에서 **추가 비용분을 보수적으로 1:1 차감**하여 `adjusted_avg_net_pnl_pct`를 계산한다.
   - 수식: `Adjusted PnL = Original PnL - (Scenario Cost - Base Cost)`

## 4. 시나리오 판별 및 최종 진단 기준

### 시나리오별 판단 라벨
| 라벨 | 조건 |
|---|---|
| `ROBUST` | 조정된 PnL이 양수(`> 0`)이며, 해당 시나리오의 비용이 `0.25%` 이상일 때 |
| `SURVIVES_COST` | 조정된 PnL이 양수(`> 0`)이며, 해당 시나리오의 비용이 `0.25%` 미만일 때 |
| `FAILS_COST` | 조정된 PnL이 `0` 이하일 때 |

### 최종 진단 결과 (Final Judgement)
모든 시나리오를 종합하여 다음 중 하나로 평가한다.

| 진단 라벨 | 조건 | 조치 권고 |
|---|---|---|
| `ROBUST_TO_COST` | `ROBUST` 시나리오가 1개 이상 존재함 (비용 `0.25%` 이상에서도 수익) | 엣지가 매우 견고함. 다음 단계(3D Paper 등) 진행. |
| `SURVIVES_BASE_ONLY` | 수익인 시나리오가 2개 이상 존재함 (Base 외 1개 이상 살아남음) | 비용에 민감함. 체결 로직/슬리피지 개선 연구 요망. |
| `FRAGILE_EDGE` | 오직 Base(`0.20%`) 시나리오에서만 수익임 | 엣지가 너무 취약함. 파라미터 재조정 필수. |
| `FAILED` | Base 시나리오조차 손실임 | 전략 엣지 소멸. Candidate 완전 폐기. |
| `NEED_MORE_DATA` | 입력 데이터 부족 또는 Trades 0회 | 데이터 추가 수집 후 재평가. |

## 5. 설계 안전 원칙

1. **완전 보수적 삭감**: 시뮬레이션 엔진을 뜯어고치지 않고 결과 PnL에서 추가 비용을 직관적이고 보수적으로 차감하는 수학적 모델을 사용한다.
2. **Read-Only**: 데이터와 `config` 파일은 오직 읽기 전용으로만 다루며, 본 도구로 인해 어떠한 코드 수정이나 `logs` 파괴가 일어나지 않는다.
3. **실거래 보호**: 결과가 `ROBUST_TO_COST` 라 할지라도 도구 스스로 `live.enabled`를 조작하지 않으며, 사람의 최종 판단 후 수동 승격 원칙을 고수한다.
