@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo [INFO] Starting Reversal Edge v2 OOS 72H Validation

set WS_LOG_PATH=logs\experiments\reversal_oos_72h_ws_events.jsonl
set DIAG_JSON_PATH=reports\experiments\reversal_oos_72h_reversal_edge_diagnostics.json
set DIAG_TXT_PATH=reports\experiments\reversal_oos_72h_reversal_edge_diagnostics_summary.txt
set BT_JSON_PATH=reports\experiments\reversal_oos_72h_reversal_edge_backtest_v2.json
set BT_TXT_PATH=reports\experiments\reversal_oos_72h_reversal_edge_backtest_v2_summary.txt
set CANDIDATE_PATH=configs\experiments\reversal_edge_candidate_v2_from_36h.json
set SECONDS=259200

if not exist logs\experiments mkdir logs\experiments
if not exist reports\experiments mkdir reports\experiments

if exist %WS_LOG_PATH% del /Q %WS_LOG_PATH%
if exist %DIAG_JSON_PATH% del /Q %DIAG_JSON_PATH%
if exist %DIAG_TXT_PATH% del /Q %DIAG_TXT_PATH%
if exist %BT_JSON_PATH% del /Q %BT_JSON_PATH%
if exist %BT_TXT_PATH% del /Q %BT_TXT_PATH%

echo [STEP 1] Validating Config...
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto fail

echo [STEP 2] Collecting WS Logs for %SECONDS% seconds...
python -m coinb.main collect-ws --seconds %SECONDS% --output %WS_LOG_PATH%
if errorlevel 1 goto fail

echo [STEP 3] Running Reversal Edge Diagnostics...
python -m coinb.main reversal-edge-diagnostics --ws %WS_LOG_PATH% --output-json %DIAG_JSON_PATH% --output-txt %DIAG_TXT_PATH%
if errorlevel 1 goto fail

echo [STEP 4] Running Reversal Edge Backtest...
python -m coinb.main reversal-edge-backtest --ws %WS_LOG_PATH% --candidate %CANDIDATE_PATH% --output-json %BT_JSON_PATH% --output-txt %BT_TXT_PATH%
if errorlevel 1 goto fail

echo [SUCCESS] OOS 72H Validation Completed
echo.
echo --- Diagnostics Summary ---
type %DIAG_TXT_PATH%
echo.
echo --- Backtest Summary ---
type %BT_TXT_PATH%
echo.

pause
exit /b 0

:fail
echo [ERROR] Process failed at step.
pause
exit /b 1
