@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

:MENU
cls
echo ========================================
echo coinB PRO v3.0.1
echo Upbit KRW Orderflow Paper System
echo ========================================
echo.
echo [1] Basic Check
echo     - validate config
echo     - run tests
echo     - run backtest
echo     - generate report
echo.
echo [2] Run Orderflow Paper Cycle
echo     - collect Upbit WS data
echo     - build microstructure snapshot
echo     - run virtual buy/sell paper step
echo     - build learning dataset
echo.
echo [3] Run Tuner
echo     - create config candidate
echo     - auto apply disabled
echo.
echo [4] Collect Upbit WS only
echo.
echo [5] Build Microstructure only
echo.
echo [6] Run Orderflow Paper Step only
echo.
echo [7] Build Learning Dataset only
echo.
echo [8] Run Loss Analysis
echo     - analyze paper trades and rejection reasons
echo     - output reports/orderflow_loss_analysis.json
echo.
echo [0] Exit
echo.
echo ========================================
set /p choice=Select number: 

if "%choice%"=="1" goto BASIC_CHECK
if "%choice%"=="2" goto ORDERFLOW_CYCLE
if "%choice%"=="3" goto TUNER
if "%choice%"=="4" goto COLLECT_WS
if "%choice%"=="5" goto MICROSTRUCTURE
if "%choice%"=="6" goto ORDERFLOW_PAPER
if "%choice%"=="7" goto LEARNING_LOG
if "%choice%"=="8" goto LOSS_ANALYSIS
if "%choice%"=="0" goto END

echo.
echo Invalid selection.
pause
goto MENU

:BASIC_CHECK
cls
echo ========================================
echo [1/4] Validate config
echo ========================================
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto FAIL

echo.
echo ========================================
echo [2/4] Run tests
echo ========================================
python -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 goto FAIL

echo.
echo ========================================
echo [3/4] Run backtest
echo ========================================
python -m coinb.main backtest --config config/config.json --csv data/sample_ohlcv.csv
if errorlevel 1 goto FAIL

echo.
echo ========================================
echo [4/4] Generate report
echo ========================================
python -m coinb.main report --config config/config.json
if errorlevel 1 goto FAIL

echo.
echo [OK] Basic check completed.
pause
goto MENU

:ORDERFLOW_CYCLE
cls
echo ========================================
echo coinB Orderflow Paper Cycle
echo ========================================
echo This is PAPER ONLY. Live trading is disabled.
echo.

echo [1/5] Collect Upbit WS data
python -m coinb.main collect-ws --config config/config.json --seconds 30 --output logs/upbit_ws_events.jsonl
if errorlevel 1 goto FAIL

echo.
echo [2/5] Build microstructure snapshot
python -m coinb.main microstructure --micro-input logs/upbit_ws_events.jsonl --micro-output reports/microstructure_snapshot.json
if errorlevel 1 goto FAIL

echo.
echo [3/5] Run orderflow paper step
python -m coinb.main orderflow-paper ^
  --config config/config.json ^
  --micro-output reports/microstructure_snapshot.json ^
  --paper-state runtime/orderflow_paper_state.json ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl
if errorlevel 1 goto FAIL

echo.
echo [4/5] Build learning dataset
python -m coinb.main learning-log ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl ^
  --learning-output logs/orderflow_learning_dataset.jsonl ^
  --learning-summary reports/orderflow_learning_summary.json
if errorlevel 1 goto FAIL

echo.
echo [5/5] Run loss analysis
python -m coinb.main loss-analysis ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl ^
  --loss-output reports/orderflow_loss_analysis.json
if errorlevel 1 goto FAIL

echo.
echo [OK] Orderflow paper cycle completed.
echo.
echo Generated:
echo - logs/upbit_ws_events.jsonl
echo - reports/microstructure_snapshot.json
echo - runtime/orderflow_paper_state.json
echo - logs/orderflow_paper_decisions.jsonl
echo - logs/orderflow_paper_trades.jsonl
echo - logs/orderflow_learning_dataset.jsonl
echo - reports/orderflow_learning_summary.json
echo - reports/orderflow_loss_analysis.json
pause
goto MENU

:TUNER
cls
echo ========================================
echo Run tuner
echo ========================================
python -m coinb.main tune --config config/config.json --csv data/sample_ohlcv.csv
if errorlevel 1 goto FAIL
echo.
echo [OK] Tuner completed.
pause
goto MENU

:COLLECT_WS
cls
echo ========================================
echo Collect Upbit WS data
echo ========================================
python -m coinb.main collect-ws --config config/config.json --seconds 30 --output logs/upbit_ws_events.jsonl
if errorlevel 1 goto FAIL
echo.
echo [OK] Upbit WS collection completed.
pause
goto MENU

:MICROSTRUCTURE
cls
echo ========================================
echo Build microstructure snapshot
echo ========================================
python -m coinb.main microstructure --micro-input logs/upbit_ws_events.jsonl --micro-output reports/microstructure_snapshot.json
if errorlevel 1 goto FAIL
echo.
echo [OK] Microstructure snapshot generated.
pause
goto MENU

:ORDERFLOW_PAPER
cls
echo ========================================
echo Run orderflow paper step
echo ========================================
python -m coinb.main orderflow-paper ^
  --config config/config.json ^
  --micro-output reports/microstructure_snapshot.json ^
  --paper-state runtime/orderflow_paper_state.json ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl
if errorlevel 1 goto FAIL
echo.
echo [OK] Orderflow paper step completed.
pause
goto MENU

:LEARNING_LOG
cls
echo ========================================
echo Build learning dataset
echo ========================================
python -m coinb.main learning-log ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl ^
  --learning-output logs/orderflow_learning_dataset.jsonl ^
  --learning-summary reports/orderflow_learning_summary.json
if errorlevel 1 goto FAIL
echo.
echo [OK] Learning dataset generated.
pause
goto MENU

:LOSS_ANALYSIS
cls
echo ========================================
echo Run loss analysis
echo ========================================
python -m coinb.main loss-analysis ^
  --paper-decisions logs/orderflow_paper_decisions.jsonl ^
  --paper-trades logs/orderflow_paper_trades.jsonl ^
  --loss-output reports/orderflow_loss_analysis.json
if errorlevel 1 goto FAIL
echo.
echo [OK] Loss analysis completed.
echo Output: reports/orderflow_loss_analysis.json
pause
goto MENU

:FAIL
echo.
echo ========================================
echo [FAIL] Command failed.
echo ========================================
pause
goto MENU

:END
exit /b 0