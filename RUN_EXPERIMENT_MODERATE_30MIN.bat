@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo [STEP 0] Creating experiment directories and initializing logs...
if not exist "logs\experiments" mkdir "logs\experiments"
if not exist "reports\experiments" mkdir "reports\experiments"

if exist "logs\experiments\moderate_ws_events.jsonl" del "logs\experiments\moderate_ws_events.jsonl"
if exist "logs\experiments\moderate_decisions.jsonl" del "logs\experiments\moderate_decisions.jsonl"
if exist "logs\experiments\moderate_trades.jsonl" del "logs\experiments\moderate_trades.jsonl"
if exist "logs\experiments\moderate_learning_dataset.jsonl" del "logs\experiments\moderate_learning_dataset.jsonl"
if exist "logs\experiments\moderate_equity_curve.jsonl" del "logs\experiments\moderate_equity_curve.jsonl"

set CONFIG=configs\experiments\config_moderate.json

echo [STEP 1] Validating experiment config...
python -m coinb.main validate-config --config %CONFIG%
if !ERRORLEVEL! NEQ 0 goto :error

echo [STEP 2] Running 30-minute experiment in 60 cycles...

for /L %%i in (1,1,60) do (
    echo.
    echo --- Cycle %%i / 60 ---
    
    echo [%%i/60] Collecting WS events - 30 sec
    python -m coinb.main collect-ws --config %CONFIG% --seconds 30 --output logs\experiments\moderate_ws_events_temp.jsonl
    if !ERRORLEVEL! NEQ 0 goto :error
    
    rem Append temp ws events to main ws log
    type logs\experiments\moderate_ws_events_temp.jsonl >> logs\experiments\moderate_ws_events.jsonl
    del logs\experiments\moderate_ws_events_temp.jsonl

    echo [%%i/60] Building microstructure...
    python -m coinb.main microstructure --micro-input logs\experiments\moderate_ws_events.jsonl --micro-output reports\experiments\moderate_microstructure_snapshot.json
    if !ERRORLEVEL! NEQ 0 goto :error

    echo [%%i/60] Running orderflow-paper step...
    python -m coinb.main orderflow-paper --config %CONFIG% --micro-output reports\experiments\moderate_microstructure_snapshot.json --paper-decisions logs\experiments\moderate_decisions.jsonl --paper-trades logs\experiments\moderate_trades.jsonl
    if !ERRORLEVEL! NEQ 0 goto :error

    echo [%%i/60] Building learning dataset...
    python -m coinb.main learning-log --paper-decisions logs\experiments\moderate_decisions.jsonl --paper-trades logs\experiments\moderate_trades.jsonl --learning-output logs\experiments\moderate_learning_dataset.jsonl
    if !ERRORLEVEL! NEQ 0 goto :error

    echo [%%i/60] Running loss analysis...
    python -m coinb.main loss-analysis --paper-decisions logs\experiments\moderate_decisions.jsonl --paper-trades logs\experiments\moderate_trades.jsonl --loss-output reports\experiments\moderate_loss_analysis.json
    if !ERRORLEVEL! NEQ 0 goto :error

    echo [%%i/60] Running paper performance...
    python -m coinb.main paper-performance --config %CONFIG% --decisions logs\experiments\moderate_decisions.jsonl --trades logs\experiments\moderate_trades.jsonl --output-json reports\experiments\moderate_performance.json --equity-output logs\experiments\moderate_equity_curve.jsonl --summary-output reports\experiments\moderate_performance_summary.txt
    if !ERRORLEVEL! NEQ 0 goto :error

    echo [%%i/60] Running rejection diagnostics...
    python -m coinb.main rejection-diagnostics --decisions logs\experiments\moderate_decisions.jsonl --output-json reports\experiments\moderate_rejection_diagnostics.json --output-txt reports\experiments\moderate_rejection_diagnostics_summary.txt
    if !ERRORLEVEL! NEQ 0 goto :error
)

echo.
echo ============================================================
echo [FINAL RESULT] Rejection Diagnostics Summary:
type reports\experiments\moderate_rejection_diagnostics_summary.txt
echo.
echo ============================================================
echo [FINAL RESULT] Performance Summary:
type reports\experiments\moderate_performance_summary.txt
echo ============================================================
echo.
echo [OK] 30-minute repeated experiment completed successfully.
pause
exit /b 0

:error
echo.
echo [ERROR] Experiment failed.
pause
exit /b 1
