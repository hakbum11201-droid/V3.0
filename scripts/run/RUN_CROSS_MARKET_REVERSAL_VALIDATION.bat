@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Starting Cross-Market Reversal Edge Universal Validation...
echo [Info] This runs 5 threshold grids x 3 cost scenarios = 15 backtests.
echo [Info] Each backtest on 4.1M rows takes ~5-10 minutes. Total: ~1.5-2.5 hours.
echo.

python tools\run_cross_market_reversal_validation.py

if errorlevel 1 (
    echo.
    echo [Error] Validation failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\cross_market_validation\cross_market_reversal_validation_latest.txt
echo ============================================================
pause
