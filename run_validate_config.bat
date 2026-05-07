@echo off
cd /d %~dp0
set PYTHONPATH=%cd%\src
python -m coinb.main validate-config
pause
