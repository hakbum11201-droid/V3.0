@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ========================================
echo Reversal Edge v2 OOS Chunk Runner 24H
echo 30min chunks x 48 = 24h total
echo ========================================

if not exist logs\experiments\chunks mkdir logs\experiments\chunks
if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] validate-config
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto FAIL

echo.
echo [STEP 2] Running OOS Chunk Runner (24H / 30min chunks)
python tools\run_reversal_oos_chunk_runner.py ^
  --duration-sec 86400 ^
  --chunk-sec 1800 ^
  --output-dir logs\experiments\chunks ^
  --summary-json reports\experiments\reversal_oos_chunk_runner_summary.json ^
  --summary-txt  reports\experiments\reversal_oos_chunk_runner_summary.txt
if errorlevel 1 goto FAIL

echo.
echo ========================================
echo OOS Chunk Runner Completed
echo ========================================
echo.
type reports\experiments\reversal_oos_chunk_runner_summary.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ========================================
echo ERROR OCCURRED
echo ========================================
echo 에러가 발생했습니다. 위쪽 메시지를 확인하세요.
pause
exit /b 1
