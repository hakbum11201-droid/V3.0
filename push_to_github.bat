@echo off
cd /d "%~dp0"
git add .
git commit -m "fix: add coinB PRO v3.0.1 corrected files"
git push
pause
