import unittest

import engine
from test_conversion import statement_pdf


def yearless_statement(period="2025-12-20 to 2026-01-15", first_date="Dec 31"):
    lines = [
        "Opening balance: 100.00",
        "Closing balance: 115.00",
        "Total debits: 10.00",
        "Total credits: 25.00",
        "Date               Description         Amount    Balance",
        f"{first_date:<19}Synthetic debit     -10.00    90.00",
        "8 janvier          Synthetic credit    25.00     115.00",
    ]
    if period:
        lines.append(f"Statement period: {period}")
    return statement_pdf(lines)


class YearlessTransactionDateTests(unittest.TestCase):
    def convert(self, **changes):
        return engine.extract_universal_transactions(yearless_statement(**changes), "Other", "Personal Savings")

    def test_printed_period_resolves_english_and_french_dates_across_new_year(self):
        frame, info = self.convert()
        self.assertEqual(frame["Date"].tolist(), ["2025-12-31", "2026-01-08"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_missing_ambiguous_or_out_of_period_dates_fail(self):
        with self.assertRaisesRegex(ValueError, "statement period is required"):
            self.convert(period=None)
        for changes in (
            {"period": "2024-12-20 to 2026-01-15"},
            {"first_date": "Nov 30"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "exactly one day"):
                    self.convert(**changes)
