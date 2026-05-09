@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo [STEP 0] Creating experiment directories...
if not exist "logs\experiments" mkdir "logs\experiments"
if not exist "reports\experiments" mkdir "reports\experiments"

set CONFIG=configs\experiments\config_conservative.json

echo [STEP 1] Validating experiment config...
python -m coinb.main validate-config --config %CONFIG%
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 2] Collecting WS events (30 min / 1800 sec)...
python -m coinb.main collect-ws --config %CONFIG% --seconds 1800 --output logs\experiments\conservative_ws_events.jsonl
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 3] Building microstructure...
python -m coinb.main microstructure --micro-input logs\experiments\conservative_ws_events.jsonl --micro-output reports\experiments\conservative_microstructure_snapshot.json
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 4] Running orderflow-paper step...
python -m coinb.main orderflow-paper --config %CONFIG% --micro-output reports\experiments\conservative_microstructure_snapshot.json --paper-decisions logs\experiments\conservative_decisions.jsonl --paper-trades logs\experiments\conservative_trades.jsonl
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 5] Building learning dataset...
python -m coinb.main learning-log --paper-decisions logs\experiments\conservative_decisions.jsonl --paper-trades logs\experiments\conservative_trades.jsonl --learning-output logs\experiments\conservative_learning_dataset.jsonl
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 6] Running loss analysis...
python -m coinb.main loss-analysis --paper-decisions logs\experiments\conservative_decisions.jsonl --paper-trades logs\experiments\conservative_trades.jsonl --loss-output reports\experiments\conservative_loss_analysis.json
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 7] Building paper review...
python -m coinb.main paper-review --loss-output reports\experiments\conservative_loss_analysis.json --review-output reports\experiments\conservative_paper_review.txt
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 8] Running paper performance...
python -m coinb.main paper-performance --config %CONFIG% --decisions logs\experiments\conservative_decisions.jsonl --trades logs\experiments\conservative_trades.jsonl --output-json reports\experiments\conservative_performance.json --equity-output logs\experiments\conservative_equity_curve.jsonl --summary-output reports\experiments\conservative_performance_summary.txt
if %ERRORLEVEL% NEQ 0 goto :error

echo [STEP 9] Running rejection diagnostics...
python -m coinb.main rejection-diagnostics --decisions logs\experiments\conservative_decisions.jsonl --output-json reports\experiments\conservative_rejection_diagnostics.json --output-txt reports\experiments\conservative_rejection_diagnostics_summary.txt
if %ERRORLEVEL% NEQ 0 goto :error

echo.
echo ============================================================
echo [RESULT] Rejection Diagnostics Summary:
type reports\experiments\conservative_rejection_diagnostics_summary.txt
echo.
echo ============================================================
echo [RESULT] Performance Summary:
type reports\experiments\conservative_performance_summary.txt
echo ============================================================
echo.
echo [OK] Experiment completed successfully.
pause
exit /b 0

:error
echo.
echo [ERROR] Experiment failed.
pause
exit /b 1
