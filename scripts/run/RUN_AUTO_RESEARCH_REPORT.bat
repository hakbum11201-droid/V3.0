@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo Auto Research Report Generator
echo ======================================================

if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating Auto Research Report...
python tools\generate_auto_research_report.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Report Generated Successfully
echo ======================================================
echo.
type reports\experiments\auto_research_report_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo 리포트 생성 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
