@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo HTF Regime Diagnostics Tool
echo ======================================================

if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating HTF Regime Diagnostics Report...
python tools\htf_regime_diagnostics.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Report Generated Successfully
echo ======================================================
echo.
type reports\experiments\htf_regime_diagnostics_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo 진단 리포트 생성 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
