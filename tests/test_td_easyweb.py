import csv
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import fitz
from streamlit.testing.v1 import AppTest

import engine


def easyweb_printout(printed_debit="10.00", zero_balance="115.00"):
    with fitz.open() as document:
        page = document.new_page()
        for y, fields in (
            (30, [(32, "Bank: TD Canada Trust")]),
            (40, [(32, "Account Activity")]),
            (50, [(32, "Account type: Business Chequing")]),
            (70, [(32, "Your transactions for Jan 1, 2026 to Jan 31, 2026")]),
            (110, [(32, "Date"), (93, "Transaction Description"), (235, "Withdrawals"),
                   (300, "Deposits"), (371, "Balance")]),
            (130, [(32, "Jan 9, 2026"), (93, "Synthetic zero"), (249, "0.00"), (371, zero_balance)]),
            (150, [(32, "Jan 8, 2026"), (93, "Synthetic deposit"), (314, "25.00"), (371, "115.00")]),
        ):
            for x, text in fields:
                page.insert_text((x, y), text, fontsize=8)
        page = document.new_page()
        for x, text in ((32, "Jan 5, 2026"), (93, "Synthetic debit"), (249, "10.00"), (371, "90.00")):
            page.insert_text((x, 70), text, fontsize=8)
        page.insert_text((194, 110), f"Total :      ${printed_debit}        $25.00", fontsize=8)
        return document.tobytes()


class TdEasyWebTests(unittest.TestCase):
    def test_newest_first_activity_is_reconciled_and_zero_rows_are_omitted(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout())
        self.assertTrue(info["td_easyweb"])
        self.assertEqual(info["source_pages"], [2, 1])
        self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
        csv_rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(csv_rows[1:], [
            ["05/01/2026", "Synthetic debit", "-10.0"],
            ["08/01/2026", "Synthetic deposit", "25.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])

    def test_printed_total_mismatch_blocks_reconciliation(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout(printed_debit="10.01"))
        self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])

    def test_even_zero_rows_must_match_printed_running_balances(self):
        with self.assertRaisesRegex(ValueError, "printed running balance"):
            engine.extract_td_chequing_transactions(easyweb_printout(zero_balance="115.01"))

    def test_iif_writes_balanced_entries_without_account_or_payee_creation(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout())
        result = engine.generate_statement_iif(frame, info, "TD Chequing", "Clearing:Bank Imports")
        self.assertEqual(result.decode("ascii").splitlines(), [
            "!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO\tCLEAR",
            "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO\tCLEAR",
            "!ENDTRNS",
            "TRNS\tCHECK\t01/05/2026\tTD Chequing\t-10.00\tSynthetic debit\tN",
            "SPL\tCHECK\t01/05/2026\tClearing:Bank Imports\t10.00\tSynthetic debit\tN",
            "ENDTRNS",
            "TRNS\tDEPOSIT\t01/08/2026\tTD Chequing\t25.00\tSynthetic deposit\tN",
            "SPL\tDEPOSIT\t01/08/2026\tClearing:Bank Imports\t-25.00\tSynthetic deposit\tN",
            "ENDTRNS",
        ])
        self.assertTrue(result.endswith(b"\r\n"))

    def test_iif_uses_each_category_and_falls_back_for_blank_rows(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout())
        categorized = frame.assign(Category=["Expenses:Bank Fees", ""])
        result = engine.generate_statement_iif(categorized, info, "TD Chequing", "Clearing")
        self.assertIn(b"SPL\tCHECK\t01/05/2026\tExpenses:Bank Fees\t10.00", result)
        self.assertIn(b"SPL\tDEPOSIT\t01/08/2026\tClearing\t-25.00", result)
        self.assertNotIn(b"TAX", result)
        with self.assertRaisesRegex(ValueError, "transaction 2"):
            engine.generate_statement_iif(categorized, info, "TD Chequing")

    def test_iif_rejects_discrepancies_unsupported_currency_and_invalid_names(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout())
        with self.assertRaisesRegex(ValueError, "CAD statements"):
            engine.generate_statement_iif(frame, dict(info, currency="USD"), "Bank", "Clearing")
        with self.assertRaisesRegex(ValueError, "different account"):
            engine.generate_statement_iif(frame, info, "Bank", "bank")
        with self.assertRaisesRegex(ValueError, "printable ASCII"):
            engine.generate_statement_iif(frame, info, "Bank\tOther", "Clearing")
        frame.loc[0, "Debit"] += 0.01
        with self.assertRaisesRegex(ValueError, "Reconcile"):
            engine.generate_statement_iif(frame, info, "Bank", "Clearing")

    def test_desktop_iif_download_requires_reconciliation_and_account_confirmation(self):
        app = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        for valid in (True, False):
            with self.subTest(reconciled=valid):
                pdf = easyweb_printout(printed_debit="10.00" if valid else "10.01")
                uploaded = SimpleNamespace(name="easyweb.pdf", file_id="easyweb", getvalue=lambda: pdf)
                with patch("streamlit.file_uploader", return_value=uploaded):
                    ui = AppTest.from_file(str(app)).run()
                    next(button for button in ui.button if button.label == "Convert statement").click().run()
                    self.assertFalse(ui.exception)
                    if not valid:
                        self.assertFalse(ui.get("download_button"))
                        continue
                    self.assertTrue(ui.get("download_button")[-1].proto.disabled)
                    bank = next(field for field in ui.text_input if field.label == "QuickBooks bank account")
                    bank.set_value("Bank").run()
                    self.assertTrue(ui.get("download_button")[-1].proto.disabled)
                    next(box for box in ui.checkbox if "Uncategorized Expenses" in box.label).check().run()
                    self.assertFalse(ui.exception)
                    button = ui.get("download_button")[-1]
                    self.assertEqual(button.label, "Download IIF for QuickBooks Desktop")
                    self.assertFalse(button.proto.disabled)
