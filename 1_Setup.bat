@echo off
title BankBridge - One-time Setup
cd /d "%~dp0"

echo ============================================
echo   BankBridge - One-time Setup
echo ============================================
echo.

if not exist "app.py" (
    echo ERROR: app.py was not found in this folder.
    echo Copy your converter code into this folder and name it app.py
    pause
    exit /b 1
)

py -3.12 --version >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3.12"
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python is not installed or not on PATH.
        echo Install Python 3.12 from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" on the first installer screen.
        pause
        exit /b 1
    )
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 ( echo Failed to create virtual environment. & pause & exit /b 1 )
)

echo Installing packages - this can take a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip uninstall -y fitz frontend >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Package installation failed. & pause & exit /b 1 )

echo Preparing the BankBridge engine from app.py...
".venv\Scripts\python.exe" build_engine.py
if errorlevel 1 ( echo app.py has an error - see the message above. & pause & exit /b 1 )

echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\BankBridge.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0run_app.py\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\bankbridge.ico'; $s.Description='BankBridge'; $s.Save()"

echo.
echo Setup complete. Open BankBridge from the new icon on your desktop.
pause
