# coinB PRO v3.1

업비트 KRW 마켓 주문흐름(Orderflow) 기반 개인용 자동매매 관제 시스템.

이 프로젝트는 단순 프로토타입을 넘어, **1인 개인이 실제로 운영 가능한 업비트 실거래 자동매매 시스템** 구축을 최종 목표로 합니다. 
현재는 **Paper Trading 기반의 연구 및 검증 단계**에 있으며, 철저한 안전 장치와 검증 절차를 거친 후 단계별 실거래 전환을 추진합니다.

## 핵심 목표
1. **전문가급 관제**: 개인용 로컬 대시보드(Streamlit)를 통한 실시간 시장 및 시스템 모니터링.
2. **손실 방어 우선**: DDM(Drawdown Defense Manager)을 통한 리스크 감지 및 신규 진입 자동 차단.
3. **데이터 중심 검증**: 업비트 WebSocket 기반 주문흐름(Orderflow) 미시구조 분석을 통해 기대값이 남는 거래 선별.
4. **단계적 실거래**: Conservative -> Moderate 실험으로 최적의 기준을 찾고, 소액 실거래(tiny_live) 모드를 거쳐 실제 자산 운용에 투입.
5. **성과 지향**: 수익률보다 원금 방어를 우선하며, 연환산 **net_pnl 5%** 이상의 실질적 가치 창출을 목표로 함.

## 현재 프로젝트 상태 (V3.1 Foundation)
- **데이터**: Upbit 공개 WebSocket 실시간 수집 및 Microstructure 특징 추출.
- **엔진**: 백그라운드 `paper_engine`을 통한 자동 판단, 학습 로그, 손실 분석 수행.
- **UI**: 한국어 기반 Streamlit 대시보드로 시스템 상태 및 DDM 리스크 실시간 시각화.
- **안전**: DDM Gate를 통한 Paper 신규 진입 차단 연동 완료.
- **제한**: 현재 `live.enabled = false` 및 `default_mode = paper`가 엄격히 적용 중입니다.

---

## 주요 문서 링크
- [docs/README_DOCS_KR.md](docs/README_DOCS_KR.md) - 전체 문서 체계 및 우선순위 안내
- [docs/CURRENT_RESEARCH_STATE_KR.md](docs/CURRENT_RESEARCH_STATE_KR.md) - Reversal Edge v2 등 최신 전략 연구 현황
- [docs/HIGHER_TIMEFRAME_REGIME_FILTER_PLAN_KR.md](docs/HIGHER_TIMEFRAME_REGIME_FILTER_PLAN_KR.md) - 시장 레짐 필터 설계 계획

---

## Quick Start (Windows PowerShell)

```powershell
# 1. 환경 설정
cd <프로젝트 루트>
$env:PYTHONPATH = "$PWD\src"

# 2. 시스템 검증
python -m coinb.main validate-config --config config/config.json
```

## 1. Offline Smoke Tests
아래 명령들은 오프라인 환경이나 API 연결 없이도 실행 가능합니다.

```powershell
# 샘플 데이터 기반 백테스트
python -m coinb.main backtest --config config/config.json --csv data/sample_ohlcv.csv

# 성과 리포트 생성
python -m coinb.main report --config config/config.json
```

## 2. Background Engine 실행
V3.1부터 제공되는 개인용 로컬 관제 UI와 백그라운드 Paper Engine은 다음 스크립트로 실행/종료합니다.

**실행**:
```
RUN_COINB_ALL.bat
```

**종료**:
```
STOP_COINB_ALL.bat
```

---

## Project Structure
- `src/coinb/`: Python 소스 패키지
- `tests/`: unittest 테스트 코드
- `config/config.json`: 시스템 설정 (live.enabled=false 고정)
- `docs/`: 전략 설계 및 상태 문서
- `logs/`: 실행 및 수집 로그 (자동 생성)
- `reports/`: 분석 리포트 (자동 생성)

## Security & Safety
- **Keyless Mode**: 기본적으로 API Key 없이 Paper Mode로 작동합니다.
- **보안 정책**: 자세한 내용은 [SECURITY_KEY_POLICY_KR.md](docs/SECURITY_KEY_POLICY_KR.md)를 참고하세요.
- **안전 원칙**: `live.enabled = false` 코드로 강제 차단 및 DDM 위험 감지 로직 적용.
