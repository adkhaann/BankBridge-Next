import unittest

import engine
from test_conversion import statement_pdf


def signed_statement(charge, payment, credit_total="20.00", closing="110.00", running=None):
    header = "Date          Description          Amount"
    rows = [
        f"2026-01-05    Synthetic charge      {charge}",
        f"2026-01-08    Synthetic payment     {payment}",
    ]
    if running:
        header += "      Balance"
        rows = [f"{row:<50}{balance}" for row, balance in zip(rows, running)]
    return statement_pdf([
        "Previous balance: 100.00", f"New balance: {closing}",
        "Total charges: 30.00", f"Total payments and credits: {credit_total}",
        header, *rows,
    ])


class SignedCardTests(unittest.TestCase):
    def convert(self, *args, **kwargs):
        return engine.extract_universal_transactions(
            signed_statement(*args, **kwargs), "Other", "Credit Card"
        )

    def test_both_sign_conventions_reconcile_against_printed_totals(self):
        for charge, payment in (("30.00", "-20.00"), ("-30.00", "20.00")):
            with self.subTest(charge=charge):
                frame, info = self.convert(charge, payment)
                self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 20.0]])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
                self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])

    def test_running_balance_resolves_equal_totals_or_blocks_inconsistent_rows(self):
        frame, info = self.convert("30.00", "-30.00", "30.00", "100.00", ("130.00", "100.00"))
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.convert("30.00", "-20.00", running=("130.01", "110.00"))

    def test_equal_totals_without_running_balances_are_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.convert("30.00", "-30.00", "30.00", "100.00")

    def test_explicit_markers_fix_direction_even_when_totals_are_equal(self):
        for charge, payment in (("30.00 DR", "30.00CR"), ("30.00 DR", "-30.00")):
            with self.subTest(charge=charge, payment=payment):
                frame, info = self.convert(charge, payment, "30.00", "100.00")
                self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 30.0]])
                self.assertTrue(engine.reconcile_statement(frame, info)[1])

    def test_conflicting_markers_stop_conversion(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.convert("30.00 CR", "20.00 DR")
        with self.assertRaisesRegex(ValueError, "separate sign"):
            self.convert("30.00 DR", "-20.00 CR")
