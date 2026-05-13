# coinB Control Center UI & Auto Research Loop 설계안

## 1. 설계 철학
- **자동 연구/운영 시스템**: 목표는 자동으로 실거래하는 봇이 아니라, 자동으로 데이터를 분석하고 후보 전략을 검증하는 전문가형 연구 및 운영 시스템이다.
- **5초 관제**: UI는 복잡한 수치를 나열하는 화면이 아니라, 운영자가 시스템의 건강 상태와 현재 기회를 5초 안에 판단할 수 있는 직관적인 관제판이어야 한다.
- **인적 승인 원칙**: 모든 자동화의 목적은 편의성과 검증 품질 향상이며, 실거래(live) 전환 및 핵심 설정 변경은 반드시 운영자의 명시적인 수동 승인을 거쳐야 한다.
- **연구 루프(Loop)**: "데이터 수집 → 진단 → 후보 생성 → 백테스트 → OOS(Out-of-Sample) → Paper → 승격 판단 → 사람 승인"으로 이어지는 파이프라인의 시각화와 보조를 최우선으로 한다.

## 2. 현재 UI 문제점
- **정보 과부하**: 개발자용 디버깅 정보가 많아 실제 운영 환경에서 즉각적인 의사결정이 어렵다.
- **연결성 부족**: 현재 실행 중인 Reversal Paper Runner와 UI의 마켓 보드, DDM 등의 데이터가 실시간으로 일관되게 연결되지 않아 운영상 혼란을 초래할 수 있다.
- **시인성 결여**: 시스템의 생존 여부(Runner Status), 실거래 차단 상태(LIVE OFF), 최근 거래 발생 여부, 로그 갱신 주기가 상단에서 강하게 강조되지 않는다.
- **맥락 부재**: "왜 지금 진입하지 않는가?"에 대한 설명(Why Card)이 부족하여 운영자가 시스템 오류인지 대기 상태인지 구분하기 힘들다.
- **운영 제어 미흡**: 단순 모니터링을 넘어 Runner의 시작/중단, 상태 체크, 로그 확인 등의 운영 도구가 파편화되어 있다.
- **연구 흐름 단절**: 전략의 개선 과정, 후보군 승격 조건, 실패 사례 분석 등의 연구 맥락이 UI에 반영되어 있지 않다.

## 3. UI 목표
운영자가 대시보드 접속 후 5초 안에 다음 8가지 질문에 답할 수 있어야 한다.
1. 지금 시스템이 정상적으로 실행 중인가? (Runner Status)
2. 실거래가 확실히 꺼져 있는가? (Safety Guard)
3. 최근 Paper 진입이나 거래가 있었는가? (Activity)
4. 데이터 로그가 실시간으로 갱신되고 있는가? (Heartbeat)
5. 왜 아직 진입이 없는가? (Why Card - 대기 사유)
6. 현재 검증 중인 후보 전략은 무엇인가? (Candidate Snapshot)
7. 이 후보가 다음 단계로 승격 가능한 상태인가? (Promotion Status)
8. 운영자가 다음에 수행해야 할 작업은 무엇인가? (Next Action)

## 4. 상단 핵심 카드 (Status Board)
대시보드 최상단에 6개의 핵심 지표 카드를 크게 배치하여 직관성을 극대화한다.
- **Runner Status**: `RUNNING` (초록) / `STOPPED` (회색) / `ERROR` (빨강)
- **Mode**: `PAPER` (파랑)
- **Live Trading**: `OFF` (초록 - 안전) / `ON` (빨강 - 주의)
- **Paper Trades**: 오늘 또는 현재 세션의 총 거래 횟수
- **Last Update**: `events.jsonl` 마지막 기록 후 경과 시간 (예: 5s ago)
- **Candidate Status**: `TESTING` (노랑) / `PROMISING` (초록) / `REJECTED` (빨강) / `NEED_DATA` (회색)

**색상 규칙**:
- 초록: 정상, 통과, 안전
- 노랑: 주의, 검증 중, 데이터 부족
- 빨강: 오류, 위험, 차단 필요, 승격 거부
- 회색: 비활성, 데이터 없음

