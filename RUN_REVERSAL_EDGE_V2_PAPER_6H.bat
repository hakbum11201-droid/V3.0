@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo [INFO] Starting Reversal Edge v2 Paper Runner (6H)

set CANDIDATE_PATH=configs\experiments\reversal_edge_candidate_v2_from_36h.json
set SECONDS=21600
set RUN_MODE=STATIC_SOL_ONLY
set EVENT_LOG=logs\paper\reversal_edge_v2_paper_events.jsonl
set TRADE_LOG=logs\paper\reversal_edge_v2_paper_trades.jsonl
set SUMMARY_JSON=reports\paper\reversal_edge_v2_paper_summary.json
set SUMMARY_TXT=reports\paper\reversal_edge_v2_paper_summary.txt

if not exist logs\paper mkdir logs\paper
if not exist reports\paper mkdir reports\paper

echo [STEP 1] Validating Config...
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto fail

echo [STEP 2] Running Reversal Edge Paper Runner for %SECONDS% seconds...
python -m coinb.main reversal-edge-paper-runner --candidate %CANDIDATE_PATH% --duration-sec %SECONDS% --mode %RUN_MODE% --output-events %EVENT_LOG% --output-trades %TRADE_LOG% --output-json %SUMMARY_JSON% --output-txt %SUMMARY_TXT%
if errorlevel 1 goto fail

echo [SUCCESS] Paper Runner Completed
echo.
type %SUMMARY_TXT%
echo.

pause
exit /b 0

:fail
echo [ERROR] Process failed at step.
pause
exit /b 1
