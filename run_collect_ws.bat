@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - collect Upbit WebSocket data
echo ========================================
echo.
echo This collects PUBLIC Upbit trade/orderbook data only.
echo Live trading is disabled.
echo.

set PYTHONPATH=%CD%\src

python -m coinb.main collect-ws --config config/config.json --seconds 30 --output logs/upbit_ws_events.jsonl

if errorlevel 1 (
    echo.
    echo [FAIL] Upbit WebSocket collection failed.
    echo.
    echo If the error says websocket-client is missing, run:
    echo python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Upbit WebSocket collection completed.
echo Output: logs/upbit_ws_events.jsonl
pause
exit /b 0