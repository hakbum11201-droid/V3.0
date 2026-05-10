@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo Starting 36H Combined Filter Diagnostic Runner...

set "WS_LOG=logs\experiments\combined_36h_ws_events.jsonl"
set "FACTOR_C=configs\experiments\market_factor_filter_candidate_v1.json"
set "FOCUS_C=configs\experiments\market_focus_filter_candidate_v1.json"
set "TREND_C=configs\experiments\short_term_trend_candidate_v1.json"

rem Create directories
if not exist logs\experiments mkdir logs\experiments
if not exist reports\experiments mkdir reports\experiments

rem Step 1: Validate Config
echo [Step 1] Validating configuration...
python -m coinb.main validate-config --config config/config.json
if errorlevel 1 goto fail

rem Step 2: Collect WS (36h = 129600s)
echo [Step 2] Collecting WS events for 36H (129600s)...
python -m coinb.main collect-ws --seconds 129600 --output %WS_LOG%
if errorlevel 1 goto fail

rem Step 3: Market Excursion Diagnostics
echo [Step 3] Running Market Excursion Diagnostics...
python -m coinb.main market-excursion-diagnostics --ws %WS_LOG% --output-json reports\experiments\combined_36h_market_excursion_diagnostics.json --output-txt reports\experiments\combined_36h_market_excursion_diagnostics_summary.txt
if errorlevel 1 goto fail

rem Step 4: Short-Term Trend Diagnostics
echo [Step 4] Running Short-Term Trend Diagnostics...
python -m coinb.main short-term-trend-diagnostics --ws %WS_LOG% --output-json reports\experiments\combined_36h_short_term_trend_diagnostics.json --output-txt reports\experiments\combined_36h_short_term_trend_diagnostics_summary.txt
if errorlevel 1 goto fail

rem Step 5: Market Factor Diagnostics
echo [Step 5] Running Market Factor Diagnostics...
python -m coinb.main market-factor-diagnostics --ws %WS_LOG% --output-json reports\experiments\combined_36h_market_factor_diagnostics.json --output-txt reports\experiments\combined_36h_market_factor_diagnostics_summary.txt
if errorlevel 1 goto fail

rem Step 6: Market Factor Filter Backtest
echo [Step 6] Running Market Factor Filter Backtest...
python -m coinb.main market-factor-filter-backtest --ws %WS_LOG% --market-filter %FACTOR_C% --trend-candidate %TREND_C% --output-json reports\experiments\combined_36h_market_factor_filter_backtest.json --output-txt reports\experiments\combined_36h_market_factor_filter_backtest_summary.txt
if errorlevel 1 goto fail

rem Step 7: Market Focus Diagnostics
echo [Step 7] Running Market Focus Diagnostics...
python -m coinb.main market-focus-diagnostics --backtest reports\experiments\combined_36h_market_factor_filter_backtest.json --output-json reports\experiments\combined_36h_market_focus_diagnostics.json --output-txt reports\experiments\combined_36h_market_focus_diagnostics_summary.txt
if errorlevel 1 goto fail

rem Step 8: Combined Filter Backtest
echo [Step 8] Running Combined Filter Backtest...
python -m coinb.main combined-filter-backtest --ws %WS_LOG% --market-factor %FACTOR_C% --market-focus %FOCUS_C% --trend-candidate %TREND_C% --output-json reports\experiments\combined_36h_combined_filter_backtest.json --output-txt reports\experiments\combined_36h_combined_filter_backtest_summary.txt
if errorlevel 1 goto fail

echo.
echo All diagnostics completed successfully.
echo.
type reports\experiments\combined_36h_combined_filter_backtest_summary.txt
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: Diagnostic failed at some step.
echo.
pause
exit /b 1
