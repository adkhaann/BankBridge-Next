# BankBridgeNext development status

Branch `pdf-to-qbo` is the development branch. `main` is the stable branch.

## Completed

- Restored a buildable `app.py` from the last compilable source after finding an unterminated parser and duplicate UI code at the development branch tip. Regenerated `engine.py`.
- Established a regression baseline before conversion changes. The tests cover dedicated parser availability, a synthetic CIBC deposit statement with an independent running balance failure case, and the QuickBooks Online CSV schema.
- Implemented experimental multi-page deposit extraction for explicit debit and credit tables in either column order or a single signed amount column. Downloads require printed opening and closing balances and independent debit and credit totals. Reconciliation also checks printed counts, running balances, and statement periods when present.
- Added opt-in Tesseract OCR for image-only pages in the experimental path. PDF text extraction, OCR, edits, reconciliation, and export run locally. Existing Windows installation and shortcut scripts remain in place.
- Added detection of explicit bank and account-type labels, or an exact institution heading on the first text page. The experimental parser detects a printed three-letter Currency field, rejects conflicting codes, and shows the result during review. CSV has no currency column and must be imported into the matching account.
- Removed embedded customer account numbers from the export path. RBC deposit exports use the statement account and transit. Full card account numbers must come from an unambiguous printed field. Masked or unmapped accounts retain the reconciled CSV path.

- Unified credit-card reconciliation across the desktop and standalone interfaces. It compares currency totals to the cent, calculates closing balance from extracted transactions, and rejects invalid dates and rows with both a debit and a credit. When TD's purchases subtotal is unavailable, the existing balance-derived fallback is labeled in the review.

- Applied transaction-row validation to dedicated deposit export gates. CIBC deposit exports also recheck the printed running balances after edits and reject a one-cent difference during extraction.

- Added synthetic coverage for French deposit headings and controls, named-month dates, comma-decimal amounts, and printed-count failures. French OCR remains untested.

- Aligned the Windows packaged shortcut and documentation with the PyInstaller output. The build script checks for the executable before updating the BankBridgeNext shortcut. The configuration is covered by a static test.

- Clear previous review and downloads when the uploaded PDF, bank, account type, or desktop OCR setting changes. Both interfaces are covered by a test that replaces the PDF with a different upload of the same name.

- Dedicated parsers now capture explicitly printed currency codes across pages. Conflicting codes block conversion. Existing CAD QBO templates reject declared foreign currencies, with synthetic USD and EUR evidence for RBC deposit CSV. Undeclared currencies can still use the existing legacy QBO mappings.

- Experimental fixed-width tables can leave one debit or credit cell blank when the amount aligns with a heading on the same page. Missing headings or ambiguous alignment block conversion.

- Experimental signed amounts and printed balances accept parentheses and trailing minus signs, including comma-decimal amounts. Synthetic tests cover an overdrawn balance and rejection of contradictory signs.

- The desktop review table shows the original PDF page for each experimental transaction. The page is read-only and is excluded from the QuickBooks CSV.

## Dedicated layout compatibility

“Dedicated” identifies a parser in the application. Layout verification requires a fixture that parses and reconciles. Desktop eligibility refers to file generation only. QuickBooks Desktop import verification remains pending for all rows.

| Institution | Account types routed to a dedicated parser | Fixture evidence in this branch | QuickBooks Desktop eligibility |
| --- | --- | --- | --- |
| TD Canada Trust | Business Chequing | Synthetic multi-page PDF, identical debits, printed totals and counts, and CSV generation | Pending a confirmed account mapping and printed ledger balance |
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
| National Bank of Canada, Desjardins, ATB Financial, Laurentian Bank of Canada, Canadian Western Bank, Manulife Bank, First Nations Bank of Canada | Experimental CSV | Catalog only |
| Tangerine Bank, Simplii Financial, EQ Bank, Motusbank | Experimental CSV | Catalog only |
| PC Financial, Wealthsimple, Home Trust | Experimental CSV | Catalog only |
| Coast Capital Savings, Meridian Credit Union, Vancity, Servus Credit Union | Experimental CSV | Catalog only |
| Other Canadian Bank / Credit Union | Experimental CSV for unlisted institutions, including issuers and credit unions with compatible deposit layouts | Catalog only |

Experimental coverage has synthetic evidence for a two-page USD deposit table and a rasterized scan of that layout. The evidence does not establish support for named institution layouts.

## Account type compatibility

The existing catalog contains 38 types. Dedicated entries take precedence over the experimental deposit route.

| Account types | Current conversion coverage |
| --- | --- |
| Personal Chequing, Business Chequing, Joint Chequing | Dedicated entries above plus experimental CSV |
| Personal Savings, Business Savings, Joint Savings, High-Interest Savings, Cash Management Account | Dedicated entries above plus experimental CSV |
| Credit Card | Dedicated entries above |
| Personal Credit Card, Business Credit Card, Corporate Credit Card, Secured Credit Card | Routes to the existing dedicated TD, RBC, BMO, and CIBC parsers. Product-specific layouts require separate fixture evidence. |
| Prepaid Credit Card | Catalog only |
| Line of Credit, Personal Line of Credit, Business Line of Credit, Home Equity Line of Credit (HELOC), Student Line of Credit | Catalog only |
| Personal Loan, Business Loan, Vehicle Loan, Mortgage, Equipment Financing | Catalog only |
| Non-Registered Investment Account, TFSA, RRSP, RRIF, RESP, FHSA, RDSP, LIRA, LIF, Corporate Investment Account | Catalog only |
| Trust Account, GIC and Term Deposit, Digital Banking Account, Other Account Type | Catalog only |

