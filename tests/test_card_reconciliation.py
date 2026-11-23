import unittest

import engine
from test_bmo_card import bmo_mastercard_statement
from test_cibc_credit_card import cibc_visa_statement
from test_rbc_card import rbc_mastercard_statement
from test_td_card import td_card_statement


class CardReconciliationTests(unittest.TestCase):
    def test_all_dedicated_card_fixtures_pass_shared_reconciliation(self):
        for parser, fixture in (
            (engine.extract_bmo_credit_card_transactions, bmo_mastercard_statement),
            (engine.extract_cibc_credit_card_transactions, cibc_visa_statement),
            (engine.extract_rbc_mastercard_transactions, rbc_mastercard_statement),
            (engine.extract_td_credit_card_transactions, td_card_statement),
        ):
            with self.subTest(parser=parser.__name__):
                self.assertTrue(engine.reconcile_credit_card(*parser(fixture()))[1])

    def test_one_cent_difference_fails_each_control(self):
        frame, info = engine.extract_rbc_mastercard_transactions(rbc_mastercard_statement())
        for key in ("purchases_charges", "payments_credits", "new_balance"):
            with self.subTest(control=key):
                summary = {**info["summary"], key: info["summary"][key] + 0.01}
                self.assertFalse(engine.reconcile_credit_card(frame, {"summary": summary})[1])

    def test_mixed_debit_and_credit_or_invalid_date_fails_even_when_totals_match(self):
        frame, info = engine.extract_rbc_mastercard_transactions(rbc_mastercard_statement())
        invalid = frame.copy()
        invalid.loc[0, "Credit"] = invalid.loc[1, "Credit"]
        invalid.loc[1, "Credit"] = 0.0
        self.assertFalse(engine.reconcile_credit_card(invalid, info)[1])
        invalid = frame.copy()
        invalid.loc[0, "Date"] = "2026-02-30"
        self.assertFalse(engine.reconcile_credit_card(invalid, info)[1])
