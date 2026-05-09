@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo V3.0 PAPER LOOP 1H
echo 30sec collect + paper decision loop
echo ========================================

set PYTHONPATH=%CD%\src

if not exist logs mkdir logs
if not exist reports mkdir reports
if not exist runtime mkdir runtime

echo.
echo [CHECK] validate-config
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto ERROR

set COUNT=0
set MAX=120

:LOOP
set /a COUNT+=1

echo.
echo ========================================
echo LOOP %COUNT% / %MAX%
echo ========================================

echo [1/3] collect-ws 30 seconds
python -m coinb.main collect-ws --config config/config.json --seconds 30 --output logs/upbit_ws_events_recent.jsonl
if errorlevel 1 goto ERROR

echo [2/3] microstructure
python -m coinb.main microstructure --micro-input logs/upbit_ws_events_recent.jsonl --micro-output reports/microstructure_snapshot.json
if errorlevel 1 goto ERROR

echo [3/3] orderflow-paper
python -m coinb.main orderflow-paper --config config/config.json --micro-output reports/microstructure_snapshot.json --paper-state runtime/orderflow_paper_state.json --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl
if errorlevel 1 goto ERROR

if %COUNT% LSS %MAX% goto LOOP

echo.
echo ========================================
echo FINAL learning-log
echo ========================================
python -m coinb.main learning-log --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --learning-output logs/orderflow_learning_dataset.jsonl --learning-summary reports/orderflow_learning_summary.json
if errorlevel 1 goto ERROR

echo.
echo ========================================
echo FINAL loss-analysis
echo ========================================
python -m coinb.main loss-analysis --paper-decisions logs/orderflow_paper_decisions.jsonl --paper-trades logs/orderflow_paper_trades.jsonl --loss-output reports/orderflow_loss_analysis.json
if errorlevel 1 goto ERROR

echo.
echo ========================================
echo FINAL paper-review
echo ========================================
python -m coinb.main paper-review --loss-output reports/orderflow_loss_analysis.json --review-output reports/paper_review_latest.txt
if errorlevel 1 goto ERROR

echo.
echo ========================================
echo PAPER LOOP COMPLETE
echo ========================================

echo.
echo [ REVIEW SUMMARY ]
type reports\paper_review_latest.txt

echo.
echo logs:
dir logs

echo.
echo reports:
dir reports

pause
exit /b 0

:ERROR
echo.
echo ========================================
echo ERROR OCCURRED
echo ========================================
echo 에러가 발생했습니다. 위쪽 에러 메시지를 복사해서 보내세요.
pause
exit /b 1