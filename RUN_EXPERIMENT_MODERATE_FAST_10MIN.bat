@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo [STEP 0] Creating experiment directories and initializing logs...
if not exist "logs\experiments" mkdir "logs\experiments"
if not exist "reports\experiments" mkdir "reports\experiments"

if exist "logs\experiments\moderate_fast_ws_events.jsonl" del "logs\experiments\moderate_fast_ws_events.jsonl"
if exist "logs\experiments\moderate_fast_decisions.jsonl" del "logs\experiments\moderate_fast_decisions.jsonl"
if exist "logs\experiments\moderate_fast_trades.jsonl" del "logs\experiments\moderate_fast_trades.jsonl"
if exist "logs\experiments\moderate_fast_learning_dataset.jsonl" del "logs\experiments\moderate_fast_learning_dataset.jsonl"
if exist "logs\experiments\moderate_fast_equity_curve.jsonl" del "logs\experiments\moderate_fast_equity_curve.jsonl"

set CONFIG=configs\experiments\config_moderate.json

echo [STEP 1] Validating experiment config...
python -m coinb.main validate-config --config %CONFIG%
if !ERRORLEVEL! NEQ 0 goto :error

echo [STEP 1.5] Warming up - 30s data collection...
python -m coinb.main collect-ws --config %CONFIG% --seconds 30 --output logs\experiments\moderate_fast_ws_events.jsonl
if !ERRORLEVEL! NEQ 0 goto :error

echo [STEP 2] Running 10-minute fast experiment in 120 cycles (5s each)...

for /L %%i in (1,1,120) do (
    echo.
    echo --- Cycle %%i / 120 ---
    
    echo [%%i/120] Collecting WS events - 5 sec
    python -m coinb.main collect-ws --config %CONFIG% --seconds 5 --output logs\experiments\moderate_fast_ws_events_temp.jsonl
    if !ERRORLEVEL! NEQ 0 goto :error
    
    rem Append temp ws events to main ws log
    type logs\experiments\moderate_fast_ws_events_temp.jsonl >> logs\experiments\moderate_fast_ws_events.jsonl
    del logs\experiments\moderate_fast_ws_events_temp.jsonl

    echo [%%i/120] Building microstructure...
    python -m coinb.main microstructure --micro-input logs\experiments\moderate_fast_ws_events.jsonl --micro-output reports\experiments\moderate_fast_microstructure_snapshot.json
    if !ERRORLEVEL! NEQ 0 goto :error

    rem Check if microstructure is empty
    python -c "import json, sys; d=json.load(open('reports/experiments/moderate_fast_microstructure_snapshot.json')); sys.exit(0 if d.get('market_count', 0) > 0 else 1)"
    if !ERRORLEVEL! NEQ 0 (
        echo [%%i/120] SKIP - no market features yet
    ) else (
        echo [%%i/120] Running orderflow-paper step...
        python -m coinb.main orderflow-paper --config %CONFIG% --micro-output reports\experiments\moderate_fast_microstructure_snapshot.json --paper-decisions logs\experiments\moderate_fast_decisions.jsonl --paper-trades logs\experiments\moderate_fast_trades.jsonl
        if !ERRORLEVEL! NEQ 0 goto :error

        echo [%%i/120] Building learning dataset...
        python -m coinb.main learning-log --paper-decisions logs\experiments\moderate_fast_decisions.jsonl --paper-trades logs\experiments\moderate_fast_trades.jsonl --learning-output logs\experiments\moderate_fast_learning_dataset.jsonl
        if !ERRORLEVEL! NEQ 0 goto :error

        echo [%%i/120] Running loss analysis...
        python -m coinb.main loss-analysis --paper-decisions logs\experiments\moderate_fast_decisions.jsonl --paper-trades logs\experiments\moderate_fast_trades.jsonl --loss-output reports\experiments\moderate_fast_loss_analysis.json
        if !ERRORLEVEL! NEQ 0 goto :error

        echo [%%i/120] Running paper performance...
        python -m coinb.main paper-performance --config %CONFIG% --decisions logs\experiments\moderate_fast_decisions.jsonl --trades logs\experiments\moderate_fast_trades.jsonl --output-json reports\experiments\moderate_fast_performance.json --equity-output logs\experiments\moderate_fast_equity_curve.jsonl --summary-output reports\experiments\moderate_fast_performance_summary.txt
        if !ERRORLEVEL! NEQ 0 goto :error

        echo [%%i/120] Running rejection diagnostics...
        python -m coinb.main rejection-diagnostics --decisions logs\experiments\moderate_fast_decisions.jsonl --output-json reports\experiments\moderate_fast_rejection_diagnostics.json --output-txt reports\experiments\moderate_fast_rejection_diagnostics_summary.txt
        if !ERRORLEVEL! NEQ 0 goto :error
    )
)

echo.
echo [STEP 3] Running opportunity diagnostics for the whole experiment...
python -m coinb.main opportunity-diagnostics --ws logs\experiments\moderate_fast_ws_events.jsonl --config %CONFIG% --output-json reports\experiments\moderate_fast_opportunity_diagnostics.json --output-txt reports\experiments\moderate_fast_opportunity_diagnostics_summary.txt
if !ERRORLEVEL! NEQ 0 goto :error

echo.
echo ============================================================
echo [FINAL RESULT] Rejection Diagnostics Summary:
if exist reports\experiments\moderate_fast_rejection_diagnostics_summary.txt type reports\experiments\moderate_fast_rejection_diagnostics_summary.txt
echo.
echo ============================================================
echo [FINAL RESULT] Performance Summary:
if exist reports\experiments\moderate_fast_performance_summary.txt type reports\experiments\moderate_fast_performance_summary.txt
echo.
echo ============================================================
echo [FINAL RESULT] Opportunity Diagnostics Summary:
if exist reports\experiments\moderate_fast_opportunity_diagnostics_summary.txt type reports\experiments\moderate_fast_opportunity_diagnostics_summary.txt
echo ============================================================
echo.
echo [OK] 10-minute fast repeated experiment completed successfully.
pause
exit /b 0

:error
echo.
echo [ERROR] Experiment failed.
pause
exit /b 1
