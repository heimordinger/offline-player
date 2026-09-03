@echo off
cd /d "%~dp0\.."
py -3.13 legacy\do_main.py 2>nul
if not errorlevel 1 goto :done
python legacy\do_main.py 2>nul
if not errorlevel 1 goto :done
echo 无法启动 legacy 版，请确认已安装 Python 3.13 与 pygame。
pause
:done
