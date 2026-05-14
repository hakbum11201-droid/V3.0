@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo ======================================================
echo Diagnose Reversal Entry Funnel
echo ======================================================

if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Running Diagnostics...
python tools\diagnose_reversal_entry_funnel.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Diagnostics Completed Successfully
echo ======================================================
echo.
type reports\experiments\reversal_entry_funnel_diagnostics_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo 진입 펀넬 진단 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
