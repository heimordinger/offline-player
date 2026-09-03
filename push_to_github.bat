@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "GIT_SAFE=-c safe.directory=%CD%"
set "REPO_NAME=offline-player"

echo === 离线播放器 · 推送到 GitHub ===
echo.
echo 远程仓库: heimordinger/%REPO_NAME%
echo.

git %GIT_SAFE% remote get-url origin >nul 2>&1
if errorlevel 1 (
    git %GIT_SAFE% remote add origin https://github.com/heimordinger/%REPO_NAME%.git
) else (
    git %GIT_SAFE% remote set-url origin https://github.com/heimordinger/%REPO_NAME%.git
)

echo 推送到 origin/main ...
git %GIT_SAFE% push -u origin main
if errorlevel 1 (
    echo.
    echo 推送失败。请确认 GitHub 上已有仓库 heimordinger/%REPO_NAME%
    pause
    exit /b 1
)

echo.
echo 完成: https://github.com/heimordinger/%REPO_NAME%
pause
