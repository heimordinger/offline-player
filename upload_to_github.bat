@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "GIT_SAFE=-c safe.directory=%CD%"
set "REPO_NAME=offline-player"

set "GH=%LOCALAPPDATA%\gh-portable\bin\gh.exe"
if not exist "%GH%" set "GH=gh"
if not exist "C:\Program Files\GitHub CLI\gh.exe" (
    if not exist "%GH%" set "GH=gh"
) else (
    set "GH=C:\Program Files\GitHub CLI\gh.exe"
)

echo === 离线播放器 · 上传到 GitHub ===
echo.

"%GH%" auth status >nul 2>&1
if errorlevel 1 (
    echo 尚未登录 GitHub，将打开浏览器进行授权...
    "%GH%" auth login --hostname github.com --git-protocol https --web
    if errorlevel 1 (
        echo 登录失败。请确认网络/VPN 可用后重试。
        pause
        exit /b 1
    )
)

"%GH%" repo view "heimordinger/%REPO_NAME%" >nul 2>&1
if errorlevel 1 (
    echo 创建仓库 %REPO_NAME% ...
    "%GH%" repo create "%REPO_NAME%" --public --source=. --remote=origin --description="离线 ADV 播放器"
    if errorlevel 1 (
        echo 创建失败，尝试手动添加远程后推送：
        echo   git -c safe.directory=%%CD%% remote add origin https://github.com/heimordinger/%REPO_NAME%.git
        pause
        exit /b 1
    )
) else (
    git %GIT_SAFE% remote get-url origin >nul 2>&1
    if errorlevel 1 git %GIT_SAFE% remote add origin https://github.com/heimordinger/%REPO_NAME%.git
    echo 推送到 origin/main ...
    git %GIT_SAFE% push -u origin main
)

echo.
echo 完成。仓库地址：
"%GH%" repo view --web 2>nul
pause
