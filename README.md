# coinB PRO v3.1

업비트 KRW 마켓 주문흐름(Orderflow) 기반 개인용 자동매매 관제 시스템.

이 프로젝트는 단순 프로토타입을 넘어, **1인 개인이 실제로 운영 가능한 업비트 실거래 자동매매 시스템** 구축을 최종 목표로 합니다. 현재는 **Paper Trading 기반의 연구 및 검증 단계**에 있으며, 철저한 안전 장치와 검증 절차를 거친 후 단계별 실거래 전환을 추진합니다.

## 핵심 목표
1. **전문가급 관제:** 개인용 로컬 대시보드(Streamlit)를 통한 실시간 시장 및 시스템 모니터링.
2. **손실 방어 우선:** DDM(Drawdown Defense Manager)을 통한 리스크 감지 및 신규 진입 자동 차단.
3. **데이터 중심 검증:** Orderflow 미시구조 분석과 Paper Trading을 통한 장기 수익성 검증.
4. **단계적 실거래:** tiny_live(소액 실거래) 모드를 거쳐 검증된 전략만 실제 자산 운용에 투입.

## 현재 프로젝트 상태 (V3.1 Foundation)
- **데이터:** Upbit 공개 WebSocket 실시간 수집 및 Microstructure 특징 추출.
- **엔진:** 백그라운드 `paper_engine`을 통한 자동 판단, 학습 로그, 손실 분석 수행.
- **UI:** 한국어 기반 Streamlit 대시보드로 시스템 상태 및 DDM 리스크 실시간 시각화.
- **안전:** DDM Gate를 통한 Paper 신규 진입 차단 연동 완료.
- **제한:** 현재 `live.enabled = false` 및 `default_mode = paper`가 엄격히 적용 중입니다.

---

## Quick Start (Windows PowerShell)

```powershell
cd <프로젝트 루트>
$env:PYTHONPATH = "$PWD\src"
```

## 1. Offline Smoke Tests (네트워크/API 불필요, 샘플 데이터 기반)

아래 명령들은 오프라인 환경이나 API 연결 없이도 실행 가능합니다.

```powershell
# 1) 설정 유효성 검증
python -m coinb.main validate-config --config config/config.json

# 2) 샘플 데이터 기반 백테스트
python -m coinb.main backtest --config config/config.json --csv data/sample_ohlcv.csv

# 3) 성과 리포트 생성
python -m coinb.main report --config config/config.json

# 4) 설정 튜너 실행
python -m coinb.main tune --config config/config.json --csv data/sample_ohlcv.csv

# 5) 페이퍼 모드 체크
python -m coinb.main paper-check --config config/config.json
```

정상 기준:
- `validate-config` → `"ok": true`, `"mode": "paper"`, `"live.enabled": false`
- `backtest`, `report`, `tune` 정상 종료 및 `logs/`, `reports/`, `runtime/` 폴더 내 결과물 생성

## 2. Live Data Tests (네트워크/Upbit API 필수)

아래 명령들은 인터넷 연결 및 Upbit Public WebSocket API 접근이 필요합니다. 네트워크 상태에 따라 실패할 수 있습니다.

```powershell
# 1) Upbit WebSocket 실시간 데이터 수집 (예: 5초)
python -m coinb.main collect-ws --config config/config.json --seconds 5 --output logs/upbit_ws_events.jsonl

# 2) 미시구조(Microstructure) 스냅샷 생성
python -m coinb.main microstructure --micro-input logs/upbit_ws_events.jsonl --micro-output reports/microstructure_snapshot.json

# 3) 주문 흐름(Orderflow) 페이퍼 스텝 실행
python -m coinb.main orderflow-paper --config config/config.json --micro-output reports/microstructure_snapshot.json --paper-state runtime/orderflow_paper_state.json --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl

# 4) 머신러닝 학습 데이터셋 생성
python -m coinb.main learning-log --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --learning-output logs/orderflow_learning_dataset.jsonl --learning-summary reports/orderflow_learning_summary.json

# 5) 손실 분석(Loss Analysis) 리포트 생성
python -m coinb.main loss-analysis --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --loss-output reports/orderflow_loss_analysis.json
```

## 3. 편리한 메뉴 실행

위 명령들을 그룹화하여 쉽게 실행할 수 있습니다.

```
START_COINB.bat
```

