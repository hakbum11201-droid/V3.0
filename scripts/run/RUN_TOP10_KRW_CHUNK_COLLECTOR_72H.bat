@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Starting Top 10 KRW Market Chunk Collector for 72h...
python tools\run_top10_krw_chunk_collector.py --duration-sec 259200 --chunk-sec 1800 --output-dir logs/experiments/top10_krw_72h_chunks

if errorlevel 1 (
    echo.
    echo [Error] Data collection failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\top10_krw_chunk_collector_summary.txt
echo ============================================================
pause
