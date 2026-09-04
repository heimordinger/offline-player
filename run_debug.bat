@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 调试启动 OfflinePlayer ...
if exist OfflinePlayer.exe (
    OfflinePlayer.exe
) else if exist release\offline-player\OfflinePlayer.exe (
    release\offline-player\OfflinePlayer.exe
) else (
    echo 找不到 OfflinePlayer.exe，请先运行 build_release.bat
)
echo.
echo 退出码: %ERRORLEVEL%
if exist startup_error.log type startup_error.log
pause
