# REGIME-AWARE MEDIUM HORIZON MINING PLAN

## 1. 개요
초단기 (execution-aware) feature 공간이 수수료 및 슬리피지(0.05%) 비용 장벽을 넘지 못함이 확인됨에 따라, 5~15분 보유 기반의 Regime-Aware Medium Horizon 탐색으로 전환한다. 거래 횟수를 줄이더라도 1회 기대 수익(TP 1.0~3.0%)을 높여 비용 장벽을 안정적으로 넘는 전략적 엣지를 찾는 것을 목표로 한다.

## 2. 목표
- 보유 기간 5~30분의 Medium Horizon 엣지 발견
- TP 1.0~3.0%, SL -0.5~-1.5% 수준의 가격 반경에서 유효한 타점 발굴
- Entry(Ask) / Exit(Bid) 기준 체결 리얼리티 확보 및 Spread Filter 적용
- Regime/Momentum/Pullback 기반의 4개 Signal Family 성능 비교 검증

## 3. 탐색 대상 Signal Families
1. **Regime Momentum**: 중기 상승 모멘텀 유지장
2. **Pullback in Uptrend**: 상승장 내 단기 눌림목 반등
3. **Volatility Breakout**: 변동성 수축 후 거래량 동반 돌파
4. **Liquidity Quality Momentum**: 우량 호가 및 유동성 기반 모멘텀

## 4. 검증 및 생존 기준
- **수익성**: slip 0.05% 차감 후 Net PnL > 0 (Strong: > 0.10%)
- **안정성**: Test PF >= 1.15 (Strong: >= 1.3)
- **보편성**: Test Trades >= 20, Viable Markets >= 2, Top1 Market Share < 60%
- **체결성**: Fallback Rate < 30%

## 5. 산출물
- `tools/run_regime_aware_medium_horizon_mining.py` (탐색기)
- TXT / JSON 리포트 (Candidate 생성 및 Config 변경 절대 없음)
