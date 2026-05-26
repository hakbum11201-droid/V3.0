@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo Reversal Edge v2 OOS Chunk Backtest Pipeline
echo ======================================================

if not exist logs\experiments\chunks mkdir logs\experiments\chunks
if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Running Pipeline...
python tools\run_reversal_oos_chunk_backtest_pipeline.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Pipeline Completed
echo ======================================================
echo.
type reports\experiments\reversal_oos_chunk_pipeline_summary.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo 파이프라인 실행 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
