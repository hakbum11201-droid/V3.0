@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo ======================================================
echo Independent Holdout Validation
echo ======================================================

if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating Independent Holdout Validation Report...
python tools\run_independent_holdout_validation.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Validation Completed Successfully
echo ======================================================
echo.
type reports\experiments\independent_holdout_validation_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo Holdout Validation 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
