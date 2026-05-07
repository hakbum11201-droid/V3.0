@echo off
cd /d %~dp0
git status
git add .
git commit -m "release: add coinB pro v3.0 baseline"
git push
pause
