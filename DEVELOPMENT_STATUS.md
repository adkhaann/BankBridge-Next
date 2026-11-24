# BankBridgeNext development status

Branch `pdf-to-qbo` is the development branch. `main` is the stable branch.

## Completed

- Restored a buildable `app.py` from the last compilable source after finding an unterminated parser and duplicate UI code at the development branch tip. Regenerated `engine.py`.
- Established a regression baseline before conversion changes. The tests cover dedicated parser availability, a synthetic CIBC deposit statement with an independent running balance failure case, and the QuickBooks Online CSV schema.
- Implemented experimental multi-page deposit extraction for explicit debit and credit tables in either column order or a single signed amount column. Downloads require printed opening and closing balances and independent debit and credit totals. Reconciliation also checks printed counts, running balances, and statement periods when present.
- Added opt-in Tesseract OCR for image-only pages in the experimental path. PDF text extraction, OCR, edits, reconciliation, and export run locally. Existing Windows installation and shortcut scripts remain in place.
- Expanded first-page selection detection to English and French metadata, common institution aliases, and exact TD Business Cash Back Visa and Simplii No Fee Chequing product headings. Conflicting bank evidence leaves the selection unchanged. The experimental parser detects a printed three-letter Currency field, rejects conflicting codes, and shows the result during review. CSV has no currency column and must be imported into the matching account.
- Removed embedded customer account numbers from the export path. RBC deposit exports use the statement account and transit. Full card account numbers must come from an unambiguous printed field. Masked or unmapped accounts retain the reconciled CSV path.

- Unified credit-card reconciliation across the desktop and standalone interfaces. It compares currency totals to the cent, calculates closing balance from extracted transactions, and rejects invalid dates and rows with both a debit and a credit. When TD's purchases subtotal is unavailable, the existing balance-derived fallback is labeled in the review.

- Applied transaction-row validation to dedicated deposit export gates. CIBC deposit exports also recheck the printed running balances after edits and reject a one-cent difference during extraction.

- Added synthetic coverage for French deposit headings and controls, named-month dates, comma-decimal amounts, and printed-count failures. French OCR remains untested.

- Aligned the Windows packaged shortcut and documentation with the PyInstaller output. The build script checks for the executable before updating the BankBridgeNext shortcut. The configuration is covered by a static test.

- Clear previous review and downloads when the uploaded PDF, bank, account type, or desktop OCR setting changes. Both interfaces are covered by a test that replaces the PDF with a different upload of the same name.

- Dedicated parsers now capture explicitly printed currency codes across pages. Conflicting codes block conversion. Existing CAD QBO templates reject declared foreign currencies, with synthetic USD and EUR evidence for RBC deposit CSV. Undeclared currencies can still use the existing legacy QBO mappings.

- Experimental fixed-width tables can leave one debit or credit cell blank when the amount aligns with a heading on the same page. Missing headings or ambiguous alignment block conversion.

- Experimental signed amounts and printed balances accept parentheses and trailing minus signs, including comma-decimal amounts. Synthetic tests cover an overdrawn balance and rejection of contradictory signs.

- The desktop review table shows the original PDF page for each experimental transaction. The page is read-only and is excluded from the QuickBooks CSV. An optional in-memory preview shows the selected source page on the desktop review screen. If conversion fails, the same preview allows inspection of every page and export stays unavailable.

- Added a GitHub Actions regression job for pushes to `pdf-to-qbo` and pull requests targeting it. The Linux job installs Tesseract so OCR runs alongside the generated-engine and interface tests. A Windows job builds the PyInstaller package and checks that its executable starts on loopback, shows its build ID, reconciles the synthetic TD statement in headless Edge, and downloads a CSV with the expected rows. It also tests RBC QBO download, repeat-download transaction IDs, and that a mismatched statement exposes neither export. After that check passes on a development branch push, GitHub retains the full Windows package as a downloadable artifact for 14 days. The package includes synthetic TD and RBC deposit statements used in regression tests. The README documents the expected results and the RBC QuickBooks Desktop import check.

