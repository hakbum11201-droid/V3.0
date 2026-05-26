@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Starting Master Dataset Cache Build...
python tools\build_master_dataset_cache.py --rebuild

if errorlevel 1 (
    echo [Error] Cache build failed.
    pause
    exit /b %errorlevel%
)

echo.
echo [Info] Build completed. Showing summary:
echo ------------------------------------------------------------
type reports\experiments\master_dataset_cache_latest.txt
echo ------------------------------------------------------------
pause
