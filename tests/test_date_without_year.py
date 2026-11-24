import unittest

import engine
from test_conversion import statement_pdf


def yearless_statement(period="2025-12-20 to 2026-01-15", first_date="Dec 31", declaration=None):
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
    if declaration:
        lines.append(f"Date format: {declaration}")
    return statement_pdf(lines)


class YearlessTransactionDateTests(unittest.TestCase):
    def convert(self, **changes):
        return engine.extract_universal_transactions(yearless_statement(**changes), "Other", "Personal Savings")

    def test_printed_period_resolves_english_and_french_dates_across_new_year(self):
        frame, info = self.convert()
        self.assertEqual(frame["Date"].tolist(), ["2025-12-31", "2026-01-08"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_full_english_month_name(self):
        frame, info = self.convert(first_date="December 31")
        self.assertEqual(frame["Date"].tolist(), ["2025-12-31", "2026-01-08"])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_numeric_dates_require_a_matching_declaration_and_period(self):
        for date, declaration in (("31/12", "DD/MM/YYYY"), ("12-31", "MM-DD-YYYY")):
            with self.subTest(date=date):
                frame, info = self.convert(first_date=date, declaration=declaration)
                self.assertEqual(frame["Date"].iloc[0], "2025-12-31")
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        with self.assertRaisesRegex(ValueError, "matching printed"):
            self.convert(first_date="12/03")
        with self.assertRaisesRegex(ValueError, "statement period is required"):
            self.convert(first_date="31/12", declaration="DD/MM/YYYY", period=None)
        with self.assertRaisesRegex(ValueError, "exactly one day"):
            self.convert(first_date="31/12", declaration="DD/MM/YYYY", period="2024-12-20 to 2026-01-15")

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

    def test_english_month_punctuation_and_optional_comma(self):
        for date in ("Dec. 31", "Dec. 31, 2025", "Dec 31 2025", "31 Dec. 2025"):
            with self.subTest(date=date):
                frame, info = self.convert(
                    first_date=date, period="Dec. 20 2025 to Jan. 15, 2026",
                )
                self.assertEqual(frame["Date"].tolist(), ["2025-12-31", "2026-01-08"])
                self.assertTrue(engine.reconcile_statement(frame, info)[1])

    def test_abbreviated_french_months_in_rows_and_period(self):
        for date in ("31 déc.", "31 DÉC. 2025"):
            with self.subTest(date=date):
                frame, info = self.convert(first_date=date, period="20 déc. 2025 au 15 janv. 2026")
                self.assertEqual(frame["Date"].tolist(), ["2025-12-31", "2026-01-08"])
                self.assertEqual(info["period"], ("2025-12-20", "2026-01-15"))
                self.assertTrue(engine.reconcile_statement(frame, info)[1])
        with self.assertRaisesRegex(ValueError, "exactly one day"):
            self.convert(first_date="31 déc.", period="1 janv. 2026 au 15 janv. 2026")
