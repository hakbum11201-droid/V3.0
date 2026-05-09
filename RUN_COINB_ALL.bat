@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo V3.1 coinB PRO Dashboard (Streamlit)
echo ========================================

set PYTHONPATH=%CD%\src

echo [INFO] Starting Streamlit UI...
streamlit run src/coinb/ui_dashboard.py

pause
exit /b 0
