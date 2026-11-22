@echo off
title BankBridge - Build EXE
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run 1_Setup.bat first.
    pause
    exit /b 1
)

echo Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install "pyinstaller==6.*"
if errorlevel 1 ( pause & exit /b 1 )

echo Building BankBridge.exe - takes 2 to 5 minutes...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean BankBridge.spec
if errorlevel 1 ( echo Build failed - see messages above. & pause & exit /b 1 )

echo Pointing the desktop shortcut at the new BankBridge.exe...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\BankBridge.lnk'); $s.TargetPath='%~dp0dist\BankBridge\BankBridge.exe'; $s.Arguments=''; $s.WorkingDirectory='%~dp0dist\BankBridge'; $s.IconLocation='%~dp0dist\BankBridge\BankBridge.exe'; $s.Description='BankBridge'; $s.Save()"

echo.
echo Done. The app is in dist\BankBridge  -  open it from the desktop icon.
echo To install on another PC, copy the WHOLE dist\BankBridge folder.
pause
