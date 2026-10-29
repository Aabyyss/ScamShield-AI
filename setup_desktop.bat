@echo off
title ScamShield AI - create desktop shortcut
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\create_shortcut.ps1"
if errorlevel 1 (
    echo.
    echo Could not create the shortcut. See the message above.
    pause
    exit /b 1
)

echo.
echo Done. Double-click "ScamShield AI" on your Desktop to open the app.
echo.
pause
