@echo off
cd /d "%~dp0"
REM 新版 PySide6 客户端（共用根目录 json / resource / settings.json）
py -3.13 run_app.py 2>nul
if not errorlevel 1 goto :done
python run_app.py 2>nul
if not errorlevel 1 goto :done
echo PySide6 启动失败，尝试 legacy 版 (pygame) ...
call legacy\start.bat
:done
