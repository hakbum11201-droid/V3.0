# coinB PRO v3.0.1

Upbit KRW market orderflow-based paper trading framework.

This project is a **paper trading / research system**.  
Live trading is intentionally disabled. `live.enabled = false` is enforced in code.

---

## Quick Start (Windows PowerShell)

```powershell
cd <프로젝트 루트>
$env:PYTHONPATH = "$PWD\src"
```

### 1. 검증 명령 (기준선 확인)

```powershell
python -m compileall src tests
python -m unittest discover -s tests -p "test_*.py"
python -m coinb.main validate-config --config config/config.json
```

정상 기준:
- `compileall` → 오류 없음
- `unittest` → `Ran 40 tests ... OK`
- `validate-config` → `"ok": true`, `"mode": "paper"`, `"live.enabled": false`

### 2. 메뉴 실행 (추천)

```
START_COINB.bat
```

메뉴 선택:
- `[1]` Basic Check (validate → test → backtest → report)
- `[2]` Orderflow Paper Cycle (WS수집 → microstructure → paper step → learning → loss)
- `[3]` Tuner (설정 후보 생성, 코드 수정 없음)

---

## Core Direction

```text
Upbit KRW market
→ public WebSocket trade/orderbook collection
→ microstructure feature calculation
→ virtual buy/sell paper decision
→ learning dataset generation
→ loss pattern analysis
→ config candidate tuning
→ long-term paper verification
→ tiny_live only after approval
```

---

## Project Structure

```
src/coinb/          Python 소스 패키지
tests/              unittest 테스트
config/config.json  설정 파일 (live.enabled=false 고정)
data/               샘플 OHLCV CSV
logs/               실행 로그
reports/            분석 리포트
runtime/            paper 상태 저장
START_COINB.bat     Windows 메뉴 실행기
```

---

## Safety

- `live.enabled = false` — config_loader.py에서 코드로 차단
- API Key, 실거래 주문 코드 없음
- paper/backtest/tune/report 모드만 동작