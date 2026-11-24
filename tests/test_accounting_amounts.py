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

    def test_unicode_minus_and_spaced_thousands(self):
        for value, cents in (
            ("−1 234.56", -123456), ("1\u202f234.56−", -123456),
            ("1\u00a0234.56", 123456), ("(1 234.56)", -123456),
        ):
            with self.subTest(value=value):
                self.assertEqual(engine.universal_money_cents(value), cents)
        for invalid in ("−1,234 567.89", "−10.00-", "−10.00 CR", "10.00− DR"):
            with self.subTest(invalid=invalid):
                parser = engine.marked_amount_cents if invalid.endswith(("CR", "DR")) else engine.universal_money_cents
                with self.assertRaises(ValueError):
                    parser(invalid)

    def test_space_grouping_keeps_statement_totals_and_rows_in_agreement(self):
        pdf = statement_pdf([
            "Opening balance: 2 000.00", "Closing balance: 765.44",
            "Total debits: 1 234.56", "Total credits: 0.00",
            "Date          Description         Amount      Balance",
            "2026-01-05    Synthetic debit     -1 234.56   765.44",
        ])
        frame, info = engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
        self.assertEqual(frame["Debit"].tolist(), [1234.56])
        self.assertTrue(engine.reconcile_statement(frame, info)[1])

    def test_dot_grouping_with_comma_decimals_reconciles(self):
        pdf = statement_pdf([
            "Currency: EUR",
            "Opening balance: 2.000,00", "Closing balance: 765,44",
            "Total debits: 1.234,56", "Total credits: 0,00",
            "Date          Description         Amount      Balance",
            "2026-01-05    Synthetic debit     -1.234,56   765,44",
        ])
        frame, info = engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
        self.assertEqual(frame["Debit"].tolist(), [1234.56])
        self.assertEqual(info["currency"], "EUR")
        self.assertTrue(engine.reconcile_statement(frame, info)[1])
        for invalid in ("1.23,45", "1.234 567,89", "1.234"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Unrecognized amount"):
                    engine.universal_money_cents(invalid)

    def test_dollar_symbol_can_precede_or_follow_either_decimal_format(self):
        pdf = statement_pdf([
            "Currency: USD",
            "Opening balance: $ 100.00", "Closing balance: 90.00 $",
            "Total debits: $ 10,00", "Total credits: 0,00 $",
            "Date          Description         Amount     Balance",
            "2026-01-05    Synthetic debit     ($ 10,00)  90.00 $",
        ])
        frame, info = engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
        self.assertEqual(frame["Debit"].tolist(), [10.0])
        self.assertEqual(info["currency"], "USD")
        self.assertTrue(engine.reconcile_statement(frame, info)[1])
        for invalid in ("$10.00$", "$$10.00", "1$0.00", "$-10.00"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Unrecognized amount"):
                    engine.universal_money_cents(invalid)