## Tests and resuming

Test result on Linux with Python 3.12 was **63 passing tests** with local Tesseract English data. The desktop Streamlit UI initialized and displayed the OCR option for an unlisted institution. Windows packaging and imports in QuickBooks were not exercised.

1. Check out `pdf-to-qbo` and pull it with `git pull --ff-only`.
2. On Linux, run `python3.12 -m venv .venv` and `.venv/bin/python -m pip install -r requirements.txt`. On Windows, use `1_Setup.bat` and `.venv\Scripts\python.exe`.
3. Run `.venv/bin/python build_engine.py` and `.venv/bin/python -m unittest discover -s tests -v`. The OCR integration test skips if Tesseract trained data is unavailable. Install Tesseract English language data locally and configure `TESSDATA_PREFIX` if discovery fails.
4. Run the UI locally with `.venv/bin/python -m streamlit run bankbridge_ui.py --server.address 127.0.0.1 --browser.gatherUsageStats false`, or use `BankBridge.bat` on Windows.

## Pending and next priorities

1. Gather redacted or synthetic fixtures for every existing dedicated parser and Web Connect mapping. Verify QuickBooks Desktop imports before claiming compatibility, including the revised RBC account mapping and repeat import behavior. Verify sample QuickBooks Online imports. Reconcile legacy parsers against independent printed counts, totals, and balances wherever available. Audit remaining legacy QBO helpers and hard-coded institution mappings. The application currently withholds QBO for TD, BMO, and Scotiabank deposits.
2. Improve explicit-layout detection and parsing with coordinates, bilingual labels, day/month layouts and year boundaries, right-aligned or variable-width debit/credit cells, multiline descriptions, continuation pages, and row-level source review. Current date support covers year-first, selected English and French named-month formats, and numeric day/month or month/day dates when the statement declares its format. Conflicting declarations block conversion. Selected English and French named-month transaction dates without a year require a uniquely matching date in the printed statement period. OCR is restricted to the experimental path and has one synthetic layout test.
3. Expand foreign-currency fixtures and validate QBO currency per institution. Current eligible legacy QBO templates target CAD. Experimental CSV preserves printed amounts without FX conversion and currency can remain undetected.
4. Build dedicated modules for cards, lines of credit, mortgages, loans, and investments. Define how to preserve principal, interest, fees, dividends, investment transactions, and transfers before adding export mappings. Add institution and account-type catalog entries as evidence becomes available.
5. Validate stable transaction IDs using overlapping statements, repeat imports, true duplicate rows, and separate accounts. Existing QBO FITIDs require regression coverage across layouts. CSV has no import identifier and does not provide cross-import deduplication.
6. Verify the repaired packaged shortcut and the source-installed desktop app on Windows, including optional OCR. Implement a one-click update flow with rollback.

User involvement will be needed for redacted statement and genuine Web Connect samples, QuickBooks Desktop import testing, and local Windows validation. Synthetic fixtures and parser work can continue independently.

## GitHub commits

Yearless transaction dates resolved against printed periods are in `c09e5df`. Accounting-style negative amounts are in `6e99448`. Credit-first experimental tables are in `d93b7da`. Aligned blank debit and credit cells are covered in `fd3a976`. Single signed amount tables are in `c47aa1a`. The foreign-currency QBO safeguard is in `a0656ca`. Stale review and download cleanup is in `92feb1f`. Dedicated credit card product routing is in `88beecc`. The Windows shortcut configuration fix is in `7d7d2eb`. Declared numeric date formats are in `7d81fb5`. French deposit extraction is in `733e270`. CIBC running-balance validation after edits is in `eb43087`. Shared credit-card reconciliation is in `e6fbd38`. TD credit-card duplicate-looking charges and statement year rollover are covered in `a47f34e`. BMO Mastercard balance, credit sign, and year rollover corrections are in `7f06287`. The RBC Mastercard amount-column regression is in `85200d1`. CIBC Visa continuation and credit reconciliation are in `4d5441b`. The Scotiabank deposit fixture and shared deposit reconciliation are in `230c85a`. The RBC and TD deposit fixtures are in `3d0300a` and `b7b3ae4`. BMO deposit reconciliation in `10d7a13` checks printed balances and totals and uses the printed combined item count when available.

| Commit | Change |
| --- | --- |
| `4f04774` | Restore buildable converter and baseline regression tests |
| `96ef7f9` | Implement reconciled experimental deposit PDF conversion |
| `54f4e18` | Add opt-in local OCR and printed statement periods |
| `ea5417c` | Prevent QBO exports with borrowed or incomplete account identifiers |
| `01c97bb` | Offer conservative statement selection detection |
