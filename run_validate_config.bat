@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - validate config
echo ========================================

set PYTHONPATH=%CD%\src

python -m coinb.main validate-config --config config/config.json

if errorlevel 1 (
    echo.
    echo [FAIL] config validation failed.
    pause
    exit /b 1
)

echo.
echo [OK] config validation completed.
pause
exit /b 0