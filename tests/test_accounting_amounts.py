import unittest

import engine
from test_conversion import statement_pdf


class AccountingAmountTests(unittest.TestCase):
    def test_overdrawn_statement_reconciles_with_accounting_negatives(self):
        pdf = statement_pdf([
            "Opening balance: 5.00",
            "Closing balance: (3.00)",
            "Total debits: 10.00",
            "Total credits: 2.00",
            "Date             Description          Amount    Balance",
            "2026-01-05       Synthetic debit      ($10.00)  (5.00)",
            "2026-01-08       Synthetic credit     +2,00 $   3,00 $-",
        ])
        frame, info = engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10.0, 0.0], [0.0, 2.0]])
        self.assertEqual(info["running_balances"], [-5.0, -3.0])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_double_signs_and_unmatched_parentheses_are_rejected(self):
        for amount in ("(-$10.00)", "-10.00-", "10.00)", "(10,00 $-)", "+10.00-"):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValueError, "Unrecognized amount"):
                    engine.universal_money_cents(amount)

    def test_negative_value_in_explicit_debit_column_is_rejected(self):
        pdf = statement_pdf([
            "Opening balance: 5.00",
            "Closing balance: (5.00)",
            "Total debits: 10.00",
            "Total credits: 0.00",
            "Date             Description          Debit     Credit",
            "2026-01-05       Synthetic debit      ($10.00)  -",
        ])
        with self.assertRaisesRegex(ValueError, "Expected one positive debit or credit"):
            engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
