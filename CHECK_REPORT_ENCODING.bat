@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo Checking and fixing report encoding (UTF-8-SIG for Windows)...

python tools/check_report_encoding.py --root reports --fix

echo.
echo Encoding check completed.
echo.
pause