- Desktop experimental conversion now accepts explicit credit-card charge and payment/credit columns. It accepts negative and CR-marked credits in explicitly labeled columns, or a single signed amount column when exactly one interpretation matches printed totals and balances. Tables with both transaction and posting dates validate both dates and export the transaction date. An unlisted issuer can use Other Canadian Bank / Credit Union with a credit card selection. A toggle enables this path for a bank with a dedicated parser. Experimental statements are eligible for CSV after reconciliation. QBO requires a confirmed institution and account mapping.

- Added synthetic coverage for the Simplii no-fee chequing statement-period header with full English month names and a spaced dash. A second synthetic fixture mirrors the supplied two-date table with Funds out, Funds in, and Balance Forward. Synthetic fixed-width and proportional-font fixtures, including irregular header spacing, reconcile against printed controls and test mismatched carry-forward balances. The actual Simplii PDF and its summary layout still require an end-to-end retry.

- The portable Windows build includes an updater that uses GitHub CLI to fetch the latest passing development package. It validates the build marker, keeps one rollback copy inside the portable app folder, and attempts automatic recovery if replacement fails. Existing backup folders made by older updaters are outside its scope. It preserves existing shortcuts and other files in the portable folder.

- Added release-candidate checks that run every dedicated route through desktop conversion, reconciliation, and download availability. Automated checks also cover QBO signs and stable IDs on repeat exports for four card writers and an overlapping RBC deposit transaction. Simplii validation is deferred from the first release candidate.

- The desktop header displays the installed build ID from the same package marker used by the updater. This makes it possible to confirm which copy a shortcut opened.

- Verified the dedicated TD Business Cash Back Visa parser and CSV output against a user-supplied PDF. Added support for TD EasyWeb account-activity printouts and verified CSV export against a user-supplied multi-page printout. EasyWeb reconciliation checks printed totals and running balances for the displayed period. Zero-dollar rows are checked but omitted from the CSV. The automated fixtures use synthetic data.

- Made QuickBooks Desktop IIF a standard export for reconciled CAD bank and card statements on both dedicated and experimental routes. Bank rows generate cheques and deposits. Card rows generate balanced journal entries against the existing clearing account. IIF uses QuickBooks account names and remains available alongside the existing CSV and eligible QBO exports. Synthetic tests verify both categories. Actual QuickBooks Desktop IIF imports remain pending. Repeat or overlapping imports can duplicate entries.

- Experimental fixed-width tables preserve wrapped transaction descriptions when the next line aligns entirely with the description column on the same page. Synthetic coverage checks amounts, reconciliation, source pages, and exclusion of a separated footer.

- Experimental deposit statements can include explicitly labeled posting or effective dates. The parser validates the second date and exports the transaction date. Synthetic fixtures cover English and French headings and rejection of invalid effective dates.

- Currency detection accepts explicitly labeled codes and selected English and French currency names on dedicated and experimental routes. A name and code can appear together in either order, with one in parentheses. Conflicting names and codes block conversion even when they appear in the same label. Synthetic USD evidence verifies that CAD-only QBO remains unavailable.

- Experimental statements check standalone English and French balance-forward lines against preceding transactions, including after review edits. A synthetic continuation-page fixture verifies that balance forwards remain reconciliation controls and a one-cent mismatch blocks conversion.

- The experimental signed deposit amount column also accepts explicit DR and CR suffixes. Synthetic coverage verifies both transaction directions and rejects a separate sign or a running balance mismatch.

- Experimental credit card statements can use DR and CR in a single amount column. Markers fix the direction of those rows. Unmarked rows require a unique sign convention that reconciles with the printed controls, including continuation balances and separate printed charge and credit counts. A synthetic equal-totals card statement verifies both directions and rejects an inconsistent continuation balance.

## Dedicated layout compatibility

“Dedicated” identifies a parser in the application. Layout verification requires a fixture that parses and reconciles. Desktop eligibility refers to file generation only. The user confirmed a synthetic RBC Business Chequing QBO import and repeat-import check. Other QBO mappings remain unverified in QuickBooks Desktop. IIF can be generated for every reconciled CAD deposit or card layout shown below, including experimental layouts.

