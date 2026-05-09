# V3 Next Phase: UI, DDM, Account Roadmap

## 1. 현재 상태 요약
- V3.1 Foundation 완료 (UI, DDM Gate 연동)
- 실데이터 기반 수집/분석/판단/리포트 및 리스크 차단 흐름 작동
- 다음 목표: 성과 추적(PnL/MDD) 시각화 및 실계좌 조회 연동

## 2. 최종 목표
- **1인 개인용 업비트 자동매매 관제·검증 및 실거래 시스템**
- 실시간 마켓 보드 및 정밀 미시구조 분석 시각화
- Paper Trading 판단 로그 시각화 및 PnL/MDD 추적
- DDM(Drawdown Defense Manager)을 통한 리스크 자동 차단
- 장기 Paper 검증 후 단계적 실거래(tiny_live) 전환

## 3. UI 기술 및 언어 원칙
- **기술:** Streamlit 기반 로컬 대시보드
- **언어:** 사용자가 접하는 모든 UI 및 리포트 요약은 **한국어**를 기본으로 함
- **보안:** 로컬 환경 전용 UI로 외부 노출 최소화
- **이유:** Python 연동성, 빠른 개발, 로컬 파일 직접 접근 가능
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
- **[x] Phase 1: UI Foundation (한국어)**
  - Streamlit UI 생성 (`src/coinb/ui_dashboard.py`)
  - `RUN_COINB_ALL.bat` 등을 통한 자동 실행 및 리포트 시각화
- **[x] Phase 2: DDM Foundation**
  - `src/coinb/ddm.py` 생성 및 리스크 분석 엔진 구축
- **[x] Phase 3: DDM Paper Gate**
  - DDM 위험 감지 시 `orderflow-paper` 신규 진입 자동 차단 연동 완료
- **Phase 4: Paper PnL & Drawdown**
  - paper 상태 기반 PnL 계산, equity curve/MDD 계산 및 UI 표시
- **Phase 5: Account Snapshot**
  - 실제 Upbit 잔고 조회 전용 기능 연결 (.env, 조회 권한 전용 Key만 사용)
- **Phase 6: Realistic Experimentation (Conservative -> Moderate -> Aggressive)**
  - **Conservative 결과:** 판단 180회, 거래 1회, LOW_VOLUME 약 80.56%. (너무 보수적임)
  - **Moderate 목표:** 거래 횟수를 늘리는 것이 아니라, 수수료 차감 후 기대값이 남는 현실적인 거래량 기준점 검토.
  - 1일/3일/7일 단위 장기 paper 검증 운영 및 비교 리포트 생성.

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
