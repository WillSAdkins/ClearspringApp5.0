@echo off
REM ============================================================
REM  Clearspring - build the Android app
REM
REM  Double-click this. It installs what's needed, creates the
REM  Android project, and opens Android Studio.
REM
REM  You need first:
REM    - Node.js         https://nodejs.org  (the LTS button)
REM    - Android Studio  https://developer.android.com/studio
REM ============================================================

title Clearspring - Android build
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [X] Node.js isn't installed.
  echo       Get it from https://nodejs.org - choose the LTS version,
  echo       then run this again.
  echo.
  pause
  exit /b 1
)

echo.
echo   Installing dependencies. First run takes a few minutes...
echo.
call npm install
if errorlevel 1 goto failed

if not exist "android" (
  echo.
  echo   Creating the Android project...
  call npx cap add android
  if errorlevel 1 goto failed
)

echo.
echo   Syncing...
call npx cap sync android
if errorlevel 1 goto failed

echo.
echo   Opening Android Studio. Press the green Run button there to
echo   put the app on a phone or emulator.
echo.
call npx cap open android
goto done

:failed
echo.
echo   [X] Something failed above. The message usually says what.
echo.

:done
pause
