# V3 Next Phase: UI, DDM, Account Roadmap

## 1. 현재 상태 요약
- V3.0은 paper/research framework 단계
- 실데이터 기반 수집/분석/판단/리포트 흐름은 작동
- `trade_count`가 아직 0인 상태이며, 수익성 검증 완료 단계가 아님
- 다음 목표는 실거래가 아니라 관제/리스크/분석 UI 구축

## 2. 최종 목표
- 개인용 준전문가급 자동매매 관제·검증 시스템
- 실시간 마켓 보드
- paper 판단 로그 시각화
- DDM 리스크 차단
- paper PnL/Drawdown 추적
- 향후 실제 계좌 조회 연동
- 실거래 전 장기 paper 검증 체계

## 3. UI 기술 선택
- **1차 UI는 Streamlit 사용**
- **이유:**
  - Python 프로젝트와 직접 연결 쉬움
  - 빠른 개발 가능
  - logs/reports/runtime 파일을 바로 읽을 수 있음
  - 로컬 개인용 UI에 적합
- **실행 방식:**
  - `RUN_UI.bat`
  - `streamlit run src/coinb/ui_dashboard.py`
- **기본 접속:**
  - `http://localhost:8501`
- 외부 공개/HTTPS는 후순위
- 초기 목표는 로컬 개인용 관제 UI

## 4. UI 화면 구성
- **상단 상태바:**
  - Mode
  - live.enabled
  - WS 상태
  - 마지막 데이터 수신 시간
  - 대상 마켓
  - DDM 상태
  - 시스템 상태: RUNNING / BLOCKED / ERROR

- **마켓 보드:**
  - KRW-BTC, KRW-XRP, KRW-SOL
  - 현재가, spread_pct
  - buy_trade_value_3s, sell_trade_value_3s
  - bid_ask_depth_ratio_5
  - ofi_score, sweep_score, absorption_score, continuation_score
  - 현재 decision, reason, diagnostic actual/required/gap_pct

- **최근 판단 로그:**
  - 최근 100개 decision
  - timestamp, market, decision, reason, diagnostic
  - expected_edge, slippage_estimate, virtual_fill_result

- **Paper 성과판:**
  - decision_count, trade_count
  - virtual_buy_count, no_buy_count
  - realized_pnl_krw, avg_pnl_pct
  - win_rate, MDD, 연속 손실, open_positions

- **분석 리포트:**
  - paper_review_latest.txt 표시
  - orderflow_loss_analysis.json 요약
  - orderflow_config_candidates.txt 표시

## 5. DDM (Drawdown Defense Manager) 설계
**DDM 목적:**
- 수익률 개선 기능이 아니라 손실 방어 기능
- 위험 상태에서 신규 진입 차단
- 청산/정리 로직은 차단하지 않음
- 처음에는 UI 표시만 하고, 이후 paper 신규 진입 차단에 연결

**DDM 상태:**
- NORMAL, CAUTION, BLOCK_NEW_ENTRY, STOP_PAPER, DATA_ERROR

**DDM 감시 항목:**
- paper drawdown, 연속 손실, BTC 급락, 전체 마켓 spread 확대
- WS 데이터 지연, orderbook/trade 수신 끊김
- LOW_VOLUME 과다, 특정 마켓 반복 손실, 변동성 급등, 계좌 평가금액 급감

**DDM 출력 및 UI 표시:**
- `reports/ddm_status.json` 생성
- 현재 상태, 차단 여부, 차단 사유, 마지막 갱신 시간, 위험 레벨, 권장 조치 표시

## 6. 계좌/성과 추적 계획
**1단계 (Paper 계좌 표시):**
- starting_cash_krw, cash_krw, open_positions
- realized_pnl_krw, unrealized_pnl_krw
- equity_curve, max_drawdown

**2단계 (실제 Upbit 계좌 조회):**
- 단, **자산조회 전용 API Key만 사용** (주문 권한 금지)
- `.env` 파일 사용 (GitHub 업로드 금지)
- 조회 전용 모듈: `src/coinb/account_snapshot.py`, `reports/account_snapshot.json`

## 7. 개발 단계
- **Phase 1: UI Foundation**
  - Streamlit UI 생성 (`src/coinb/ui_dashboard.py`)
  - `RUN_UI.bat` 생성, 기본 파일/로그 연동 및 마켓/최근 판단 보드 구축
- **Phase 2: DDM Foundation**
  - `src/coinb/ddm.py` 생성 (`reports/ddm_status.json`)
  - UI에 DDM 상태 표시 (아직 차단 연동 X)
- **Phase 3: DDM Paper Gate**
  - DDM이 BLOCK_NEW_ENTRY일 때 orderflow-paper 신규 매수 차단 구현
- **Phase 4: Paper PnL & Drawdown**
  - paper 상태 기반 PnL 계산, equity curve/MDD 계산 및 UI 표시
- **Phase 5: Account Snapshot**
  - 실제 Upbit 잔고 조회 전용 기능 연결 (.env, 조회 권한 전용 Key만 사용)
- **Phase 6: Long Paper Verification**
  - 1일/3일/7일 단위 장기 paper 검증 운영 및 비교 리포트 생성

## 8. 안전 원칙
- 실거래는 별도 승인 전까지 철저히 금지 (`live.enabled=false` 유지)
- config 자동 변경 금지 (후보만 생성 유지)
- UI를 통한 버튼 하나로 실거래 켜기 금지
- API Key는 `.env`로 격리 보관하고 주문 권한 Key는 철저히 배제
- DDM은 신규 진입 차단 우선 동작 (손실 방어가 수익 개선보다 우선)

## 9. UI 및 언어 원칙
- **UI 기본 언어는 한국어:** 사용자가 보는 Streamlit 화면, 리포트 요약, 버튼/상태 문구는 한국어를 우선으로 사용한다.
- **내부 코드 및 데이터 구조 유지:** 내부 변수명, JSON Key, 로그 필드명 등은 기존 영어 체계를 유지하여 코드 일관성을 확보한다.
- **전문 용어 병기:** 필요한 경우 전문 용어는 영어와 병기할 수 있다. (예: DDM 손실 방어 관리자(Drawdown Defense Manager))
- **리포트 로컬라이징:** 자동 요약 리포트나 UI 상의 권장 조치 사항은 사용자가 즉각 이해할 수 있도록 한국어로 제공한다.
