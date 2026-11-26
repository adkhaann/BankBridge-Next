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

This is an unsigned development build. GitHub runs a Windows browser test that checks the TD CSV and RBC QBO downloads, stable IDs on repeat download, and that a reconciliation mismatch blocks both exports. The packaged Windows app has also converted the synthetic TD fixture in an interactive check. The synthetic RBC QBO repeat-import check in QuickBooks Desktop and the synthetic TD CSV import check in QuickBooks Online also passed, as confirmed by the user.

### Update the portable Windows build

The portable package includes `Update-BankBridgeNext.cmd` and `Update-BankBridgeNext.ps1`. Keep both beside `BankBridgeNext.exe`. If you already have a portable build, you can copy just those two updater files into its folder.

1. Install [GitHub CLI](https://cli.github.com/) and run `gh auth login` once. Choose GitHub.com and follow the sign-in prompts.
2. Close BankBridgeNext and double-click `Update-BankBridgeNext.cmd`. The updater downloads the latest passing Windows build from the development branch and replaces only the application files. Your desktop shortcut keeps its existing target.
3. Open BankBridgeNext using the same shortcut. The header shows the seven-character build ID from the installed package. If you need to undo a successful update, close the app and restore `BankBridgeNext.exe`, `_internal`, and `BankBridgeNext.build` from the single `.bankbridge-previous` folder inside the app folder. Each successful update replaces that rollback copy. Move the current copies aside before restoring.

The updater is for the extracted portable app. A source checkout continues to update through Git.

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

The RBC statement and account identifiers in this test are synthetic. The user confirmed the test import and repeat-import check passed.

### First release coverage

The desktop conversion and export checks use synthetic PDFs. They cover the statement layouts listed here.

| Institution | QuickBooks Online CSV | QuickBooks Desktop QBO generation |
| --- | --- | --- |
| TD Canada Trust | Business Chequing, Credit Card | Credit Card with full printed card number and closing balance |
| RBC Royal Bank | Business Chequing, Mastercard | Business Chequing with printed transit, account and closing balance. Mastercard requires full printed card number and closing balance. |
| BMO Bank of Montreal | Business Chequing, Mastercard | Mastercard with full printed card number and closing balance |
| Scotiabank | Business Chequing | Requires a confirmed Web Connect mapping |
| CIBC | Chequing, Savings, Visa | Chequing and Savings with the printed CIBC account and transit format. Visa requires full printed card number and closing balance. |

The user confirmed the synthetic RBC Business Chequing QBO imported into QuickBooks Desktop and the repeat import offered no duplicate transactions. The user also confirmed the synthetic TD Business Chequing CSV import in QuickBooks Online. The other entries describe automated conversion and file generation. Production statement layouts and account mappings require their own verification. Simplii is deferred from this release scope.

For a QuickBooks Online import check, use a test company, upload a CSV through **Bank transactions → Upload from file**, and map **Date**, **Description**, and **Amount**. Choose the day/month/year date format. The synthetic TD sample should show two $10.00 payments and one $35.00 deposit.

### Convert a TD EasyWeb activity printout

Choose **TD Canada Trust → Business Chequing** and use the dedicated parser. The activity printout must include the displayed date range, the withdrawals and deposits table with running balances, and the printed totals. Reconciled activity exports to CSV.

### Export bank or credit card transactions to QuickBooks Desktop IIF

The **QuickBooks Desktop IIF** option is available for reconciled CAD deposit and credit card statements from any bank or issuer the app can read, including experimental layouts. Enter the full name of the existing bank or credit card register. The IIF posts each balancing entry to the existing CAD account named **Uncategorized Expenses** so it can be reclassified in QuickBooks after import. Bank transactions post as cheques or deposits. Card transactions post as journal entries, with charges increasing the card liability and payments and refunds reducing it.

The file uses Intuit’s ASCII IIF format. If a description contains unsupported characters, the app points to the row to review. [Intuit’s IIF file format and samples](https://quickbooks.intuit.com/learn-support/en-ca/help-article/list-management/iif-overview-import-kit-sample-files-headers/L5CZIpJne_CA_en_CA)

To try bank IIF, convert `samples/Synthetic-TD-EasyWeb.pdf`, which contains a $10.00 withdrawal and $25.00 deposit. To try card IIF, convert `samples/Synthetic-Credit-Card.pdf` under **TD Canada Trust → Credit Card** with **Try experimental statement parser** selected. It contains a $30.00 charge and $20.00 payment. Import the file first in a test company via **File → Utilities → Import → IIF Files**. Check the bank or card register for the dates and amounts and the clearing register for the opposite amounts. IIF posts directly to the registers and repeat or overlapping imports can duplicate entries. Use a fresh test company or restore its backup before retrying. [Intuit's QuickBooks Desktop IIF instructions](https://quickbooks.intuit.com/learn-support/en-ca/help-article/import-export-files/export-import-edit-iif-files/L56LT9Z0Q_CA_en_CA)

### Convert a statement from another institution

In the desktop app, choose **Other Canadian Bank / Credit Union** and select the account type. For a bank with a dedicated parser, select **Try experimental statement parser** to use the fallback on a different layout. Compatible statements can export CSV after reconciliation.

The experimental card parser accepts separate **Charges** and **Payments and credits** (or **Credits**) columns, or one signed **Amount** column. It needs printed previous and new balances, total charges, and total payments and credits. A signed table can export only when exactly one sign convention matches the printed controls and any running balances. Tables with separate transaction and posting dates use the transaction date for CSV export. An unfamiliar layout can be inspected with the local PDF preview. QuickBooks Desktop QBO is available through supported dedicated mappings.

## Adding a new bank later
1. Add the parser and its institution/account combination to DEDICATED_EXTRACTORS in app.py.
2. If it has its own QBO generator, add a branch to make_qbo() in app.py.
3. Re-run 2_Build_EXE.bat if you use the .exe.

## Problems
Log file: %LOCALAPPDATA%\BankBridgeNext\bankbridge.log
- Blank/white window: install "Microsoft Edge WebView2 Runtime" (free, from Microsoft).
- If the window can't be created, BankBridge falls back to opening in your browser.
