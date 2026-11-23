import unittest

import engine
from test_conversion import statement_pdf


class SimpliiPeriodTests(unittest.TestCase):
    def convert(self, period):
        pdf = statement_pdf([
            "Simplii Financial",
            "your no fee chequing account",
            f"statement period:        {period}",
            "statement date:          October 28, 2026",
            "Opening balance: 100.00",
            "Closing balance: 115.00",
            "Total debits: 10.00",
            "Total credits: 25.00",
            "Date             Description         Debit     Credit",
            "2026-09-29       Synthetic debit     10.00     -",
            "2026-10-28       Synthetic credit    -         25.00",
        ])
        return engine.extract_universal_transactions(pdf, "Simplii Financial", "Personal Chequing")

    def test_full_month_names_and_spaced_dash_match_the_printed_header(self):
        frame, info = self.convert("September 28, 2026 - October 28, 2026")
        self.assertEqual(info["period"], ("2026-09-28", "2026-10-28"))
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_dashed_period_still_blocks_out_of_range_transactions(self):
        frame, info = self.convert("2026-09-30 - 2026-10-28")
        self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])

    def test_a_single_date_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "start and end date"):
            self.convert("October 28, 2026")
