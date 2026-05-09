@echo off
setlocal enabledelayedexpansion

rem Orderflow Soft Score One Hour Net Edge Diagnostic Runner
rem Strictly ASCII version for Windows CMD compatibility

chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONPATH=%CD%\src"

echo STARTING SOFT SCORE ONE HOUR DIAGNOSTIC...
echo ANALYSIS DURATION 3600 SECONDS
echo CONFIG PATH configs/experiments/config_moderate.json
echo CANDIDATE PATH configs/experiments/soft_score_candidate_v1.json

rem Create directories
if not exist "logs\experiments" mkdir "logs\experiments"
if not exist "reports\experiments" mkdir "reports\experiments"

rem Define paths
set "CONFIG_PATH=configs\experiments\config_moderate.json"
set "CANDIDATE_PATH=configs\experiments\soft_score_candidate_v1.json"
set "WS_LOG=logs\experiments\soft_score_1h_ws_events.jsonl"
set "OPP_JSON=reports\experiments\soft_score_1h_opportunity_diagnostics.json"
set "OPP_TXT=reports\experiments\soft_score_1h_opportunity_diagnostics_summary.txt"
set "BT_JSON=reports\experiments\soft_score_1h_backtest.json"
set "BT_TXT=reports\experiments\soft_score_1h_backtest_summary.txt"
set "SIM_JSON=reports\experiments\soft_score_1h_net_edge_sim.json"
set "SIM_TXT=reports\experiments\soft_score_1h_net_edge_sim_summary.txt"
set "DIAG_JSON=reports\experiments\soft_score_1h_net_edge_candidate_diagnostics.json"
set "DIAG_TXT=reports\experiments\soft_score_1h_net_edge_candidate_diagnostics_summary.txt"

rem Cleanup existing files
if exist "%WS_LOG%" del "%WS_LOG%"
if exist "%OPP_JSON%" del "%OPP_JSON%"
if exist "%BT_JSON%" del "%BT_JSON%"
if exist "%SIM_JSON%" del "%SIM_JSON%"
if exist "%DIAG_JSON%" del "%DIAG_JSON%"

echo STEP 1 VALIDATING CONFIG...
python -m coinb.main validate-config --config %CONFIG_PATH%
if errorlevel 1 goto fail

echo STEP 2 COLLECTING WS EVENTS FOR 3600 SECONDS...
python -m coinb.main collect-ws --config %CONFIG_PATH% --seconds 3600 --output "%WS_LOG%"
if errorlevel 1 goto fail

echo STEP 3 RUNNING OPPORTUNITY DIAGNOSTICS...
python -m coinb.main opportunity-diagnostics --ws "%WS_LOG%" --config %CONFIG_PATH% --output-json "%OPP_JSON%" --output-txt "%OPP_TXT%"
if errorlevel 1 goto fail

echo STEP 4 RUNNING SOFT SCORE BACKTEST...
python -m coinb.main soft-score-backtest --opportunity "%OPP_JSON%" --candidate %CANDIDATE_PATH% --output-json "%BT_JSON%" --output-txt "%BT_TXT%"
if errorlevel 1 goto fail

echo STEP 5 RUNNING NET EDGE SIMULATION...
python -m coinb.main soft-score-net-edge-sim --opportunity "%OPP_JSON%" --backtest "%BT_JSON%" --candidate %CANDIDATE_PATH% --ws "%WS_LOG%" --output-json "%SIM_JSON%" --output-txt "%SIM_TXT%"
if errorlevel 1 goto fail

echo STEP 6 RUNNING NET EDGE CANDIDATE DIAGNOSTICS...
python -m coinb.main net-edge-candidate-diagnostics --opportunity "%OPP_JSON%" --backtest "%BT_JSON%" --net-edge-sim "%SIM_JSON%" --ws "%WS_LOG%" --output-json "%DIAG_JSON%" --output-txt "%DIAG_TXT%"
if errorlevel 1 goto fail

echo ALL STEPS COMPLETED SUCCESSFULLY.
echo DISPLAYING SUMMARIES...
echo ----------------------------------------
type "%OPP_TXT%"
echo ----------------------------------------
type "%BT_TXT%"
echo ----------------------------------------
type "%SIM_TXT%"
echo ----------------------------------------
type "%DIAG_TXT%"
echo ----------------------------------------

echo DIAGNOSTIC FINISHED.
pause
exit /b 0

:fail
echo ERROR OCCURRED DURING DIAGNOSTIC STEPS.
pause
exit /b 1
