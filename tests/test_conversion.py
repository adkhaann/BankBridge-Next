import csv
import io
import unittest

import fitz
import pandas as pd

import engine


def statement_pdf(*pages):
    with fitz.open() as document:
        for lines in pages:
            page = document.new_page()
            page.insert_text((42, 42), "\n".join(lines), fontname="cour", fontsize=10)
        return document.tobytes()


class ExistingConversionTests(unittest.TestCase):
    def test_every_dedicated_combination_has_an_extractor(self):
        bank_parsers = {
            "TD Canada Trust": ("td_chequing", "td_credit_card"),
            "RBC Royal Bank": ("rbc_business_chequing", "rbc_mastercard"),
            "BMO Bank of Montreal": ("bmo_business_chequing", "bmo_credit_card"),
            "Scotiabank": ("scotiabank_business_chequing",),
            "CIBC": ("cibc_chequing", "cibc_credit_card"),
        }
        self.assertEqual({bank for bank, _ in engine.SUPPORTED_COMBINATIONS}, set(bank_parsers))
        for parsers in bank_parsers.values():
            for parser in parsers:
                self.assertTrue(callable(getattr(engine, f"extract_{parser}_transactions")))

    def test_cibc_deposit_parses_and_checks_printed_balances(self):
        lines = [
            "CIBC Account Statement", "For Jan 1 to Jan 31, 2026",
            "Branch transit number 12345", "Account number 98-76543",
            "Opening balance on Jan 1", "100.00", "Withdrawals", "10.00",
            "Deposits", "25.00", "Closing balance on Jan 31", "115.00",
            "Transaction details", "Jan 05", "Synthetic debit", "10.00", "90.00",
            "Jan 08", "Synthetic credit", "25.00", "115.00",
        ]
        frame, info = engine.extract_cibc_chequing_transactions(statement_pdf(lines))
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10, 0], [0, 25]])
        self.assertEqual(info["ending_balance"], 115)
        lines[-1] = "116.00"
        with self.assertRaisesRegex(ValueError, "running balance mismatch"):
            engine.extract_cibc_chequing_transactions(statement_pdf(lines))

    def test_quickbooks_online_csv_dates_and_signs(self):
        frame = pd.DataFrame([
            ("2026-01-05", "Synthetic debit", 10.0, 0.0),
            ("2026-01-08", "Synthetic credit", 0.0, 25.0),
        ], columns=["Date", "Description", "Debit", "Credit"])
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows, [
            ["Date", "Description", "Amount"],
            ["05/01/2026", "Synthetic debit", "-10.0"],
            ["08/01/2026", "Synthetic credit", "25.0"],
        ])


class UniversalDepositTests(unittest.TestCase):
    headings = "Date             Description       Debit    Credit    Balance"
    first = [
        "Currency: USD", "Opening balance: 100.00", "Total debits: 10.00",
        "Total credits: 25.00", "Closing balance: 115.00", "Transaction count: 2",
        headings, "2026-01-05       Synthetic debit   10.00    -         90.00",
    ]
    second = [headings, "08 Jan 2026      Synthetic credit  -        25.00     115.00"]

    def parse(self, first=None, second=None):
        return engine.extract_universal_transactions(
            statement_pdf(first or self.first, second or self.second),
            "Other Canadian Bank / Credit Union", "Personal Savings",
        )

    def test_unknown_institution_two_pages_dates_currency_and_csv(self):
        frame, info = self.parse()
        self.assertEqual(frame["Date"].tolist(), ["2026-01-05", "2026-01-08"])
        self.assertEqual(info["currency"], "USD")
        self.assertIsNone(info["account_id"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        self.assertIn("08/01/2026,Synthetic credit,25.0", engine.generate_quickbooks_csv(frame))

    def test_printed_totals_and_counts_are_independent(self):
        for original, changed in (
            ("Transaction count: 2", "Transaction count: 3"),
            ("Total debits: 10.00", "Total debits: 9.99"),
            ("Closing balance: 115.00", "Closing balance: 115.01"),
        ):
            with self.subTest(control=original):
                frame, info = self.parse([changed if line == original else line for line in self.first])
                self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])

    def test_reordered_rows_fail_running_balance_check_after_editing(self):
        frame, info = self.parse()
        self.assertFalse(engine.reconcile_universal_transactions(frame.iloc[::-1], info)[1])

    def test_one_cent_running_balance_difference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "running balance"):
            self.parse(second=[self.headings, self.second[1].replace("115.00", "115.01")])

    def test_missing_controls_and_ambiguous_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "printed opening balance"):
            self.parse([line for line in self.first if not line.startswith("Opening")])
        with self.assertRaisesRegex(ValueError, "ambiguous transaction date"):
            self.parse(second=[self.headings, self.second[1].replace("08 Jan 2026", "01/08/2026")])

    def test_edited_dates_must_stay_within_the_printed_period(self):
        frame, info = self.parse(self.first + ["Statement period: 2026-01-01 to 2026-01-31"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        frame.loc[0, "Date"] = "2026-02-05"
        self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])

    def test_scanned_page_requires_opt_in(self):
        with fitz.open(stream=statement_pdf(self.first + self.second), filetype="pdf") as source:
            pixmap = source[0].get_pixmap(dpi=180)
            with fitz.open() as document:
                page = document.new_page()
                page.insert_image(page.rect, pixmap=pixmap)
                with self.assertRaisesRegex(ValueError, "Enable local OCR"):
                    engine.extract_universal_transactions(document.tobytes(), "Other", "Personal Savings")

    def test_local_ocr_of_synthetic_scan_reconciles(self):
        if not fitz.get_tessdata():
            self.skipTest("Tesseract language data unavailable")
        with fitz.open(stream=statement_pdf(self.first + self.second[1:]), filetype="pdf") as source:
            pixmap = source[0].get_pixmap(dpi=300)
            with fitz.open() as document:
                page = document.new_page()
                page.insert_image(page.rect, pixmap=pixmap)
                frame, info = engine.extract_universal_transactions(
                    document.tobytes(), "Other", "Personal Savings", use_ocr=True
                )
        self.assertEqual(frame["Description"].tolist(), ["Synthetic debit", "Synthetic credit"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