## 5. Candidate Snapshot
현재 Runner에서 사용 중인 후보 전략의 상세 설정을 한눈에 표시한다.
- **Candidate File**: `reversal_edge_candidate_v2_from_36h.json`
- **Strategy Type**: Reversal Edge v2
- **Run Mode**: `STATIC_SOL_ONLY`
- **Target Market**: KRW-SOL
- **Exit Policy**: TP 0.4% / SL -0.1% / Timeout 300s
- **Cost Estimate**: Floor 0.20% (수수료+슬리피지)
- **Current Phase**: Paper Validation (24H+)
- **주의**: 이 정보는 모니터링용이며, UI에서의 수정은 실제 파일에 자동 반영되지 않음을 명시한다.

## 6. Why Card (Reasoning Engine)
"진입 없음"이 "고장"이 아님을 증명하여 운영자의 불안을 해소한다.
- **현재 상태**: `WAITING` (대기 중)
- **주요 대기 사유**:
  - Reversal Edge Score (현재 45 / 기준 60) → `미충족`
  - HTF Regime Filter → `상승장 대기`
  - Spread Pct (현재 0.15% / 기준 0.12%) → `차단`
  - Volatility (현재 0.02% / 기준 0.04%) → `데이터 부족`
- **시스템 건전성**: 수집 모듈 `정상`, 엔진 루프 `정상`, 잔고 연동 `Keyless`

## 7. Runner Control 버튼 그룹
운영에 필요한 제어 도구를 직관적으로 배치하되, 위험한 버튼은 철저히 배제한다.
- **초기 필수 버튼**:
  - `Run Paper 6H` / `Run Paper 24H`: 프리셋 실행
  - `Stop Runner`: 안전한 종료
  - `Status Check`: 프로세스 생존 및 로그 파일 정합성 검사
  - `Open Summary`: 최신 성과 리포트 팝업
  - `Open Logs Folder`: 탐색기로 로그 폴더 열기
- **연구 보조 버튼 (향후)**:
  - `Run OOS Validation`: 미검증 데이터 구간 백테스트
  - `Compare Candidates`: 다른 후보 전략과 성과 비교
  - `Promotion Check`: 승격 기준 자동 체크리스트 실행
- **절대 금지 버튼 (Safety First)**:
  - `Live Start`, `Real Trade`, `API Key Input` 등 주문 관련 기능
  - `Auto Apply Config`: 검증된 설정을 실제 운영 설정에 자동 덮어쓰기 금지

## 8. 대시보드 탭 구조
정보의 중요도와 사용 빈도에 따라 9개의 탭으로 구성한다.

1. **Dashboard**: 전체 현황, 핵심 카드, Why Card, 실거래 차단 상태 고정 표시.
2. **Runner**: 실행 프로세스(PID), 현재 실행 중인 CLI 명령줄, 실행 시간 및 남은 시간.
3. **Trades**: `trades.jsonl` 기반 최근 10개 거래 목록, 누적 수익률, TP/SL/Timeout 비율 통계. (거래 0건 시 "아직 거래 없음" 안내)
4. **Events**: `events.jsonl` 파일 상태, 마지막 heartbeat 시간, 이벤트 타입별(trade/orderbook/heartbeat) 빈도 카운트.
5. **Reports**: 최신 Paper Summary, Backtest 결과, OOS 분석 리포트 원문 뷰어.
6. **Candidate Lab**: 생성된 후보 전략들의 목록과 각 후보별 백테스트/OOS/Paper 성과 비교 매트릭스.
7. **Auto Research**: 주문흐름 분석을 통한 실패/성공 조건 자동 추출 및 차세대(vNext) 후보 조건 제안 (자동 적용 금지).
8. **Regime**: 상위 타임프레임(BTC 24h/72h) 변화율 및 현재 시장 레짐(상승/횡보/하락/급락) 시각화.
9. **Safety**: `live.enabled=false` 코드 수준 확인, Secret Guard 통과 여부, API Key 미사용 상태 확인.

## 9. 기존 UI 정리 및 배치 우선순위
- **상단 고정 (High Priority)**: Runner Status, LIVE OFF(강조), Events Heartbeat, Trades Count, Why Card, Candidate Snapshot.
- **하단/접기 (Low Priority)**: 마켓 보드(상세 수치), DDM 상세 리스크 항목, 과거 보고서 원문, 보안 정책 안내문.

