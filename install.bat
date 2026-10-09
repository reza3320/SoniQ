@echo off
title SoniQ Installer
cd /d "%~dp0"
set SONIQ_VER=unknown
if exist VERSION set /p SONIQ_VER=<VERSION
echo ============================================
echo    SoniQ — Installation
echo ============================================
echo.
echo This script will install everything needed
echo to run SoniQ on your computer.
echo.
echo    SoniQ v%SONIQ_VER%
if exist app.bat echo    Existing installation found — updating in place (settings, logs and downloads preserved).
echo ============================================
echo.

:: ──────────────────────────────────────────────
:: Step 1: Check Python
:: ──────────────────────────────────────────────
echo [1/5] Checking Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python is not installed.
    echo   Downloading Python 3.13...
    curl -o python-installer.exe https://www.python.org/ftp/python/3.13.2/python-3.13.2-amd64.exe
    echo   Running installer. IMPORTANT: Check "Add Python to PATH" and click Install Now.
    start /wait python-installer.exe
    del python-installer.exe
    echo   Python installation complete.
) else (
    python --version
    echo   Python is already installed.
)

echo.

:: ──────────────────────────────────────────────
:: Step 2: Check ffmpeg
:: ──────────────────────────────────────────────
echo [2/5] Checking ffmpeg...

where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo   ffmpeg is not installed. Installing via winget...
    winget install ffmpeg 2>nul
    if %errorlevel% neq 0 (
        echo   winget failed. Trying pip instead...
        pip install ffmpeg-python 2>nul
    )
    echo   ffmpeg installation complete.
) else (
    ffmpeg -version | findstr "ffmpeg"
    echo   ffmpeg is already installed.
)

echo.

:: ──────────────────────────────────────────────
:: Step 3: Install Python Dependencies
:: ──────────────────────────────────────────────
echo [3/5] Installing Python dependencies...

cd /d "%~dp0"
cd core

pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo   Retrying with --user flag...
    pip install --user -r requirements.txt
)

cd ..

echo   Dependencies installed.
echo.

:: ──────────────────────────────────────────────
:: Step 4: Check yt-dlp
:: ──────────────────────────────────────────────
echo [4/5] Checking converter tool...

where yt-dlp >nul 2>&1
if %errorlevel% neq 0 (
    echo   Not installed. Installing...
    winget install yt-dlp 2>nul
    if %errorlevel% neq 0 (
        pip install yt-dlp
    )
    echo   Installation complete.
) else (
    echo   Updating to the latest version ^(YouTube needs it^)...
    pip install -U yt-dlp >nul 2>&1
    yt-dlp --version
    echo   Converter tool is ready.
)

echo.

:: ──────────────────────────────────────────────
:: Step 5: Create app launcher + Start Menu entry
:: ──────────────────────────────────────────────
echo [5/5] Creating app launcher...

(
echo @echo off
echo title SoniQ
echo cd /d "%%~dp0"
echo wscript //nologo "%%~dp0tray.vbs"
echo python -B core\run.py %%*
echo if %%errorlevel%% neq 2 pause
) > app.bat

echo   app.bat created — you can now double-click it or use it from the command line.

:: Keep the installation clean: remove bytecode and old in-folder logs
for /d /r "%~dp0" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" >nul 2>&1
if exist "%~dp0logs" rd /s /q "%~dp0logs" >nul 2>&1

:: Start Menu shortcut with the app icon (non-fatal if PowerShell is blocked)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sm = [Environment]::GetFolderPath('Programs'); $lnk = $ws.CreateShortcut($sm + '\SoniQ.lnk'); $lnk.TargetPath = '%~dp0app.bat'; $lnk.WorkingDirectory = '%~dp0'; $lnk.IconLocation = '%~dp0core\assets\icon.ico'; $lnk.Description = 'SoniQ - Music Downloader'; $lnk.Save()" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Could not create the Start Menu shortcut ^(not critical^).
) else (
    echo   Start Menu shortcut created — search "SoniQ" in your Start Menu.
)

:: No separate "SoniQ Tray" Start Menu entry - the single "SoniQ" entry
:: launches the app and brings the tray up with it. Remove any older one.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sm = [Environment]::GetFolderPath('Programs'); Remove-Item ($sm + '\SoniQ Tray.lnk') -ErrorAction SilentlyContinue" >nul 2>&1

:: Verify the Start Menu shortcut landed
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sm = [Environment]::GetFolderPath('Programs'); if (Test-Path ($sm + '\SoniQ.lnk')) { Write-Host ('  Start Menu ready: ' + $sm) } else { Write-Host ('  WARNING: Start Menu shortcut missing in ' + $sm) }" 2>nul

:: Desktop shortcut ("SoniQ" with the app icon)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $dt = [Environment]::GetFolderPath('Desktop'); $lnk = $ws.CreateShortcut($dt + '\SoniQ.lnk'); $lnk.TargetPath = '%~dp0app.bat'; $lnk.WorkingDirectory = '%~dp0'; $lnk.IconLocation = '%~dp0core\assets\icon.ico'; $lnk.Description = 'SoniQ - music downloader'; $lnk.Save()" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Could not create the Desktop shortcut ^(not critical^).
) else (
    echo   Desktop shortcut created — "SoniQ" on your Desktop.
)
echo.

:: ──────────────────────────────────────────────
:: Done
:: ──────────────────────────────────────────────
echo ============================================
echo    INSTALLATION COMPLETE
echo ============================================
echo.
echo   What to do next:
echo.
echo   1. Double-click app.bat to start SoniQ
echo   2. Or find "SoniQ" in your Start Menu
echo   3. Taskbar quick downloads: open SoniQ - the tray icon comes up with it
echo   4. Or use it from the command line:
echo      app.bat download "Artist - Title"
echo      app.bat batch songs.json
echo.
echo   Tip: right-click the tray icon and pick "Start with Windows" to
echo   keep quick downloads always ready.
echo.
echo   All files are in the "core" folder.
echo   Configuration: ~\.soniq\config.json
echo.
pause
