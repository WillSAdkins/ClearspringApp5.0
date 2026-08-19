@echo off
REM ============================================================
REM  Creates a folder that is safe to upload to GitHub.
REM
REM  It copies the app but leaves out your passwords, keys and
REM  church data - so nothing private can be uploaded by mistake.
REM ============================================================

title Prepare files for upload
cd /d "%~dp0"

echo.
echo   Preparing files for GitHub
echo   ==========================
echo.

set TARGET=%USERPROFILE%\Desktop\clearspring-upload

if exist "%TARGET%" rmdir /s /q "%TARGET%"
mkdir "%TARGET%"

echo   [..] Copying app files...

REM Copy everything, then exclude the private bits
xcopy /e /i /q /y "%~dp0*" "%TARGET%" >nul

REM Remove anything that must never leave this computer
if exist "%TARGET%\settings.bat"          del /q "%TARGET%\settings.bat"
if exist "%TARGET%\settings-previous.bat" del /q "%TARGET%\settings-previous.bat"
if exist "%TARGET%\church.db"             del /q "%TARGET%\church.db"
if exist "%TARGET%\secret_key"            del /q "%TARGET%\secret_key"
if exist "%TARGET%\__pycache__"           rmdir /s /q "%TARGET%\__pycache__"
if exist "%TARGET%\church-data"           rmdir /s /q "%TARGET%\church-data"
del /q "%TARGET%\*.migrated" >nul 2>&1
del /q "%TARGET%\*.before-restore-*" >nul 2>&1

echo   [OK] Done.
echo.
echo   ============================================
echo    A folder called "clearspring-upload" is now
echo    on your Desktop.
echo.
echo    Everything in it is safe to put on GitHub.
echo    Your password, keys and church data have
echo    all been left out.
echo   ============================================
echo.

REM Open it so it's ready to drag from
start "" "%TARGET%"

pause