## 10. Auto Research Loop 설계
본 시스템은 "자동 매매"가 아닌 **"자동 연구 보조"** 시스템으로 작동한다.
- **자동화 범위**: 데이터 수집 → 로그 병합 → 진단 실행 → 성공/실패 패턴 분석 → 후보 파라미터 제안 → 백테스트/OOS 실행 → 결과 요약.
- **수동 승인 필수 범위**: 실거래(live) 모드 전환, `config/config.json`의 실거래 설정 변경, 손실 제한(Stoploss) 완화, 승격 결정.

## 11. Promotion Guard (승격 관리) 설계
후보 전략이 Paper를 넘어 소액 실거래(tiny_live)로 가기 위한 엄격한 기준이다.
- **승격 승인 조건**:
  - OOS 데이터에서 Net PnL 양수 확인.
  - 24시간~72시간 Paper Trading에서 Net PnL 양수 유지.
  - 유의미한 거래 횟수 확보 (최소 10건 이상).
  - 특정 코인에 수익이 과하게 쏠리지 않는 마켓 분산 확인.
- **즉시 차단 및 기각 사유**:
  - OOS 또는 Paper에서 Net PnL 음수 발생.
  - 손절(SL) 발생 빈도가 비정상적으로 높음.
  - 특정 기간에만 수익이 발생하는 과최적화 의심.
  - 시스템이 `live.enabled=true` 자동 변경을 시도하는 경우.

## 12. Reversal Edge v2 현재 상태 정보
- **연구 맥락**: 기존 Continuation 전략 폐기 후, Orderflow Absorption 기반의 Reversal 패턴에서 유의미한 엣지 발견.
- **현재 단계**: `configs/experiments/reversal_edge_candidate_v2_from_36h.json` 후보를 대상으로 24H+ Paper 검증 중.
- **특이사항**: SOL 마켓에서 높은 승률(85%+) 확인, 전체 마켓 확장 시 Threshold 보정 필요.

## 13. Higher Timeframe Regime Filter 연동
- Reversal Edge는 미시구조 기반이므로, 시장 전체가 무너지는 하락장에서는 필터링이 필수적이다.
- UI는 BTC 24h 변화율 등을 기반으로 현재가 'Reversal 금지(급락장)' 상태인지 '적극 참여' 상태인지 명확히 표시한다.

## 14. UI 품질 기준 (Expert Design)
- **Less is More**: 불필요한 숫자는 숨기고, 색상과 아이콘으로 판단의 결과만 크게 보여준다.
- **Positive Confirmation**: "거래 0건"은 고장이 아닌 "안전하게 대기 중"임을 긍정적으로 시각화한다.
- **Safety First**: "실거래 차단(LIVE OFF)" 상태는 언제나 UI 어디서든 확인할 수 있어야 한다.
- **Actionable**: 단순히 보는 것을 넘어, "다음에 무엇을 검증해야 하는가"를 시스템이 제안한다.

## 15. 향후 개발 마일스톤
1. **Phase 1**: `ui_dashboard.py` 레이아웃 개편 및 상단 핵심 카드/Why Card 구현.
2. **Phase 2**: Runner 제어 버튼 연동 및 실시간 프로세스 모니터링 강화.
3. **Phase 3**: Candidate Lab 탭 및 OOS/Backtest 성과 비교 화면 추가.
4. **Phase 4**: Auto Research Loop 기반의 자동 리포트 및 후보 제안 기능 통합.

## 16. 절대 금지 지침 (Safety Guard)
- 어떠한 경우에도 UI에 실거래 관련 버튼이나 API Key 입력창을 추가하지 않는다.
- 후보 전략이 자동으로 실제 운영 설정(`config/config.json`)을 수정하게 하지 않는다.
- 주문 권한을 가진 API Key는 로컬 환경에서도 UI 접근을 차단한다.
- 운영자의 수동 확인 없이 `live.enabled` 설정을 true로 변경하지 않는다.
- 로그나 리포트를 UI에서 삭제하는 기능을 넣지 않는다.

## 17. 기대 효과
운영자는 PowerShell 터미널을 복잡하게 보지 않고도, 대시보드만으로 **"수집-검증-판단-안전"**의 모든 과정을 통제하고 연구 품질을 비약적으로 높일 수 있다.
- **정상 작동 여부 1초 확인**
- **대기 사유 즉각 이해**
- **전략의 승격 여부 데이터 기반 판단**
- **실거래 차단 상태 상시 확인을 통한 심리적 안정**
