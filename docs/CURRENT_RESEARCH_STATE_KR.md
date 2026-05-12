# coinB V3.0 현재 연구 상태

## 0. 현재 우선순위
1. **Reversal Edge v2 Paper 결과 분석**
   - 6시간/24시간 단위 실시간 데이터 대응력 확인.
   - 실제 체결 엔진과의 정합성 및 레이턴시 영향성 평가.
2. **HTF Regime Filter 설계**
   - 급락장에서의 Reversal 진입 차단 로직 구체화.
   - BTC 및 주요 마켓 동반 하락 시그널 통합.
3. **Auto Research Loop 고도화**
   - 데이터 수집 → 진단 → 후보 생성 → 검증 프로세스 자동화.
   - OOS 검증 결과에 따른 자동 후보 필터링 시스템 구축.

---

## 1. 프로젝트 원칙
- **기본 모드**: `paper` 유지.
- **안전 설정**: 
  - `live.enabled=false` 고정.
  - 실거래 자동 전환 및 config 자동 반영 절대 금지.
- **검증 단계**: 실거래 전 반드시 `tiny_live` 단계를 거쳐야 함.
- **연구 핵심**: 
  - Upbit KRW 마켓의 주문흐름(Orderflow) 분석.
  - 호가(Orderbook) 미시구조 특징 추출.
  - 체결 데이터 기반의 Net Edge 전략 연구.

## 2. 실패한 방향 (Lesson Learned)
기존 추세 추격형(Continuation) 진입 구조는 현재 수수료 체계와 시장 환경에서 유효한 엣지를 찾지 못해 폐기 또는 후순위로 미뤄졌습니다.

- **Continuation / 상승 추격형**
  - 수수료와 슬리피지를 극복하지 못함.
  - Net PnL 음수 기록 지속.
- **Soft Score v1**
  - 후보 수는 확보했으나 질적 개선 실패.
  - Net PnL 양수 전환 실패.
- **Combined Filter v1/v2**
  - 필터링 로직은 개선되었으나 최종 Net PnL 양수 조합 발견 실패.
- **TP/SL Exit Simulator**
  - 기존 Trend 구조 하에서는 청산 정책 변경만으로 수익성 확보 불가.

## 3. 발견한 유망 방향: Reversal Edge
강한 매도 압력 이후 반등하는 Absorption Rebound / Exhaustion Reversal 패턴이 유망한 것으로 진단되었습니다.

### Reversal 진단 결과 (36h Diagnostics)
| 항목 | Winner Rate (MFE >= 0.2%) | 비고 |
| :--- | :--- | :--- |
| **Continuation 조건** | 15.76% | 낮은 승률 |
| **Reversal 조건** | 33.22% | 유망함 |
| **KRW-SOL Reversal** | 47.97% | 특정 마켓 엣지 강함 |

> [!NOTE]
> 600초 보유가 300초보다 유리한 경향을 보였으나, 최종 TP/SL 조합에서는 300초 타임아웃이 더 안정적인 결과 도출.

## 4. Reversal Edge v1/v2 진행 현황
- **v1 후보**
  - 조건이 너무 엄격하여 후보군 0개 발생.
  - Bottle-neck 분석 결과 Volatility 기준이 주원인.
- **v2 후보**
  - Threshold Calibrator를 통해 병목 조건을 보정하여 생성.
  - 경로: `configs/experiments/reversal_edge_candidate_v2_from_36h.json`
  - 주의: 연구/검증용이며 실거래 자동 적용 대상 아님.

## 5. Reversal Edge v2 백테스트 및 OOS 결과
처음으로 Out-of-Sample(OOS) 데이터에서도 Net PnL 양수가 재발생하는 유의미한 결과를 얻었습니다.

### 상세 성과 요약
| 데이터 구분 | 대상 마켓 | Threshold | Timeout | TP/SL | Avg Net PnL | Win Rate | 후보 수 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **기존 36h** | ALL | 60 | 300s | 0.4% / -0.2% | **+0.0180%** | 50.00% | 24개 |
| **OOS 20h** | SOL_ONLY | 60 | 300s | 0.4% / -0.1% | **+0.0235%** | 85.71% | 15개 |

- **결론**
  - 적은 표본이지만 OOS에서 수익 구조가 재발생함.
  - 실시간 Paper 검증 단계로 진입 결정.

## 6. 현재 실행 중인 작업
- **작업명**: Reversal Edge v2 Paper Runner (6시간)
- **실행 파일**: `RUN_REVERSAL_EDGE_V2_PAPER_6H.bat`
- **모니터링 대상**
  - `logs/paper/reversal_edge_v2_paper_events.jsonl` (WS 수집 상태)
  - `logs/paper/reversal_edge_v2_paper_trades.jsonl` (진입/청산 발생 여부)
  - `reports/paper/reversal_edge_v2_paper_summary.txt` (성과 요약)

## 7. 향후 단계 및 설계 방향
1. **Paper 확장**
   - 6시간 결과가 우수할 경우 24시간~72시간 장기 Paper 실행.
2. **시스템 고도화**
   - **HTF Regime Filter**: 상위 타임프레임 지표를 활용한 하락장 진입 차단.
   - **OOS Chunk Runner**: 끊김 없는 데이터 분할 검증 도구.
   - **Auto Research Loop**: 수집부터 검증까지의 파이프라인 자동화.
   - 단, 실거래 전환은 사람 승인 필수.
3. **Control Center UI**
   - 실시간 상태 확인 및 페이퍼 제어를 위한 통합 대시보드 구축.

## 8. 절대 금지 사항 (Safety Guard)
- `live.enabled=true` 자동 변경 절대 금지.
- `orderflow_paper.py`를 포함한 핵심 로직의 성급한 수정 금지.
- 후보 설정(Candidate)의 실거래 config 자동 반영 금지.
- Upbit 주문 API 호출 및 API Key의 실제 사용 금지.

## 9. 결론 및 판단
- Reversal Edge v2는 현재 가장 유망한 전략 후보입니다.
- 하지만 여전히 검증 초기 단계이며, 실거래 투입 수준은 아닙니다.
- 실시간 데이터 환경에서의 견고함을 증명하는 것이 최우선 과제입니다.
