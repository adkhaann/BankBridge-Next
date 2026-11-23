@echo off
title BankBridge - Diagnose
cd /d "%~dp0"
echo Starting BankBridge in diagnostic mode. Close the BankBridge window when done.
echo.
".venv\Scripts\python.exe" run_app.py
echo.
echo ---------- last lines of %LOCALAPPDATA%\BankBridgeNext\bankbridge.log ----------
powershell -NoProfile -Command "Get-Content -Tail 40 (Join-Path $env:LOCALAPPDATA 'BankBridgeNext\bankbridge.log')"
echo -----------------------------------------------------------------------------
echo Take a screenshot of this window if you need help.
pause
