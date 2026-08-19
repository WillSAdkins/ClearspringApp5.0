@echo off
REM ============================================================
REM  Clearspring Church App - one-click launcher
REM
REM  Just double-click this file.
REM
REM  Your passwords and keys live in settings.bat, not here, so
REM  this file can be safely replaced with a newer version.
REM  Run setup.bat once first if you haven't already.
REM ============================================================

title Clearspring Church App
cd /d "%~dp0"

echo.
echo   Clearspring Church App
echo   ======================
echo.

REM ---- Is Python installed? ----
python --version >nul 2>&1
if errorlevel 1 goto :nopython
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [OK] %%v

REM ---- Are the packages installed? ----
python -c "import flask" >nul 2>&1
if errorlevel 1 goto :install
echo   [OK] Packages ready
goto :settings

:install
echo   [..] Installing packages, this may take a minute...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :nopackages
echo   [OK] Packages installed

:settings
if exist "settings.bat" goto :havesettings
echo   [!]  No settings.bat found.
echo        Run setup.bat once to create your own password.
echo        Starting with the default password "changeme" for now.
goto :start

:havesettings
call settings.bat
echo   [OK] Your settings loaded

:start
echo.
echo   Starting the app...
echo.
echo   Your browser will open in a moment.
echo   Keep this window open while using the app.
echo   Press Ctrl+C or close this window to stop.
echo.

REM Open the browser shortly after the server comes up
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:5000"

python app.py

echo.
echo   The app has stopped.
pause
exit /b 0

:nopython
echo   [X] Python is not installed, or not on your PATH.
echo.
echo   Download it from https://python.org/downloads
echo   IMPORTANT: tick "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:nopackages
echo.
echo   [X] Could not install the required packages.
echo       Check your internet connection and try again.
echo.
pause
exit /b 1
