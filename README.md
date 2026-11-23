# BankBridge 1.0 (desktop edition)

## Files
- app.py              YOUR converter code (keep editing this as before)
- build_engine.py     copies the parsers from app.py into engine.py (automatic)
- bankbridge_ui.py    the BankBridge screen (design, steps, exports)
- run_app.py          opens BankBridge in its own window
- assets\             app icon
- 1_Setup.bat         one-time install + desktop shortcut
- BankBridge.bat      start BankBridge without the shortcut
- 2_Build_EXE.bat     build dist\BankBridgeNext\BankBridgeNext.exe

## Try the Windows development build

1. Sign in to GitHub and open the latest successful [regression run for pdf-to-qbo](https://github.com/adkhaann/BankBridge-Next/actions/workflows/regression.yml?query=branch%3Apdf-to-qbo).
2. Under **Artifacts**, download **BankBridgeNext-Windows-x64**. Artifacts are available for 14 days.
3. Extract the entire ZIP into a folder and open `BankBridgeNext.exe`. Keep the companion files in the same folder.

This is an unsigned development build. GitHub checks that the packaged app starts its local server. The packaged Windows app has also converted the synthetic TD fixture in an interactive check. Shortcut and QuickBooks import testing still need an interactive Windows session.

### Verify a conversion

1. Select **TD Canada Trust** and **Business Chequing**.
2. Upload `samples/Synthetic-TD-Business-Chequing.pdf` from the extracted folder, then choose **Convert statement**.
3. Confirm that the app shows **Reconciled**, with three transactions. The two January 5 fees are $10.00 each and the January 8 receipt is $35.00.
4. Download the CSV. It should contain two `-10.0` amounts and one `35.0` amount. Use a test company if you try importing it into QuickBooks.

### Try a QuickBooks Desktop import

1. Select **RBC Royal Bank** and **Business Chequing**. Upload `samples/Synthetic-RBC-Business-Chequing.pdf` and convert it.
2. Check for **Reconciled**, one $10.00 debit and one $25.00 credit. Click **Download QBO**.
3. In a disposable QuickBooks Desktop test company, import the QBO using **File → Utilities → Import → Web Connect Files**. Check that the two transactions appear in the intended test account with the correct dates and amounts.
4. Import the same file again and check whether QuickBooks adds any duplicate rows. If QuickBooks rejects the file, record its exact error and version.

The RBC statement and account identifiers in this test are synthetic. Import acceptance and repeat-import behavior are pending verification.

## Adding a new bank later
1. Add the parser and its institution/account combination to DEDICATED_EXTRACTORS in app.py.
2. If it has its own QBO generator, add a branch to make_qbo() in app.py.
3. Re-run 2_Build_EXE.bat if you use the .exe.

## Problems
Log file: %LOCALAPPDATA%\BankBridgeNext\bankbridge.log
- Blank/white window: install "Microsoft Edge WebView2 Runtime" (free, from Microsoft).
- If the window can't be created, BankBridge falls back to opening in your browser.
