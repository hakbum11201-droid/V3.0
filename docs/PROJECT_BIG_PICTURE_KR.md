# 프로젝트 큰 그림 (Big Picture)

## 1. 프로젝트 한 줄 정의
완전 무인 자동화된 단기 주문흐름(Orderflow) 기반 가상자산 실거래 봇 구축

## 2. 현재 목표
현재 상태는 **Paper Trading**을 통한 전략 무결성 검증 단계이며, 단기적으로 유망한 엣지 전략의 승률과 PnL 안정성을 확보하는 것이 목표입니다. 실거래 도입은 보수적인 검증을 완벽히 통과한 후에만 사람이 직접 판단하여 활성화합니다.

## 3. 전략 현황
- **현재 유망 전략**: `Reversal Edge v2` (강한 매도 압력 이후 반등하는 패턴)
- **실패/후순위 전략**:
  - Continuation (추세 추격형: 수수료 및 슬리피지 극복 불가)
  - Soft Score
  - Combined Filter
  - Market Factor Filter

## 4. 현재 검증 흐름
새로운 엣지를 발견하면 다음 단계를 거칩니다.
1. **Backtest**: 과거 데이터 기반 기본 검증
2. **OOS Chunk**: Out-of-Sample 데이터를 수집하여 추가 검증
3. **Paper**: 실제 시장 데이터 환경에서 가상매매 구동
4. **HTF Regime**: 상위 타임프레임 흐름 진단 후 승인 여부 판별
5. **Auto Research Report**: 전체 요약 및 다음 행동 권고
6. **사람 승인**: 이 모든 과정을 통과한 후 사람이 직접 확인

## 5. 작업 현황
- **현재 복사본(V3.0_WORK_UI)에서 완료한 도구**:
  - Control Center UI
  - OOS Chunk Runner
  - OOS Chunk Merge
  - OOS Chunk Backtest Pipeline
  - Auto Research Report Generator
  - HTF Regime Diagnostics
- **현재 원본(V3.0)에서 진행 중인 작업**:
  - Reversal Edge v2 Paper 24H

## 6. 다음 우선순위
1. 24H Paper 결과 분석
2. 복사본 개선사항 원본 반영
3. 3D Paper 또는 조건 조정
4. Walk-forward Validation
5. 비용 랜덤화 테스트
6. Strategy Degradation Tracking

## 7. 절대 금지 사항 (Safety Guard)
- `live.enabled=true` 자동 변경 금지
- `config` 자동 반영 금지
- 주문 API 추가 금지
- `logs/reports` 삭제 금지
