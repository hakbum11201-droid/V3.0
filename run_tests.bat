@echo off
cd /d %~dp0
set PYTHONPATH=%cd%\src
python -m unittest discover -s tests
pause
