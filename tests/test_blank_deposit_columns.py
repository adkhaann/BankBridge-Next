import unittest

import engine
from test_conversion import statement_pdf


def fixed_row(date, description, debit="", credit="", balance=""):
    return f"{date:<15}{description:<24}{debit:<11}{credit:<11}{balance}".rstrip()


class BlankDepositColumnTests(unittest.TestCase):
    def convert(self, *, running=True, include_second_heading=True, shifted=False):
        heading = fixed_row("Date", "Description", "Debit", "Credit", "Balance" if running else "")
        credit = " 25.00" if shifted else "25.00"
        pdf = statement_pdf(
            [
                "Opening balance: 100.00",
                "Closing balance: 115.00",
                "Total debits: 10.00",
                "Total credits: 25.00",
                "Transaction count: 2",
                heading,
                fixed_row("2026-01-05", "Synthetic expense", debit="10.00", balance="90.00" if running else ""),
            ],
            ([heading] if include_second_heading else []) + [
                fixed_row("2026-01-08", "Synthetic deposit", credit=credit, balance="115.00" if running else ""),
            ],
        )
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_blank_cells_use_header_alignment_with_or_without_running_balance(self):
        for running in (True, False):
            with self.subTest(running=running):
                frame, info = self.convert(running=running)
                self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10.0, 0.0], [0.0, 25.0]])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_missing_page_header_or_misaligned_amount_is_rejected(self):
        for changes in ({"include_second_heading": False}, {"shifted": True}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "Unrecognized transaction columns"):
                    self.convert(**changes)
