import unittest

import engine
from test_conversion import statement_pdf


def numeric_statement(*declarations, period="01/01/2026 to 12/12/2026", date="05/01/2026"):
    return statement_pdf(
        [
            "Opening balance: 100.00",
            "Closing balance: 90.00",
            "Total debits: 10.00",
            "Total credits: 0.00",
            f"Statement period: {period}",
            "Date            Description         Debit     Credit    Balance",
            f"{date:<16}Synthetic fee       10.00     -         90.00",
        ],
        list(declarations) or ["End of statement"],
    )


class DeclaredDateFixtureTests(unittest.TestCase):
    def parse(self, pdf):
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_date_order_applies_to_earlier_pages(self):
        for declaration, expected in (
            ("Date format: DD/MM/YYYY", "2026-01-05"),
            ("Date format: MM/DD/YYYY", "2026-05-01"),
            ("Format de date : JJ/MM/AAAA", "2026-01-05"),
        ):
            with self.subTest(declaration=declaration):
                frame, info = self.parse(numeric_statement(declaration))
                self.assertEqual(frame["Date"].tolist(), [expected])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_missing_or_conflicting_format_fails(self):
        with self.assertRaisesRegex(ValueError, "ambiguous transaction date"):
            self.parse(numeric_statement())
        with self.assertRaisesRegex(ValueError, "conflicting date formats"):
            self.parse(numeric_statement("Date format: DD/MM/YYYY", "Date format: MM/DD/YYYY"))

    def test_numeric_period_controls_export(self):
        frame, info = self.parse(numeric_statement("Date format: DD/MM/YYYY", period="06/01/2026 to 31/01/2026"))
        self.assertEqual(info["period"], ("2026-01-06", "2026-01-31"))
        self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])

    def test_dot_separated_dates_require_a_matching_declared_order(self):
        period = "01.01.2026 to 12.12.2026"
        for declaration, expected in (
            ("Date format: DD.MM.YYYY", "2026-01-05"),
            ("Date format: MM.DD.YYYY", "2026-05-01"),
            ("Format de date : JJ.MM.AAAA", "2026-01-05"),
        ):
            for date in ("05.01.2026", "05.01"):
                with self.subTest(declaration=declaration, date=date):
                    frame, info = self.parse(numeric_statement(declaration, period=period, date=date))
                    self.assertEqual(frame["Date"].tolist(), [expected])
                    self.assertTrue(engine.reconcile_statement(frame, info)[1])
        with self.assertRaisesRegex(ValueError, "ambiguous transaction date"):
            self.parse(numeric_statement(period=period, date="05.01.2026"))
        with self.assertRaisesRegex(ValueError, "matching printed"):
            self.parse(numeric_statement("Date format: DD/MM/YYYY", date="05.01"))

    def test_invalid_transaction_date_identifies_the_source_page(self):
        pdf = numeric_statement("Date format: DD/MM/YYYY", date="30/02/2026")
        with self.assertRaisesRegex(ValueError, "Invalid transaction date on PDF page 1"):
            self.parse(pdf)