| Institution | Account types routed to a dedicated parser | Fixture evidence in this branch | QuickBooks Desktop eligibility |
| --- | --- | --- | --- |
| TD Canada Trust | Business Chequing | Synthetic multi-page statements and EasyWeb activity printouts with CSV and EasyWeb IIF generation | QBO pending a confirmed account mapping and printed ledger balance. |
| TD Canada Trust | Credit Card | Synthetic two-page PDF, identical charges, year rollover, printed totals, and CSV | Full printed card ID and closing balance |
| RBC Royal Bank | Business Chequing | Synthetic PDF extraction, printed control extraction, CSV and QBO generation, and repeat-export FITIDs | Printed account, transit, and closing balance |
| RBC Royal Bank | Credit Card | Synthetic Mastercard PDF, year rollover, payments, interest, fees, CSV and missing amount regression | Full printed card ID and closing balance |
| BMO Bank of Montreal | Business Chequing | Synthetic PDF, printed balances and item count, CSV generation, and failed reconciliation cases | Pending a confirmed account mapping and printed ledger balance |
| BMO Bank of Montreal | Credit Card | Synthetic Mastercard PDF, year rollover, signed payments and refunds, independent printed balances and CSV | Full printed card ID and closing balance |
| Scotiabank | Business Chequing | Synthetic two-page PDF, CSV generation, and failed reconciliation for count and one-cent total differences | Pending a confirmed account mapping and printed ledger balance |
| CIBC | Personal Chequing, Business Chequing, Personal Savings, Business Savings | One synthetic deposit layout parses and reconciles. Coverage across products and statement variants still needs fixtures. | Printed transit/account ID and compatible CIBC deposit type |
| CIBC | Credit Card | Synthetic multi-page Visa conversion, refunds, interest, year rollover, printed balance and masked/full account export checks | Full printed card ID and closing balance |

## Institution coverage outside the dedicated routes

| Institutions | Deposit layout | Other layouts |
| --- | --- | --- |
| TD Canada Trust, RBC Royal Bank, BMO Bank of Montreal, Scotiabank, CIBC | Experimental CSV for deposit combinations outside the dedicated routes | See the dedicated rows above |
| National Bank of Canada, Desjardins, ATB Financial, Laurentian Bank of Canada, Canadian Western Bank, Manulife Bank, First Nations Bank of Canada | Experimental CSV | Simplii table parsing is in `a4dd9ca`, `3ad2218`, and `84d34c4`. Packaged RBC QBO download and the reconciliation export gate are in `c0421bf`. Packaged TD PDF-to-CSV testing was added in `36f1e1b`. Packaged dashboard startup validation was added in `9775464`. Dedicated-route release checks are in `5da5970`, and the desktop build ID is in `7ecda74`. The portable Windows updater is in `c162447`, and Simplii-style statement periods are in `5174709`. Experimental credit-card CSV for compatible card layouts. Other account layouts remain catalog only. |
| Tangerine Bank, Simplii Financial, EQ Bank, Motusbank | Experimental CSV | Simplii table parsing is in `a4dd9ca`, `3ad2218`, and `84d34c4`. Packaged RBC QBO download and the reconciliation export gate are in `c0421bf`. Packaged TD PDF-to-CSV testing was added in `36f1e1b`. Packaged dashboard startup validation was added in `9775464`. Dedicated-route release checks are in `5da5970`, and the desktop build ID is in `7ecda74`. The portable Windows updater is in `c162447`, and Simplii-style statement periods are in `5174709`. Experimental credit-card CSV for compatible card layouts. Other account layouts remain catalog only. |
| PC Financial, Wealthsimple, Home Trust | Experimental CSV | Simplii table parsing is in `a4dd9ca`, `3ad2218`, and `84d34c4`. Packaged RBC QBO download and the reconciliation export gate are in `c0421bf`. Packaged TD PDF-to-CSV testing was added in `36f1e1b`. Packaged dashboard startup validation was added in `9775464`. Dedicated-route release checks are in `5da5970`, and the desktop build ID is in `7ecda74`. The portable Windows updater is in `c162447`, and Simplii-style statement periods are in `5174709`. Experimental credit-card CSV for compatible card layouts. Other account layouts remain catalog only. |
| Coast Capital Savings, Meridian Credit Union, Vancity, Servus Credit Union | Experimental CSV | Simplii table parsing is in `a4dd9ca`, `3ad2218`, and `84d34c4`. Packaged RBC QBO download and the reconciliation export gate are in `c0421bf`. Packaged TD PDF-to-CSV testing was added in `36f1e1b`. Packaged dashboard startup validation was added in `9775464`. Dedicated-route release checks are in `5da5970`, and the desktop build ID is in `7ecda74`. The portable Windows updater is in `c162447`, and Simplii-style statement periods are in `5174709`. Experimental credit-card CSV for compatible card layouts. Other account layouts remain catalog only. |
| Other Canadian Bank / Credit Union | Experimental CSV for unlisted institutions, including issuers and credit unions with compatible deposit layouts | Catalog only |

