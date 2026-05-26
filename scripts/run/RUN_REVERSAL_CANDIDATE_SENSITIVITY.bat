@echo off
cd /d "%~dp0..\.."
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [Info] Starting Reversal Edge v2 Candidate Sensitivity Analysis...
echo.

python tools\run_reversal_candidate_sensitivity.py

if errorlevel 1 (
    echo.
    echo [Error] Analysis failed. See output above.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Final Report
echo ============================================================
type reports\experiments\reversal_candidate_sensitivity_latest.txt
echo ============================================================
pause
