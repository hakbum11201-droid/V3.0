@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo Walk-forward Validation for Reversal Edge v2
echo ======================================================

if not exist logs\experiments\walk_forward mkdir logs\experiments\walk_forward
if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating Walk-forward Validation Report...
python tools\run_walk_forward_validation.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Report Generated Successfully
echo ======================================================
echo.
type reports\experiments\walk_forward_validation_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo Walk-forward Validation 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
