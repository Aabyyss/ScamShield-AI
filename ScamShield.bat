@echo off
title ScamShield AI
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=py"

"%PY%" launcher.py %*
if errorlevel 1 (
    echo.
    echo ScamShield could not start. Details are in data\launcher.log
    echo.
    pause
)
