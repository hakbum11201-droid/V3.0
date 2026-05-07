@echo off
cd /d "%~dp0"

echo ========================================
echo coinB PRO - run tests
echo ========================================

set PYTHONPATH=%CD%\src

python -m unittest discover -s tests -p "test_*.py"

if errorlevel 1 (
    echo.
    echo [FAIL] tests failed.
    pause
    exit /b 1
)

echo.
echo [OK] tests passed.
pause
exit /b 0