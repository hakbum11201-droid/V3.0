# AGENTS.md - coinB PRO v3.0 개발 기준

## 역할
이 저장소는 Upbit KRW 마켓 자동매매 연구용 프레임워크다. 기본 모드는 paper/backtest이며, 실거래 주문은 명시 승인 전까지 금지한다.

## 최우선 원칙
1. 수익 보장 문구 금지
2. API Key 하드코딩 금지
3. 리스크 가드 우회 금지
4. 실거래 주문 코드 무단 추가 금지
5. 기존 구조 대규모 재작성 금지
6. 한 번에 하나의 기능만 수정
7. 수정 후 테스트/백테스트/리포트 생성 확인

## 완료 조건
- `run_tests.bat` 통과
- `run_backtest.bat` 실행 성공
- `run_report.bat` 리포트 생성
- `run_tuner.bat` 튜너 요약 생성
- `logs/trades.jsonl`, `reports/performance_summary.json` 확인

## 파일 역할
- `src/coinb/strategy.py`: 진입/청산 신호
- `src/coinb/risk.py`: 리스크 승인/차단
- `src/coinb/broker.py`: paper 체결/포지션
- `src/coinb/backtest.py`: 백테스트 루프
- `src/coinb/report.py`: 성과 분석
- `src/coinb/tuner.py`: 파라미터 튜닝
- `src/coinb/upbit_public.py`: 공개 시세 조회
- `src/coinb/live_disabled.py`: 실거래 차단 어댑터

## 다음 개선 순서
1. 페이퍼 장기 로그 축적
2. 손실 패턴 분석 강화
3. 코인별/시간대별 필터
4. 체결 현실성 강화
5. 주문 테스트 API 연동
6. 매우 제한적 소액 실거래 어댑터