메뉴 선택:
- `[1]` Basic Check (Offline Smoke Tests 자동 실행)
- `[2]` Orderflow Paper Cycle (Live Data Tests 자동 실행)
- `[3]` Tuner (샘플 데이터 기반 설정 후보 생성)

## 4. Paper Data Collection (데이터 축적 실행 방법)

V3.1 데이터 수집 및 학습 흐름을 위한 Paper 데이터 축적은 다음 스크립트로 진행합니다. 공개 웹소켓으로 데이터를 수집하여 판단/결과 로그를 누적합니다.

```powershell
$env:PYTHONPATH = "$PWD\src"
# 1) 일정 시간 WS 수집 (데이터 축적)
python -m coinb.main collect-ws --config config/config.json --seconds 3600 --output logs/upbit_ws_events.jsonl

# 2) 수집된 데이터로 Paper 판단 및 학습 로그 생성
python -m coinb.main microstructure --micro-input logs/upbit_ws_events.jsonl --micro-output reports/microstructure_snapshot.json
python -m coinb.main orderflow-paper --config config/config.json --micro-output reports/microstructure_snapshot.json --paper-state runtime/orderflow_paper_state.json --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl
python -m coinb.main learning-log --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --learning-output logs/orderflow_learning_dataset.jsonl --learning-summary reports/orderflow_learning_summary.json
python -m coinb.main loss-analysis --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --loss-output reports/orderflow_loss_analysis.json

# 3) Config 조정을 위한 추천(후보) 요약 생성
python -m coinb.main paper-config-candidates --decisions logs/orderflow_paper_decisions.jsonl --loss-analysis reports/orderflow_loss_analysis.json --output-json reports/orderflow_config_candidates.json --output-txt reports/orderflow_config_candidates.txt
```
위 과정을 통해 `logs/` 디렉토리에 판단 기록(`orderflow_paper_decisions.jsonl`), 거래 기록(`orderflow_paper_trades.jsonl`), 학습용 데이터셋(`orderflow_learning_dataset.jsonl`)이 누적 생성됩니다.

---

## 5. Background Paper Engine & UI Dashboard

V3.1부터 제공되는 개인용 로컬 관제 UI(Streamlit)와 백그라운드 Paper Engine은 다음 스크립트로 실행/종료합니다.

**실행:**
```
RUN_COINB_ALL.bat
```
이 스크립트는 백그라운드로 `paper_engine`을 실행하고 브라우저로 Streamlit UI를 엽니다.  
엔진은 실시간 데이터를 자동 수집하고 판단/리포트를 갱신합니다.  
UI 접속 주소: `http://localhost:8501` (UI는 한국어를 기본 언어로 제공합니다.)

**종료:**
```
STOP_COINB_ALL.bat
```
이 스크립트는 실행 중인 Paper Engine과 Streamlit 프로세스를 안전하게 종료합니다.

### 로그 보관 정책
Paper Engine은 디스크 공간을 관리하기 위해 아래와 같이 로테이션을 수행합니다.
- `logs/ws_raw/`의 원본 데이터: 최근 6시간은 원본 보관, 24시간 이전 데이터는 압축 후 자동 삭제.
- 분석용 핵심 지표: `logs/microstructure_samples.jsonl` 및 판단/학습/손실 로그는 삭제하지 않고 유지됩니다.

---

## Next Phase: UI + DDM Roadmap

다음 개발 단계인 개인용 관제 UI, DDM(Drawdown Defense Manager) 및 계좌/성과 추적 계획은 아래 문서에서 확인할 수 있습니다.
- [docs/V3_UI_DDM_ROADMAP_KR.md](docs/V3_UI_DDM_ROADMAP_KR.md)

---

## Project Structure

```
src/coinb/          Python 소스 패키지
tests/              unittest 테스트
config/config.json  설정 파일 (live.enabled=false 고정)
data/               샘플 OHLCV CSV (오프라인 테스트용)
logs/               실행 로그 (자동 생성)
reports/            분석 리포트 (자동 생성)
runtime/            paper 상태 저장 (자동 생성)
START_COINB.bat     Windows 메뉴 실행기
```

---

## Safety

- `live.enabled = false` — config_loader.py에서 코드로 차단
- API Key, 실거래 주문 코드 없음
- paper/backtest/tune/report 모드만 동작