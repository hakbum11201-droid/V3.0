@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - all check
echo ========================================

set PYTHONPATH=%CD%\src

echo.
echo [1/4] Validate config
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto FAIL

echo.
echo [2/4] Run tests
python -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 goto FAIL

echo.
echo [3/4] Run backtest
python -m coinb.main backtest --config config/config.json --csv data/sample_ohlcv.csv
if errorlevel 1 goto FAIL

echo.
echo [4/4] Generate report
python -m coinb.main report --config config/config.json
if errorlevel 1 goto FAIL

echo.
echo ========================================
echo [OK] all checks completed.
echo ========================================
pause
exit /b 0

:FAIL
echo.
echo ========================================
echo [FAIL] all check stopped.
echo ========================================
pause
exit /b 1