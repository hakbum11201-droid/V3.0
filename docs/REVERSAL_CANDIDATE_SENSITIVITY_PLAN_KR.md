# Reversal Edge v2 Candidate 민감도 분석 계획

## 1. 목적

Master Dataset 4,160,035 rows (약 106.75시간 분량)에서도 Reversal Edge v2 candidate의 backtest trades가 0건으로 나오는 현상의 원인을 규명한다.

기존 candidate를 수정하지 않고 실험용 candidate를 별도 생성하여 어떤 조건을 완화해야 진입이 발생하는지 체계적으로 확인한다.

## 2. 핵심 원칙

1. **원본 candidate 수정 금지**: `configs/experiments/reversal_edge_candidate_v2_from_36h.json` 절대 수정 불가
2. **실험 candidate 격리**: 모든 실험용 candidate는 `reports/experiments/candidate_sensitivity/tmp_candidates/`에만 생성
3. **config 자동 반영 금지**: 실험 결과를 config에 자동으로 반영하지 않는다
4. **live.enabled=false 유지**: 어떠한 결과도 실거래 자동 승격 불가

## 3. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/run_reversal_candidate_sensitivity.py` | 민감도 분석 실행 스크립트 |
| `RUN_REVERSAL_CANDIDATE_SENSITIVITY.bat` | Windows 배치 실행 파일 |
| `docs/REVERSAL_CANDIDATE_SENSITIVITY_PLAN_KR.md` | 설계 문서 (현재 파일) |
| `reports/experiments/candidate_sensitivity/tmp_candidates/` | 실험용 임시 candidate 저장 폴더 |
| `reports/experiments/reversal_candidate_sensitivity_latest.json` | 분석 결과 JSON 보고서 |
| `reports/experiments/reversal_candidate_sensitivity_latest.txt` | 분석 결과 텍스트 보고서 |

## 4. 실험 후보 목록 (1차)

| 이름 | Threshold 변화 | Cost Floor 변화 |
|---|---|---|
| A_original | 원본 유지 [60, 70, 80] | 원본 유지 0.20% |
| B_threshold_50_60_70 | 완화 [50, 60, 70] | 원본 유지 |
| C_threshold_40_50_60 | 대폭 완화 [40, 50, 60] | 원본 유지 |
| D_cost_015 | 원본 유지 | 완화 0.15% |
| E_cost_010 | 원본 유지 | 대폭 완화 0.10% |
| F_threshold_50_cost_015 | 완화 [50, 60, 70] | 완화 0.15% |
| G_threshold_40_cost_010 | 대폭 완화 [40, 50, 60] | 대폭 완화 0.10% |

## 5. 판정 기준

| 판정 라벨 | 조건 |
|---|---|
| `NO_ENTRY` | trades == 0 |
| `TOO_FEW_TRADES` | 0 < trades < 5 |
| `PROMISING` | trades >= 5 이고 avg_net_pnl_pct > 0 |
| `ENTRY_BUT_NEGATIVE` | trades >= 5 이고 avg_net_pnl_pct <= 0 |

## 6. 데이터 입력 우선순위

1. `logs/experiments/temp_cost_randomization.jsonl` (이미 추출된 최신 파일이면 재사용)
2. SQLite Cache → `logs/experiments/temp_candidate_sensitivity_master.jsonl` 임시 추출
3. `logs/experiments/master/reversal_edge_master_dataset.jsonl` JSONL 직접 읽기 (Fallback)

## 7. Trades 0건 지속 시 원인 후보

1. **Threshold만의 문제가 아닌 경우**
   - `reversal_conditions`의 개별 필터(`max_price_chg_10s`, `min_sell_buy_ratio_10s` 등)가 병목
   - 2차에서 개별 조건 완화 실험 필요

2. **Cost Floor만의 문제가 아닌 경우**
   - `cost_floor_pct`는 trade 발생 후 PnL 판단에 사용됨
   - trade 자체가 0건이면 cost_floor 완화는 의미 없음

3. **Scoring Weights 또는 Market Scope 병목**
   - `market_sync_score` 계산 시 다수 마켓 데이터 필요
   - SOL_ONLY 모드에서 타 마켓 동기화 점수가 낮게 산출될 수 있음
   - 2차에서 weights 조정 실험 예정

4. **RANGE/횡보 장세 조건 미발생**
   - 수집 기간에 강한 일방향 추세장이 지속됐다면 Reversal 신호 전제 조건 미성립
   - 가격 변화율 히스토그램 진단 필요

## 8. 2차 실험 예정 항목 (1차 결과에 따라 결정)

- `reversal_conditions` 개별 조건 단계적 완화
- `weights`의 `market_sync_score` 비중 감소 실험
- KRW-SOL 외 마켓 추가 (`STATIC_MULTI_MARKET` 모드)
- 급락 구간 집중 데이터 추가 수집

## 9. 안전 수칙

- 실험 결과는 절대 실거래 자동 승인이 아님
- 기존 candidate 자동 교체 금지
- config 자동 반영 금지
- live.enabled=false 유지
- 사람 승인 전 tiny_live 금지
