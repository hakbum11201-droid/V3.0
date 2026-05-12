# coinB V3.0 현재 연구 상태

## 1. 프로젝트 원칙
- 기본 모드는 paper
- live.enabled=false 유지
- 실거래 자동 전환 금지
- 자동 config 반영 금지
- 실거래 전 tiny_live 단계 필요
- 핵심 방향은 Upbit KRW 마켓 기준 주문흐름/호가/체결 데이터 기반 전략 연구

## 2. 실패한 방향
- Continuation / 상승 추격형 구조는 수수료와 슬리피지 극복 실패
- Soft Score v1은 후보 수는 늘렸으나 Net PnL 양수 전환 실패
- Combined Filter v1/v2는 후보 필터링은 개선했지만 Net PnL 양수 조합 없음
- TP/SL Exit Simulator만으로는 기존 Trend 구조를 살리지 못함
- 결론: 기존 추세 추격형 진입 구조는 폐기 또는 후순위

## 3. 발견한 유망 방향
- Reversal Edge / 매도 압력 후 반등 구조가 유망
- reversal-edge-diagnostics 결과:
  - Continuation Winner Rate: 15.76%
  - Reversal Winner Rate: 33.22%
  - KRW-SOL Reversal Winner Rate: 47.97%
  - 600초 보유가 300초보다 유리한 원시 분석 결과 확인

## 4. Reversal Edge v1/v2 진행
- Reversal Edge v1은 조건이 과도하여 후보 0개
- threshold calibrator로 병목 확인
- 주요 병목: volatility >= 0.04 및 조건 결합 과도
- v2 후보 파일 생성:
  - configs/experiments/reversal_edge_candidate_v2_from_36h.json
- v2 후보는 자동 적용 금지, 연구/검증용 후보

## 5. Reversal Edge v2 백테스트 결과
- 기존 36시간 데이터:
  - 최고 조합: ALL_MARKETS / Threshold 60 / Timeout 300s / TP 0.4% / SL -0.2%
  - Avg Net PnL: +0.0180%
  - Win Rate: 50.00%
  - 후보 수: 24개
  - KRW-XRP 100%
- 끊긴 약 20시간 OOS 데이터:
  - 전체 후보: 15개
  - 최고 조합: STATIC_SOL_ONLY / Threshold 60 / Timeout 300s / TP 0.4% / SL -0.1%
  - Avg Net PnL: +0.0235%
  - Win Rate: 85.71%
  - 후보 수: 15개
  - KRW-SOL 14개, KRW-XRP 1개
- 결론:
  - 처음으로 OOS에서도 Net PnL 양수 구조 재발생
  - 단, 표본이 작아 실거래 금지
  - Paper 검증 필요

## 6. 현재 실행 중인 작업
- Reversal Edge v2 Paper Runner 6시간 실행 중
- 실행 파일:
  - RUN_REVERSAL_EDGE_V2_PAPER_6H.bat
- 주요 출력:
  - logs/paper/reversal_edge_v2_paper_events.jsonl
  - logs/paper/reversal_edge_v2_paper_trades.jsonl
  - reports/paper/reversal_edge_v2_paper_summary.json
  - reports/paper/reversal_edge_v2_paper_summary.txt
- 현재 확인 기준:
  - events 파일 증가: WS 수집 정상
  - trades 파일 증가: paper 진입/청산 발생
  - trades 0이어도 조건 미발생이면 정상 가능

## 7. 다음 단계
1. 6시간 Paper 결과 확인
2. trades 수 / 평균 Net PnL / TP / SL / Timeout 확인
3. 결과가 좋으면 24시간 Paper Runner로 확장
4. 끊김 방지형 OOS Chunk Runner 설계
5. Higher Timeframe Regime Filter 진단 도구 설계
6. Auto Research Loop 설계
7. tiny_live는 최소 24시간 이상 Paper 양수 결과 후 별도 승인 필요

## 8. 추가 설계 방향
- Control Center UI 필요
  - Run Paper
  - Stop
  - Status
  - Open Summary
  - Open Logs
  - Candidate Snapshot
  - Why Card
  - Safety Guard
- Auto Research Loop 필요
  - 데이터 수집
  - 진단
  - 후보 생성
  - 백테스트
  - OOS
  - Paper
  - 사람 승인
- 자동으로 해도 되는 것:
  - 후보 생성
  - 리포트 생성
  - 백테스트
  - OOS 비교
- 자동으로 하면 안 되는 것:
  - 실거래 전환
  - config 자동 반영
  - 주문 권한 활성화
  - 손실 제한 완화

## 9. 절대 금지
- live.enabled=true 자동 변경 금지
- orderflow_paper.py 즉시 수정 금지
- candidate 자동 실거래 반영 금지
- API Key 사용 금지
- Upbit 주문 API 호출 금지
- logs/paper 실행 중 파일 수정 금지

## 10. 현재 판단
- Reversal Edge v2는 가장 유망한 후보
- 아직 실거래 전략은 아님
- 현재 단계는 실시간 Paper 검증 초입
- 다음 핵심은 6시간 Paper 결과와 24시간 Paper 확장 여부 판단
