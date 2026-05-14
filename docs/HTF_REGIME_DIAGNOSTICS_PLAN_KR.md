# HTF Regime Diagnostics 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략은 단기 주문흐름(Orderflow) 및 반등을 노리는 스캘핑/단타 전략이므로, 상위 타임프레임(HTF: Higher Timeframe)의 시장 환경이 강한 하락장(BEAR)이거나 급락장(CRASH)일 경우 치명적인 손실을 입을 위험이 크다.

이를 방지하기 위해 BTC의 24시간 및 72시간 흐름, 그리고 전체 주요 알트코인 시장의 등락 비율을 종합적으로 분석하여 현재 시장 레짐(Regime)을 진단하고, 전략 진입 여부를 제어(허용/제한/차단)할 수 있는 가이드라인 도구를 구축한다.

## 2. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/htf_regime_diagnostics.py` | Upbit 공개 API를 호출하여 시장 상태를 수집하고 레짐을 진단하는 핵심 스크립트 |
| `RUN_HTF_REGIME_DIAGNOSTICS.bat` | Windows 환경에서 진단 스크립트를 즉시 구동하기 위한 배치 스크립트 |
| `reports/experiments/htf_regime_diagnostics_latest.json` | 분석 및 진단 결과의 기계 판독형 포맷 |
| `reports/experiments/htf_regime_diagnostics_latest.txt` | 사람이 읽고 직관적으로 시장 상황을 이해할 수 있는 요약 텍스트 리포트 |

## 3. 분석 대상 및 지표 수집 (Upbit 공개 API)

본 도구는 보안을 위해 API Key가 필요한 개인 API를 사용하지 않으며, 오직 공개 API(Ticker, Candles)만 활용한다.

1. **분석 마켓 후보**: `KRW-BTC`, `KRW-ETH`, `KRW-XRP`, `KRW-SOL`, `KRW-DOGE`, `KRW-ADA`
2. **주요 추출 지표**:
   - `BTC 24H 변화율` 및 `BTC 72H 변화율` (전반적 대세 상승/하락 파악)
   - `SOL/XRP 24H 변화율` (주 타겟 마켓의 개별 컨디션 확인)
   - `시장 상승/하락 비율` (알트코인 전반의 투심 파악)
   - `급락 마켓 비율` (패닉 셀 동반 발생 여부 파악, 기준치: -5% 이하)

## 4. 레짐 판별 및 Reversal Edge 승인 조건

수집된 데이터를 기반으로 아래와 같이 시장 레짐을 판별하고, 그에 따른 전략 구동 권고(`Permission`)를 내린다.

| 레짐 (Regime) | 조건 | Reversal Edge 허용 여부 | 설명 |
|---|---|---|---|
| **CRASH** | BTC 24h < -5% 또는 급락(-5% 이하) 마켓 비율 >= 50% | `BLOCK` | 시장 전체 패닉 상태. 반등 매수 절대 금지 |
| **BEAR** | BTC 24h < -1.5% & 72h < -3.0% 또는 하락 마켓 비율 >= 60% | `RESTRICTED` | 우하향 추세. 전략 구동을 극도로 제한하거나 중지 |
| **BULL** | BTC 24h > 1.0% & 72h > 2.0% & 상승 마켓 비율 >= 60% | `ALLOW` | 견조한 상승/눌림목 장세. 전략 구동 최적기 |
| **RANGE** | 위 조건들에 해당하지 않는 경우 | `ALLOW_PREFERRED` | 횡보/혼조세. Reversal Edge의 짧은 틱 떼기에 유리함 |
| **UNKNOWN** | API 오류 등 데이터 수집 실패 시 | `CAUTION` | 데이터 부족으로 판별 불가. 보수적으로 운영 요망 |

## 5. 설계 안전 원칙

1. **오류 대응(Resilience)**: Upbit API 호출 시 Timeout이 발생하거나 특정 마켓의 데이터가 누락되어도 프로그램이 크래시(Crash)되지 않도록 예외 처리(`try-except`)를 강제한다.
2. **데이터 부족 대비**: 수집된 데이터가 부족할 경우 시스템의 기본 동작은 보수적인 `UNKNOWN` 및 `CAUTION` 모드로 진입한다.
3. **완전한 Read-Only 운영**: 이 도구는 `config` 파일을 자동 수정하지 않으며, 실거래 진입 버튼이나 제어 API를 호출하지 않는다. 
4. **책임 고지**: 출력되는 TXT 리포트 하단에 "사람 승인 전 tiny_live 금지" 및 "config 자동 반영 금지" 등 운영 원칙을 명시한다.
