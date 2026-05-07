@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - generate report
echo ========================================

set PYTHONPATH=%CD%\src

python -m coinb.main report --config config/config.json

if errorlevel 1 (
    echo.
    echo [FAIL] report generation failed.
    pause
    exit /b 1
)

echo.
echo [OK] report generated.
pause
exit /b 0