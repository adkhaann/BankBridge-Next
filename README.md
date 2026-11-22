# BankBridge 1.0 (desktop edition)

## Files
- app.py              YOUR converter code (keep editing this as before)
- build_engine.py     copies the parsers from app.py into engine.py (automatic)
- bankbridge_ui.py    the BankBridge screen (design, steps, exports)
- run_app.py          opens BankBridge in its own window
- assets\             app icon
- 1_Setup.bat         one-time install + desktop shortcut
- BankBridge.bat      start BankBridge without the shortcut
- 2_Build_EXE.bat     build dist\BankBridge\BankBridge.exe

## Adding a new bank later
1. Add the parser to app.py and the combination to SUPPORTED_COMBINATIONS (as before).
2. In bankbridge_ui.py add one line to EXTRACTORS, and (if it has its own QBO
   generator) a branch in make_qbo().
3. Re-run 2_Build_EXE.bat if you use the .exe.

## Problems
Log file: %LOCALAPPDATA%\BankBridge\bankbridge.log
- Blank/white window: install "Microsoft Edge WebView2 Runtime" (free, from Microsoft).
- If the window can't be created, BankBridge falls back to opening in your browser.
