@echo off
setlocal
cd /d "%~dp0"
cd ..

echo [INFO] Running Secret Guard...
python tools/secret_guard.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Secret Guard FAILED!
    echo Please check the output above and remove sensitive data.
    pause
    exit /b 1
) else (
    echo.
    echo [OK] Secret Guard Passed.
    pause
    exit /b 0
)
