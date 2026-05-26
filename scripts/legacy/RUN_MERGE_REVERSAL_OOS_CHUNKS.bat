@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ========================================
echo Reversal Edge v2 OOS Chunk Merge
echo ========================================

if not exist logs\experiments mkdir logs\experiments
if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Running OOS Chunk Merge Tool
python tools\merge_ws_chunks.py ^
  --input-dir logs\experiments\chunks ^
  --manifest logs\experiments\chunks\reversal_oos_chunk_manifest.jsonl ^
  --output logs\experiments\reversal_oos_chunks_merged.jsonl ^
  --summary-json reports\experiments\reversal_oos_chunk_merge_summary.json ^
  --summary-txt reports\experiments\reversal_oos_chunk_merge_summary.txt

if errorlevel 1 goto FAIL

echo.
echo ========================================
echo Merge Completed
echo ========================================
echo.
type reports\experiments\reversal_oos_chunk_merge_summary.txt
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
