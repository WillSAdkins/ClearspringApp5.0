@echo off
REM ============================================================
REM  Clearspring - first-time setup
REM
REM  Run this ONCE. It creates settings.bat containing your own
REM  admin password and notification keys.
REM ============================================================

title Clearspring Setup
cd /d "%~dp0"

echo.
echo   Clearspring - first-time setup
echo   ==============================
echo.

python --version >nul 2>&1
if errorlevel 1 goto :nopython

if exist "settings.bat" goto :already

:dosetup
echo   [..] Installing required packages...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt >nul 2>&1

echo   [..] Generating your keys...
python make_settings.py
if errorlevel 1 goto :failed

echo.
echo   ============================================
echo    Setup complete.
echo.
echo    Your admin password is shown above and is
echo    saved in settings.bat. Write it down.
echo.
echo    Now double-click run.bat to start the app.
echo   ============================================
echo.
pause
exit /b 0

:already
echo   You already have a settings.bat file.
echo.
echo   Replacing it will CHANGE your admin password and sign
echo   everyone out of notifications.
echo.
set CONFIRM=
set /p CONFIRM="  Type YES to replace it, or just press Enter to cancel: "
if /i "%CONFIRM%"=="YES" goto :replace
echo.
echo   Cancelled. Nothing was changed.
echo.
pause
exit /b 0

:replace
copy /y settings.bat settings-previous.bat >nul
echo   [OK] Your old settings were saved as settings-previous.bat
goto :dosetup

:nopython
echo   [X] Python is not installed, or not on your PATH.
echo.
echo   Download it from https://python.org/downloads
echo   IMPORTANT: tick "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:failed
echo.
echo   [X] Setup failed. Check your internet connection and try again.
echo.
pause
exit /b 1
