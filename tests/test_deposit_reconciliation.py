import unittest

import engine
from test_conversion import statement_pdf
from test_rbc_deposit import rbc_statement


def cibc_statement(last_running="115.00", *, closing_prefix=(), currency_header=()):
    return statement_pdf([
        "CIBC Account Statement", "For Jan 1 to Jan 31, 2026", *currency_header,
        "Branch transit number 12345", "Account number 98-76543",
        "Opening balance on Jan 1", "100.00", "Withdrawals", "10.00",
        "Deposits", "25.00", "Closing balance on Jan 31", *closing_prefix, "115.00",
        "Transaction details", "Jan 05", "Synthetic debit", "10.00", "90.00",
        "Jan 08", "Synthetic credit", "25.00", last_running,
    ])


class DedicatedDepositReconciliationTests(unittest.TestCase):
    def test_rbc_invalid_edit_fails_even_when_totals_and_counts_match(self):
        frame, info = engine.extract_rbc_business_chequing_transactions(rbc_statement())
        self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
        frame.loc[0, "Credit"], frame.loc[1, "Credit"] = 25.0, 0.0
        self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])

    def test_cibc_running_balances_still_apply_after_editing(self):
        frame, info = engine.extract_cibc_chequing_transactions(cibc_statement())
        self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
        self.assertFalse(engine.reconcile_dedicated_deposit(frame.iloc[::-1], info)[1])

    def test_cibc_rejects_a_one_cent_running_balance_difference(self):
        with self.assertRaisesRegex(ValueError, "running balance mismatch"):
            engine.extract_cibc_chequing_transactions(cibc_statement("115.01"))

    def test_cibc_standalone_closing_currency_reconciles_without_desktop_exports(self):
        pdf = cibc_statement(closing_prefix=("USD", "="))
        frame, info = engine.extract_cibc_chequing_transactions(pdf)
        self.assertEqual(info["currency"], "USD")
        self.assertTrue(engine.reconcile_statement(frame, info)[1])
        self.assertTrue(engine.generate_quickbooks_csv(frame))
        self.assertIsNone(engine.make_qbo(frame, info, "Personal Savings")[0])
        with self.assertRaisesRegex(ValueError, "CAD"):
            engine.generate_statement_iif(frame, info, "Test register", "Uncategorized Expenses")

        with self.assertRaisesRegex(ValueError, "conflicting currencies"):
            engine.extract_cibc_chequing_transactions(cibc_statement(
                closing_prefix=("USD", "="), currency_header=("Currency: CAD",),
            ))
