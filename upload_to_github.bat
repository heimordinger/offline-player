@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "GH=%LOCALAPPDATA%\gh-portable\bin\gh.exe"
if not exist "%GH%" set "GH=gh"

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

"%GH%" repo view "%USERNAME%/离线播放器" >nul 2>&1
if errorlevel 1 (
    echo 创建仓库「离线播放器」...
    "%GH%" repo create "离线播放器" --public --source=. --remote=origin --description="离线 ADV 播放器"
    if errorlevel 1 (
        echo 创建失败，尝试手动添加远程后推送：
        echo   git remote add origin https://github.com/你的用户名/离线播放器.git
        pause
        exit /b 1
    )
) else (
    git remote get-url origin >nul 2>&1
    if errorlevel 1 git remote add origin https://github.com/%USERNAME%/离线播放器.git
    echo 推送到 origin/main ...
    git push -u origin main
)

echo.
echo 完成。仓库地址：
"%GH%" repo view --web 2>nul
pause
