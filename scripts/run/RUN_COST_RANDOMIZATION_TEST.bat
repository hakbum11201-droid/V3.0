@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo Cost Randomization Test for Reversal Edge v2
echo ======================================================

if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating Cost Randomization Test Report...
python tools\run_cost_randomization_test.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Report Generated Successfully
echo ======================================================
echo.
type reports\experiments\cost_randomization_test_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo 거래 비용 랜덤화 테스트 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
