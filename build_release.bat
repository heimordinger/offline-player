@echo off
setlocal EnableExtensions
cd /d "%~dp0."
if not exist build_release.py goto badcwd

set "PY=python"
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3.13"

echo === OfflinePlayer Release Build ===
echo Python: %PY%
echo.

tasklist /FI "IMAGENAME eq OfflinePlayer.exe" 2>nul | find /I "OfflinePlayer.exe" >nul
if not errorlevel 1 (
    echo Please close OfflinePlayer.exe first
    pause
    exit /b 1
)

%PY% build_release.py
if errorlevel 1 (
    echo.
    echo FAILED - see release\build_release.log
    pause
    exit /b 1
)

echo.
pause
exit /b 0

:badcwd
echo ERROR: run this bat from project root
pause
exit /b 1