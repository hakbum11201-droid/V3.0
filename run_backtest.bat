@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - run backtest
echo ========================================

set PYTHONPATH=%CD%\src

python -m coinb.main backtest --config config/config.json --csv data/sample_ohlcv.csv

if errorlevel 1 (
    echo.
    echo [FAIL] backtest failed.
    pause
    exit /b 1
)

echo.
echo [OK] backtest completed.
pause
exit /b 0