Experimental coverage has synthetic evidence for a two-page USD deposit table and a rasterized scan of that layout. The evidence does not establish support for named institution layouts.

## Account type compatibility

The existing catalog contains 38 types. Dedicated entries take precedence over the experimental deposit route.

| Account types | Current conversion coverage |
| --- | --- |
| Personal Chequing, Business Chequing, Joint Chequing | Dedicated entries above plus experimental CSV |
| Personal Savings, Business Savings, Joint Savings, High-Interest Savings, Cash Management Account | Dedicated entries above plus experimental CSV |
| Credit Card | Dedicated entries above |
| Personal Credit Card, Business Credit Card, Corporate Credit Card, Secured Credit Card | Routes to the existing dedicated TD, RBC, BMO, and CIBC parsers. A desktop experimental path handles explicitly separated charges and payments/credits for any selected issuer. Product-specific layouts require separate fixture evidence. |
| Prepaid Credit Card | Catalog only |
| Line of Credit, Personal Line of Credit, Business Line of Credit, Home Equity Line of Credit (HELOC), Student Line of Credit | Catalog only |
| Personal Loan, Business Loan, Vehicle Loan, Mortgage, Equipment Financing | Catalog only |
| Non-Registered Investment Account, TFSA, RRSP, RRIF, RESP, FHSA, RDSP, LIRA, LIF, Corporate Investment Account | Catalog only |
| Trust Account, GIC and Term Deposit, Digital Banking Account, Other Account Type | Catalog only |

## Tests and resuming

Test result on Linux with Python 3.12 was **109 passing tests** with local Tesseract English data. The desktop Streamlit UI initialized and displayed the OCR option for an unlisted institution. Windows CI builds the executable, runs full TD CSV and RBC QBO downloads, checks the mismatch export gate, and tests updater rollback. The user confirmed interactive Windows conversion of the packaged synthetic TD statement with three transactions, $20.00 in debits, $35.00 in credits, and the CSV export button visible. The user also confirmed that QuickBooks Desktop accepted the synthetic RBC QBO into its review screen with the correct payment and deposit. The user subsequently confirmed that both the synthetic RBC QBO repeat-import check in QuickBooks Desktop and the synthetic TD CSV import check in QuickBooks Online passed. This closes the first release's sample import checks. Production statement mappings remain unverified.

1. Check out `pdf-to-qbo` and pull it with `git pull --ff-only`.
2. On Linux, run `python3.12 -m venv .venv` and `.venv/bin/python -m pip install -r requirements.txt`. On Windows, use `1_Setup.bat` and `.venv\Scripts\python.exe`.
3. Run `.venv/bin/python build_engine.py` and `.venv/bin/python -m unittest discover -s tests -v`. The OCR integration test skips if Tesseract trained data is unavailable. Install Tesseract English language data locally and configure `TESSDATA_PREFIX` if discovery fails.
4. Run the UI locally with `.venv/bin/python -m streamlit run bankbridge_ui.py --server.address 127.0.0.1 --browser.gatherUsageStats false`, or use `BankBridge.bat` on Windows.

## Pending and next priorities

