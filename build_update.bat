@echo off
setlocal EnableExtensions
cd /d "%~dp0."

set "STAGE=release\offline-player-update"
set "ZIP=release\offline-player-update.zip"

if exist "%STAGE%" rmdir /s /q "%STAGE%"
if exist "%ZIP%" del /f /q "%ZIP%"
if not exist release mkdir release
mkdir "%STAGE%"

echo === OfflinePlayer Update Pack ===
echo (no OfflinePlayer.exe / runtime / _deps)

copy /Y VERSION "%STAGE%\" >nul
copy /Y run_app.py "%STAGE%\" >nul
copy /Y project_paths.py "%STAGE%\" >nul
copy /Y games.json "%STAGE%\" >nul
copy /Y settings.example.json "%STAGE%\" >nul
xcopy /E /I /Y /Q app "%STAGE%\app\" >nul
xcopy /E /I /Y /Q legacy\assets "%STAGE%\legacy\assets\" >nul
if exist assets\icon.ico if not exist "%STAGE%\assets" mkdir "%STAGE%\assets"
if exist assets\icon.ico copy /Y assets\icon.ico "%STAGE%\assets\" >nul

tar -a -cf "%ZIP%" -C release offline-player-update
if errorlevel 1 (
    echo Pack failed.
    pause
    exit /b 1
)

echo OK: %ZIP%
echo Extract over install. Keep OfflinePlayer.exe, runtime, _deps, data.
pause