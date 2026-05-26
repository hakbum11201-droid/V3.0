# Price-Path Result Analysis Plan (가격 경로 시뮬레이션 결과 분석 계획)

이 문서는 `reversal_price_path_paper_simulation_latest.json` 결과를 면밀히 파악하여, 전략의 실전 가동 가능성(Production Readiness), 비용 민감도(Cost Sensitivity), 마켓 편중(Market Bias)을 체계적으로 검증하기 위한 분석 도구 및 판정 기준 설계 계획을 정의합니다.

---

## 1. 개요 및 배경
최근 수행된 가격 경로 시뮬레이션(Price-Path Paper Simulation) 결과는 아래와 같은 수치를 기록하였습니다.
- **전체 거래 수 (Total Trades)**: 1,207건
- **전체 승률 (Win Rate)**: 49.46%
- **최적 조합**: TP +0.3% / SL -0.1% / Timeout 180s
- **슬리피지별 Net 수익률**:
  - Slip 0.03%: **+0.0371%** (생존)
  - Slip 0.05%: **-0.0029%** (손실 전환)
  - Slip 0.10%: **-0.1029%** (심각한 손실)

현재 전략은 **비용에 극도로 민감**하며, 특정 마켓(예: DOGE 및 UP2)에 거래가 편중되었을 가능성이 큽니다. 이에 따라, 단순 요약 수치에 기만당하지 않고 마켓별 세부 성과와 농축도(Concentration)를 객적으로 판정하는 분석 도구(`tools/analyze_reversal_price_path_results.py`)를 개발합니다.

---

## 2. 세부 설계 및 판정 기준

### A. 마켓별 성과 및 비용 추정 (Per-Market Analysis)
각 마켓 `m`에 대해 다음 항목을 도출합니다:
- **거래 비중 (Trade Concentration %)**: `(Market Trades / Total Trades) * 100`
- **승률 (Win Rate)**: `Win Count / Market Trades`
- **평균 총수익률 (Avg Gross PnL)**: 시뮬레이션 raw gross 수익률
- **비용 반영 Net 수익률 추정**:
  - `Net PnL = Avg Gross PnL - (0.05% + Slippage) * 2`
  - Upbit 기본 수수료(0.05%)와 각 슬리피지(0.03%, 0.05%, 0.10%)를 왕복(x2) 반영하여 추정합니다.

### B. 경고(Warning) 판정 기준
1. **Market Bias Warning (`market_bias_warning`)**:
   - 거래량 기준 1위 마켓의 거래 비중이 **40% 이상**인 경우.
2. **Strong Market Bias Warning (`strong_market_bias_warning`)**:
   - 거래량 기준 1위 + 2위 마켓의 합산 거래 비중이 **70% 이상**인 경우.
3. **Instability Warning (`instability_warning`)**:
   - 개별 마켓 간 승률의 표준편차(Standard Deviation)가 전체 승률(`49.46%`)보다 큰 경우 (마켓별 성과의 불확정성이 매우 높음을 의미).
4. **Large Market Coverage Warning (`large_market_coverage_warning`)**:
   - BTC, ETH, XRP, SOL과 같은 메이저 대형 마켓의 합산 거래 비중이 **5% 미만**이거나 거래 수가 극도로 저조한 경우.

### C. 최종 판단 (Judgement Heuristic)
분석 도구는 아래의 판단 기준에 따라 전략을 5가지 범주 중 하나로 최종 격리(Categorize)합니다:

- **PRICE_PATH_SURVIVES_COSTS**: Slip 0.05% 환경에서도 Net Positive 수익을 내며 메이저 마켓 분포가 안정적인 경우.
- **COST_SENSITIVE_WEAK**: Slip 0.03%에서는 생존하지만 Slip 0.05%에서 손실로 전환되는 경우.
- **MARKET_BIASED_RESEARCH_ONLY**: 특정 1~2개 마켓(DOGE/UP2)에서만 성과가 발생하고 메이저 마켓에서는 작동하지 않는 경우.
- **REJECT_CURRENT_COMMON_STRATEGY**: 저비용 슬리피지에서도 성과가 나쁘거나 경고 조건이 다수 중첩되어 공통 전략으로 채택 불가한 경우.
- **NEED_MARKET_SPECIFIC_RETEST**: 특정 마켓별로 파라미터를 완전히 분리하여 재시뮬레이션해야 하는 경우.

---

## 3. 구현 방식
- **입력**: `reports/experiments/reversal_price_path_paper_simulation_latest.json`
- **로직**: Python의 기본 `json`, `math` 모듈만을 활용하여 외부 의존성 없이 고도로 경량화된 독립 실행 도구 작성.
- **출력**:
  - JSON 형식 데이터: `reports/experiments/reversal_price_path_result_analysis_latest.json`
  - 분석 리포트 전문(TXT): `reports/experiments/reversal_price_path_result_analysis_latest.txt`

---

## 4. 검증 계획
1. **구문 검사**:
   - `python -m py_compile tools/analyze_reversal_price_path_results.py`
2. **동작 검증**:
   - 스크립트 실행 후 `reports/experiments/reversal_price_path_result_analysis_latest.txt` 파일이 규격에 맞게(NOT PRODUCTION READY 문구 포함 등) 잘 채워졌는지 직접 검사.
3. **Git 영향도 평가**:
   - `git status`를 수행하여 지정된 commit 대상 이외의 임시 로그, 데이터베이스 또는 리포트 파일이 변경/추가되지 않았는지 면밀히 감시.
