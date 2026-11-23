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
