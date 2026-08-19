@echo off
REM ============================================================
REM  Clearspring - why isn't the study assistant showing?
REM
REM  Just double-click this file. It loads your settings the
REM  same way run.bat does, then checks each step and tells
REM  you what to fix.
REM ============================================================

title Clearspring - AI check
cd /d "%~dp0"

if exist "settings.bat" (
  call settings.bat
) else (
  echo.
  echo   [!] No settings.bat found. Run setup.bat once first.
  echo.
)

python check_ai.py

echo.
pause
