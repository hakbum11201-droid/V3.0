# Reversal Entry Funnel Diagnostics 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략의 24H Paper 실행 결과, 약 39.4만 개의 막대한 시장 이벤트(Events)가 수집되었음에도 실제 매매 진입(Trades)이 **0건**으로 기록되었습니다. 이로 인해 수익률 분석 도구들이 모두 `NEED_MORE_DATA`를 반환하고 있습니다.

본 도구는 **"수많은 데이터 속에서 왜 전략이 한 번도 방아쇠(Trigger)를 당기지 못했는가?"**를 진단하기 위한 원인 분석 파이프라인(Funnel Diagnostics)입니다.

## 2. 주요 기능 및 진단 항목

본 스크립트(`tools/diagnose_reversal_entry_funnel.py`)와 심층 탐색 스크립트(`tools/inspect_candidate_schema.py`)는 다음 항목을 연계 검사합니다.

1. **데이터 수집 정합성 및 정규화(Normalization)**
   - **Market 필터링**: 타겟 마켓(`KRW-SOL`)의 이벤트가 정상적으로 들어오고 있는가?
   - **Event Type 정규화**: `orderbook_sample`처럼 백테스트 엔진이 즉각 인식하지 못하는 raw type을 `orderbook`으로 정규화하여 올바른 분포를 집계합니다.
2. **조건 병목 및 심층 스키마 탐색 (Schema Inspection)**
   - `Candidate` 파일의 표면적인 `thresholds`가 `{}`로 비어있더라도, 하위/다른 계층에 은닉된 `score`, `threshold`, `cost`, `tp`, `sl`, `timeout`을 재귀적으로 찾아내어 병목 원인을 진단합니다.
   - 현재 시장 변동성(RANGE) 대비 `cost_floor`나 발견된 조건들이 너무 높게 설정되어 진입을 0회로 만들었는지 추정합니다.
3. **Master Dataset 축소 원인 및 파이프라인 진단**
   - 수집된 이벤트가 Master Dataset에서 누락되지 않도록(예: `timestamp` 중복, 필드 누락 등) 파이프라인의 Data Loss 구간을 진단하여 제시합니다.

## 3. 출력 결과

1. **JSON 보고서**: `reports/experiments/reversal_entry_funnel_diagnostics_latest.json`
   - 통계적 분포 및 파싱 결과를 구조화하여 저장합니다.
2. **TXT 보고서**: `reports/experiments/reversal_entry_funnel_diagnostics_latest.txt`
   - 사람 운영자가 즉시 읽고 판단할 수 있도록 한국어로 작성된 상세 원인 분석과 **다음 조치 제안(Next Steps)**을 포함합니다.

## 4. 안전 원칙

- 이 도구는 **Read-Only** 입니다. 원본 코드를 수정하지 않으며 오직 진단(Diagnostics) 결과만 출력합니다.
- `live.enabled` 등의 안전 장치 우회는 절대 금지됩니다.
