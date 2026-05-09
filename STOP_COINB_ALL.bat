@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo Stopping V3.1 coinB PRO
echo ========================================

echo Stopping Paper Engine...
taskkill /FI "WINDOWTITLE eq CoinB Paper Engine*" /F /T >nul 2>&1

echo Stopping Streamlit UI...
taskkill /FI "WINDOWTITLE eq CoinB Streamlit UI*" /F /T >nul 2>&1

echo Done.
pause
exit /b 0
