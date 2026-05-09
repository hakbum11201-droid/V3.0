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
(이 단계는 실거래 전환을 위한 핵심 데이터 파이프라인을 정립한 단계임.)

## v3.1
개인용 관제 UI, DDM(Drawdown Defense Manager) 및 리스크 차단 게이트 연동.
- [x] Phase 1: Streamlit 기반 UI Foundation (한국어)
- [x] Phase 2: DDM Foundation
- [x] Phase 3: DDM Paper Gate (위험 시 신규 진입 자동 차단)
- [ ] Phase 4: Paper PnL & MDD 정밀 추적 및 시각화
- [ ] Phase 5: Account Snapshot (조회 전용 실계좌 연동)
- [ ] Phase 6: Long Paper Verification (7일 이상 장기 무중단 운영)

## v3.2 (Future: Live Transition)
실환경 주문 기능 활성화 및 단계적 실거래 전환.
- Phase 7: tiny_live (소액 실거래 테스트 및 체결 오차 분석)
- Phase 8: 정규 실거래 운영 및 자산 운용 최적화

상세 마스터 플랜: `V3_LIVE_TRADING_MASTER_PLAN_KR.md` 참조.
