@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-BankBridgeNext.ps1"
set "BANKBRIDGE_UPDATE_STATUS=%ERRORLEVEL%"
pause
exit /b %BANKBRIDGE_UPDATE_STATUS%
