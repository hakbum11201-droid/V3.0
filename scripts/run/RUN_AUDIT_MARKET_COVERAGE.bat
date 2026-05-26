@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Auditing Market Coverage...
python tools\audit_market_coverage.py

if errorlevel 1 (
    echo.
    echo [Error] Audit failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\market_coverage_audit_latest.txt
echo ============================================================
pause
