import unittest

import engine
from test_conversion import statement_pdf


class SignedDepositFixtureTests(unittest.TestCase):
    def convert(self, second_amount="+25.00", second_header="Date             Description          Amount    Balance"):
        pdf = statement_pdf(
            [
                "Opening balance: 100.00",
                "Closing balance: 115.00",
                "Total debits: 10.00",
                "Total credits: 25.00",
                "Transaction count: 2",
                "Date             Description          Amount    Balance",
                "2026-01-05       Synthetic debit      -10.00    90.00",
            ],
            [
                second_header,
                f"2026-01-08       Synthetic credit     {second_amount}    115.00",
            ],
        )
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_signed_amounts_reconcile_across_pages(self):
        frame, info = self.convert()
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10.0, 0.0], [0.0, 25.0]])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        self.assertIsNone(engine.make_qbo(frame, info, "Personal Savings")[0])

    def test_wrong_sign_or_changed_table_blocks_conversion(self):
        with self.assertRaisesRegex(ValueError, "running balance"):
            self.convert(second_amount="-25.00")
        with self.assertRaisesRegex(ValueError, "headings changed"):
            self.convert(second_header="Date             Description          Debit    Credit    Balance")
