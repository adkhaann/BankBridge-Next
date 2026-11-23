import unittest

import engine
from test_blank_deposit_columns import fixed_row
from test_conversion import statement_pdf


class CreditFirstDepositTests(unittest.TestCase):
    def convert(self, *, french=False, reverse_second_header=False):
        first, second = ("Crédit", "Débit") if french else ("Credit", "Debit")
        header = fixed_row("Date", "Description", first, second, "Balance")
        continued_header = (
            fixed_row("Date", "Description", second, first, "Balance")
            if reverse_second_header else header
        )
        pdf = statement_pdf(
            [
                "Opening balance: 100.00",
                "Closing balance: 115.00",
                "Total debits: 10.00",
                "Total credits: 25.00",
                header,
                fixed_row("2026-01-05", "Synthetic fee", "", "10.00", "90.00"),
            ],
            [
                continued_header,
                fixed_row("2026-01-06", "Synthetic receipt", "25.00", "-", "115.00"),
            ],
        )
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_credit_first_with_explicit_and_blank_cells(self):
        for french in (False, True):
            with self.subTest(french=french):
                frame, info = self.convert(french=french)
                self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10.0, 0.0], [0.0, 25.0]])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_continuation_cannot_reverse_column_meaning(self):
        with self.assertRaisesRegex(ValueError, "headings changed"):
            self.convert(reverse_second_header=True)