1. Synthetic fixtures cover all existing dedicated parsers. Collect redacted real statements and matching Web Connect samples for production mappings as needed. Verify additional QuickBooks Desktop mappings and production layouts with appropriately redacted fixtures. Reconcile legacy parsers against independent printed counts, totals, and balances wherever available. Audit remaining legacy QBO helpers and hard-coded institution mappings. The application currently withholds QBO for TD, BMO, and Scotiabank deposits.
2. Improve explicit-layout detection and parsing with coordinates, bilingual labels, day/month layouts and year boundaries, right-aligned or variable-width debit/credit cells, multiline descriptions, continuation pages, and row-level source review. Current date support covers year-first, selected English and French named-month formats, and numeric day/month or month/day dates when the statement declares its format. Conflicting declarations block conversion. Yearless named-month dates and numeric day/month dates require a unique match in the printed period. Numeric dates also require an explicit matching date-format declaration. OCR is restricted to the experimental path and has one synthetic layout test.
3. Expand foreign-currency fixtures and validate QBO currency per institution. Current eligible legacy QBO templates target CAD. Experimental CSV preserves printed amounts without FX conversion and currency can remain undetected.
4. Build dedicated modules for cards, lines of credit, mortgages, loans, and investments. Define how to preserve principal, interest, fees, dividends, investment transactions, and transfers before adding export mappings. Add institution and account-type catalog entries as evidence becomes available.
5. Repeat exports for four card writers and an overlapping RBC deposit transaction retain their FITIDs in automated tests. Verify repeat imports in QuickBooks Desktop, including overlapping real statements, identical transaction rows, and separate accounts. CSV has no import identifier and does not provide cross-import deduplication.
6. Verify the repaired packaged shortcut and the source-installed desktop app on Windows, including optional OCR. Verify the portable updater interactively with GitHub CLI on a user Windows installation.

For broader coverage, user involvement may be needed for redacted statements, genuine Web Connect samples, additional QuickBooks imports, or interactive Windows testing. Synthetic fixtures and parser work can continue independently.

## GitHub commits

Simplii table parsing is in `a4dd9ca`, `3ad2218`, and `84d34c4`. Packaged RBC QBO download and the reconciliation export gate are in `c0421bf`. Packaged TD PDF-to-CSV testing was added in `36f1e1b`. Packaged dashboard startup validation was added in `9775464`. Dedicated-route release checks are in `5da5970`, and the desktop build ID is in `7ecda74`. The portable Windows updater is in `c162447`, and Simplii-style statement periods are in `5174709`. Experimental credit-card CSV is in `97ff75b`. The bundled RBC synthetic statement for Web Connect testing is in `e6b8d9c`. The bundled TD synthetic statement is in `3e5d1fb`. Downloadable Windows development packages are in `9b1c02b`. Windows packaging and local server smoke testing are in `ee39f66`. The GitHub Actions Linux regression job is in `a7e5d13` and `55b20c3`. The PDF preview after failed conversion is in `559b3e5`. The desktop PDF preview is in `4dbee33`. The original PDF page column is in `029a8a3`. Yearless transaction dates resolved against printed periods are in `c09e5df`. Accounting-style negative amounts are in `6e99448`. Credit-first experimental tables are in `d93b7da`. Aligned blank debit and credit cells are covered in `fd3a976`. Single signed amount tables are in `c47aa1a`. The foreign-currency QBO safeguard is in `a0656ca`. Stale review and download cleanup is in `92feb1f`. Dedicated credit card product routing is in `88beecc`. The Windows shortcut configuration fix is in `7d7d2eb`. Declared numeric date formats are in `7d81fb5`. French deposit extraction is in `733e270`. CIBC running-balance validation after edits is in `eb43087`. Shared credit-card reconciliation is in `e6fbd38`. TD credit-card duplicate-looking charges and statement year rollover are covered in `a47f34e`. BMO Mastercard balance, credit sign, and year rollover corrections are in `7f06287`. The RBC Mastercard amount-column regression is in `85200d1`. CIBC Visa continuation and credit reconciliation are in `4d5441b`. The Scotiabank deposit fixture and shared deposit reconciliation are in `230c85a`. The RBC and TD deposit fixtures are in `3d0300a` and `b7b3ae4`. BMO deposit reconciliation in `10d7a13` checks printed balances and totals and uses the printed combined item count when available.

| Commit | Change |
| --- | --- |
| `4f04774` | Restore buildable converter and baseline regression tests |
| `96ef7f9` | Implement reconciled experimental deposit PDF conversion |
| `54f4e18` | Add opt-in local OCR and printed statement periods |
| `ea5417c` | Prevent QBO exports with borrowed or incomplete account identifiers |
| `01c97bb` | Offer conservative statement selection detection |
