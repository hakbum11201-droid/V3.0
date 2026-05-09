# coinB PRO v3.0 로드맵

## v1.0
기본 엔진, 전략/리스크/브로커 분리.

## v1.1
거래 로그와 성과 분석기 추가.

## v1.2
손실 패턴 차단 필터 추가.

## v1.3
BTC 레짐 필터와 멀티팩터 전략 점수화.

## v1.4
ATR 기반 손절/익절/트레일링 및 체결 비용 모델 반영.

## v1.5
자동 튜너와 파라미터 비교 리포트.

## v2.0
공개 시세 API 클라이언트, 운영 디렉터리, 상태 저장 안정화.

## v3.0
운영형 연구 프레임워크 완성: 백테스트, 리포트, 튜너, 손실 차단, 레짐 필터, 테스트 포함.
(주의: v3.0은 실거래 자동주문 완성본이 아니라 실거래 전 검증용 운영 프레임워크다.)

## v3.1 (Next Phase)
개인용 관제 UI, DDM(Drawdown Defense Manager) 및 계좌 추적 연동.
- Phase 1: Streamlit 기반 UI Foundation
- Phase 2: DDM Foundation
- Phase 3: DDM Paper Gate (위험 시 신규 진입 차단)
- Phase 4: Paper PnL & Drawdown 추적
- Phase 5: Account Snapshot (조회 전용 실계좌 연동)
- Phase 6: Long Paper Verification (장기 Paper 운영)
자세한 내용은 `V3_UI_DDM_ROADMAP_KR.md` 참조.
