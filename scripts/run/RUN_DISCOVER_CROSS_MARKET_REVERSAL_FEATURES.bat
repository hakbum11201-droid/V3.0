@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Starting Cross-Market Reversal Feature Discovery...
echo [Info] This will scan the master dataset and extract orderflow features.
echo.

python tools\discover_cross_market_reversal_features.py

if errorlevel 1 (
    echo.
    echo [Error] Feature discovery failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\cross_market_feature_discovery_latest.txt
echo ============================================================
pause
