@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Validating Top 10 Reversal Features...
python tools\validate_top10_reversal_features.py

if errorlevel 1 (
    echo.
    echo [Error] Validation failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\top10_reversal_feature_validation_latest.txt
echo ============================================================
pause
