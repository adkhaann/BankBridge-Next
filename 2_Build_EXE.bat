@echo off
title BankBridgeNext - Build EXE
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run 1_Setup.bat first.
    pause
    exit /b 1
)

echo Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install "pyinstaller==6.*"
if errorlevel 1 ( pause & exit /b 1 )

echo Building BankBridgeNext.exe...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean BankBridge.spec
if errorlevel 1 ( echo Build failed - see messages above. & pause & exit /b 1 )

set "BB_PACKAGE=dist\BankBridgeNext"
set "BB_EXE=%BB_PACKAGE%\BankBridgeNext.exe"
if not exist "%BB_EXE%" (
    echo Build output was not found at "%BB_EXE%". The desktop shortcut was not updated.
    pause
    exit /b 1
)

echo Pointing the BankBridgeNext desktop shortcut at the packaged application...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $target=(Resolve-Path -LiteralPath $env:BB_EXE).Path; $desktop=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'BankBridgeNext.lnk')); $s.TargetPath=$target; $s.Arguments=''; $s.WorkingDirectory=(Split-Path -Parent $target); $s.IconLocation=$target; $s.Description='BankBridgeNext'; $s.Save()"
if errorlevel 1 (
    echo The build succeeded, but the desktop shortcut could not be created. Open "%BB_EXE%" directly.
    pause
    exit /b 1
)

echo.
echo Done. Open the BankBridgeNext desktop shortcut or "%BB_EXE%".
echo To install on another PC, copy the whole "%BB_PACKAGE%" folder.
pause
