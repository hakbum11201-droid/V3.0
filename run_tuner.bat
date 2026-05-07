@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - run tuner
echo ========================================

set PYTHONPATH=%CD%\src

python -m coinb.main tune --config config/config.json --csv data/sample_ohlcv.csv

if errorlevel 1 (
    echo.
    echo [FAIL] tuner failed.
    pause
    exit /b 1
)

echo.
echo [OK] tuner completed.
pause
exit /b 0