@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo BankBridge is not set up yet. Run 1_Setup.bat first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0run_app.py"
