import unittest

import engine
from test_conversion import statement_pdf


class BalanceForwardTests(unittest.TestCase):
    def convert(self, heading="Balance forward: 90.00"):
        pdf = statement_pdf(
            [
                "Opening balance: 100.00", "Closing balance: 115.00",
                "Total debits: 10.00", "Total credits: 25.00",
                "Date          Description         Debit    Credit",
                "2026-01-05    Synthetic fee       10.00    -",
            ],
            [heading, "2026-01-08    Synthetic deposit   -        25.00"],
        )
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_balance_forward_is_a_control_and_still_checked_after_edits(self):
        frame, info = self.convert("Solde reporté  90.00")
        self.assertEqual(len(frame), 2)
        rows, ok = engine.reconcile_statement(frame, info)
        self.assertTrue(ok)
        self.assertIn(("Balance forward on page 2", 90.0, 90.0, "$"), rows)
        self.assertFalse(engine.reconcile_statement(frame.iloc[::-1], info)[1])

    def test_contradictory_balance_forward_blocks_conversion(self):
        with self.assertRaisesRegex(ValueError, "printed balance forward on page 2"):
            self.convert("Balance brought forward: 90.01")
