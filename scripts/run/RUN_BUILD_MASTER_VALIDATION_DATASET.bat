@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
set PYTHONPATH=%CD%\src

echo ======================================================
echo Master Dataset Builder
echo ======================================================

if not exist logs\experiments\master mkdir logs\experiments\master
if not exist reports\experiments mkdir reports\experiments

echo.
echo [STEP 1] Generating Master & Holdout Datasets...
python tools\build_master_validation_dataset.py
if errorlevel 1 goto FAIL

echo.
echo ======================================================
echo Dataset Built Successfully
echo ======================================================
echo.
type reports\experiments\master_dataset_builder_latest.txt
echo.
pause
exit /b 0

:FAIL
echo.
echo ======================================================
echo ERROR OCCURRED
echo ======================================================
echo Dataset 빌드 중 에러가 발생했습니다. 위쪽 로그를 확인하세요.
pause
exit /b 1
