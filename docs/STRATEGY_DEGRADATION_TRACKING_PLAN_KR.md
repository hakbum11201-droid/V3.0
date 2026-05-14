# Strategy Degradation Tracking 설계안

## 1. 배경 및 목적

`Reversal Edge v2` 전략이 Paper 검증이나 실거래(차후)에서 장기간 운영될 때, 시간이 지남에 따라 시장 환경 변화(Regime Shift), 엣지 소멸(Edge Decay), 수수료/슬리피지 변동 등으로 인해 초기 백테스트에서 보여주었던 우수한 성과가 지속적으로 망가질 수 있다.

본 도구는 **"전략의 성과가 시간이 지남에 따라 점진적으로 또는 급격하게 악화(Degradation)되고 있는가?"**를 자동으로 감시하고 조기 경보를 울려주는 역할을 한다.

## 2. 파일 구성

| 파일명 | 역할 |
|---|---|
| `tools/run_strategy_degradation_tracking.py` | 기존 Paper Trades 로그와 각종 Report Summary를 읽어들여 최근 성과(Recent Metrics)를 추출하고 평가하는 파이썬 스크립트 |
| `RUN_STRATEGY_DEGRADATION_TRACKING.bat` | Windows 환경 전용 일괄 실행 배치 스크립트 |
| `docs/STRATEGY_DEGRADATION_TRACKING_PLAN_KR.md` | 도구 로직 및 판단 기준 가이드라인 (현재 파일) |
| `reports/experiments/strategy_degradation_tracking_latest.json/txt` | Tracking 결과 및 Action 플랜이 담긴 요약 보고서 |

## 3. 평가 지표 (Metrics)

모든 거래 데이터(`jsonl`)는 시간 순서로 기록됨을 가정하며, 전체 누적 성과가 아닌 **"최근 N건의 추세"**를 중점적으로 계산한다.

1. **최근 PnL 추세**:
   - `recent_10_avg_net_pnl`: 가장 최근 10건의 거래 평균 순수익
   - `recent_30_avg_net_pnl`: 가장 최근 30건의 거래 평균 순수익
2. **최근 승률 변화**:
   - `recent_10_win_rate` vs `recent_30_win_rate` 비교
3. **위험(Risk) 지표**:
   - `sl_ratio`: 전체 거래 중 손절(SL) 마감 비율
   - `timeout_ratio`: 전체 거래 중 시간초과(Timeout) 마감 비율

## 4. 성과 악화 판단 기준 (Judgement)

산출된 Metric을 바탕으로 아래 조건들을 위에서부터 순차적으로 검사하여 최종 상태(State)를 부여한다.

| 진단 라벨 | 발동 조건 | Action / 다음 행동 제안 |
|---|---|---|
| **NEED_MORE_DATA** | 거래 데이터(Trades)가 0건일 때 | "24H Paper 종료 후 재실행" |
| **DEGRADED** | `recent_10_avg_net_pnl < 0` (최근 10건 성과가 음수일 때) | "최근 손실 구간 분석 필요" |
| **RISK_DEGRADED** | `sl_ratio >= 0.5` (손절 비율 50% 이상) | "SL 조건 또는 진입 조건 재검토" |
| **WEAK_SIGNAL** | `timeout_ratio >= 0.7` (타임아웃 마감 70% 이상) | "Timeout 과다. 진입 조건 또는 TP/Timeout 재검토" |
| **POSSIBLE_DEGRADATION** | `recent_30_wr - recent_10_wr >= 15.0%` (승률 급락 시) | "최근 성과 하락. 추가 Paper 또는 구간별 분석 필요" |
| **HEALTHY** | 위 모든 악화 조건에 해당하지 않을 때 | "3D Paper 검증 후보" |

## 5. 설계 안전 원칙

1. **Read-Only**: 오직 기존 로그 및 Summary 파일들만을 파싱하며, 어떠한 전략 코드나 엔진 동작 상태를 런타임에 직접 조작하지 않는다.
2. **실거래 보호**: 결과가 `HEALTHY`로 나오더라도, 본 도구가 직접 `live.enabled=true` 설정을 켜지 않으며, 실거래 전환은 오직 사람의 승인을 통해 `tiny_live`부터 점진적으로 이루어진다.
3. **가동성**: Trades 파일(`jsonl`)이 삭제되거나 누락된 상태라도 프로그램이 크래시(Crash)되지 않으며, 사용 가능한 다른 JSON Summary 값을 최대한 참고하여 `NEED_MORE_DATA` 등 안전한 Fallback 처리를 수행한다.
