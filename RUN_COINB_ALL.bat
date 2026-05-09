@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo V3.1 coinB PRO Dashboard (Streamlit)
echo ========================================

set PYTHONPATH=%CD%\src

if not exist logs\ws_raw mkdir logs\ws_raw
if not exist reports mkdir reports
if not exist runtime mkdir runtime

echo [INFO] Starting Background Paper Engine...
start "CoinB Paper Engine" python -m coinb.paper_engine

echo [INFO] Starting Streamlit UI...
start "CoinB Streamlit UI" streamlit run src/coinb/ui_dashboard.py

echo.
echo Both Engine and UI are started in separate windows.
echo Use STOP_COINB_ALL.bat to stop them.
pause
exit /b 0
