# coinB V3.0 현재 연구 상태

## 0. 현재 우선순위
1. **Reversal Edge v2 Paper 결과 분석**
   - 24시간 단위 실시간 데이터 대응력 확인.
   - 실제 체결 엔진과의 정합성 및 레이턴시 영향성 평가.
2. **HTF Regime Filter 설계 및 연동**
   - 급락장에서의 Reversal 진입 차단 로직 적용.
   - HTF Regime Diagnostics 도구 연동 완료.
3. **Auto Research Loop 고도화**
   - OOS Chunk Pipeline부터 Auto Research Report까지의 자동화 도구 통합.

---

## 1. 프로젝트 원칙
- **기본 모드**: `paper` 유지.
- **안전 설정**: 
  - `live.enabled=false` 고정.
  - 실거래 자동 전환 및 config 자동 반영 절대 금지.
- **검증 단계**: 실거래 전 반드시 `tiny_live` 단계를 거쳐야 함. (현재는 실거래 단계 아님)
- **연구 핵심**: 
  - Upbit KRW 마켓의 주문흐름(Orderflow) 분석.
  - 호가(Orderbook) 미시구조 특징 추출.
  - 체결 데이터 기반의 Net Edge 전략 연구.

## 2. 실패한 방향 (Lesson Learned)
기존 추세 추격형(Continuation) 진입 구조는 현재 수수료 체계와 시장 환경에서 유효한 엣지를 찾지 못해 폐기 또는 후순위로 미뤄졌습니다.

- **Continuation / 상승 추격형**
- **Soft Score v1**
- **Combined Filter v1/v2**
- **TP/SL Exit Simulator**

## 3. 발견한 유망 방향: Reversal Edge v2
강한 매도 압력 이후 반등하는 Absorption Rebound / Exhaustion Reversal 패턴이 유망한 것으로 진단되었습니다. 현재 **가장 유망한 전략**으로 집중 연구 중입니다.

## 4. 진행 중인 도구 및 파이프라인 구축 (복사본 완료 사항)
현재 복사본(V3.0_WORK_UI)에서 연구 자동화를 위한 다음 도구들이 완성되었습니다.
- **Control Center UI**: 전체 상태 통합 관제
- **OOS Chunk Runner / Merge**: 백테스트 검증을 위한 데이터 수집
- **OOS Chunk Backtest Pipeline**: 자동 백테스트 연동
- **Auto Research Report Generator**: 리포트 통합 요약
- **HTF Regime Diagnostics**: 시장 상황에 따른 Reversal 진입 차단

*최근 HTF Regime 테스트 결과*:
- **Regime**: BEAR
- **Permission**: RESTRICTED

## 5. 현재 원본 실행 중인 작업
- **작업명**: Reversal Edge v2 Paper Runner (24시간)
- **실행 파일**: 원본 V3.0에서 구동 중
- 진행 목적: 안정성 및 실시간 엣지 유지 여부 판단

## 6. 절대 금지 사항 (Safety Guard)
- `live.enabled=true` 자동 변경 절대 금지.
- 후보 설정(Candidate)의 실거래 config 자동 반영 금지.
- Upbit 주문 API 호출 및 API Key의 실제 사용 금지.
- 현재 어떠한 로직도 사람의 승인 없이 자동 매매 모드로 진입할 수 없습니다.

## 7. 결론 및 판단
- Reversal Edge v2는 현재 가장 유망한 전략 후보입니다.
- 하지만 여전히 검증 초기 단계이며, 실거래 투입 수준은 아닙니다. 실거래 단계 아님을 명확히 합니다.
