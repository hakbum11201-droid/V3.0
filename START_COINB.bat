@echo off
cd /d "%~dp0"

:MENU
cls
echo ========================================
echo coinB PRO v3.0.1
echo Upbit KRW Paper Trading Framework
echo ========================================
echo.
echo [1] Run ALL CHECK
echo     - validate config
echo     - run tests
echo     - run backtest
echo     - generate report
echo.
echo [2] Run BACKTEST only
echo.
echo [3] Generate REPORT only
echo.
echo [4] Run TUNER only
echo     - create config candidate
echo     - auto apply disabled
echo.
echo [5] Validate CONFIG only
echo.
echo [6] Run TESTS only
echo.
echo [0] Exit
echo.
echo ========================================
set /p choice=Select number: 

if "%choice%"=="1" goto ALL_CHECK
if "%choice%"=="2" goto BACKTEST
if "%choice%"=="3" goto REPORT
if "%choice%"=="4" goto TUNER
if "%choice%"=="5" goto VALIDATE
if "%choice%"=="6" goto TESTS
if "%choice%"=="0" goto END

echo.
echo Invalid selection.
pause
goto MENU

:ALL_CHECK
cls
call "%~dp0run_all_check.bat"
goto MENU

:BACKTEST
cls
call "%~dp0run_backtest.bat"
goto MENU

:REPORT
cls
call "%~dp0run_report.bat"
goto MENU

:TUNER
cls
call "%~dp0run_tuner.bat"
goto MENU

:VALIDATE
cls
call "%~dp0run_validate_config.bat"
goto MENU

:TESTS
cls
call "%~dp0run_tests.bat"
goto MENU

:END
exit /b 0