@echo off
cd /d "%~dp0"
python tools\serve_lan.py %*
pause
