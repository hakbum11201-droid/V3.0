@echo off
cd /d %~dp0
set PYTHONPATH=%cd%\src

echo [1/5] Validate config
python -m coinb.main validate-config
if errorlevel 1 goto fail

echo [2/5] Run tests
python -m unittest discover -s tests
if errorlevel 1 goto fail

echo [3/5] Run backtest
python -m coinb.main backtest
if errorlevel 1 goto fail

echo [4/5] Run report
python -m coinb.main report
if errorlevel 1 goto fail

echo [5/5] Run tuner
python -m coinb.main tune
if errorlevel 1 goto fail

echo DONE. Check logs and reports folders.
pause
exit /b 0

:fail
echo FAILED. Check console output.
pause
exit /b 1
