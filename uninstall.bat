@echo off
title SoniQ Uninstaller
setlocal enabledelayedexpansion
cd /d "%~dp0"

set SCHED= 
set SONIQ_VER=?
if exist VERSION set /p SONIQ_VER=<VERSION

echo.
echo   SoniQ uninstaller (v%SONIQ_VER%)
echo   ------------------------------------------
echo.

:: 1. Start Menu shortcut, launcher, caches
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sm = [Environment]::GetFolderPath('Programs'); $st = [Environment]::GetFolderPath('Startup'); $dt = [Environment]::GetFolderPath('Desktop'); Remove-Item ($sm + '\SoniQ.lnk'), ($sm + '\SoniQ Tray.lnk'), ($st + '\SoniQ Tray.lnk'), ($dt + '\SoniQ.lnk') -ErrorAction SilentlyContinue" >nul 2>&1
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1
del /q app.bat >nul 2>&1
echo   Start Menu shortcut / launcher / caches removed.

:: 2. Settings (optional)
set /p REMOVE_CFG=  Also remove your settings (config + diagnostics)? [y/N]: 
if /i "%REMOVE_CFG%"=="y" (
    rmdir /s /q "%USERPROFILE%\.soniq" 2>nul
    echo   Settings removed.
) else (
    echo   Settings kept.
)

:: 3. Logs (optional)
set /p REMOVE_LOG=  Also remove the run logs? [y/N]: 
if /i "%REMOVE_LOG%"=="y" (
    rmdir /s /q logs 2>nul
    echo   Logs removed.
) else (
    echo   Logs kept.
)

echo.
echo   Done. To fully remove SoniQ, delete this folder:
echo       %~dp0
echo   Your downloaded songs were not touched.
echo.
pause
