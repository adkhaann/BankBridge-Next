import unittest

import engine
from test_cibc_credit_card import cibc_visa_statement


class CardSelectionTests(unittest.TestCase):
    def test_credit_card_product_selections_use_existing_issuer_routes(self):
        for bank, parser in (
            ("TD Canada Trust", engine.extract_td_credit_card_transactions),
            ("RBC Royal Bank", engine.extract_rbc_mastercard_transactions),
            ("BMO Bank of Montreal", engine.extract_bmo_credit_card_transactions),
            ("CIBC", engine.extract_cibc_credit_card_transactions),
        ):
            for account_type in engine.CREDIT_CARD_SELECTIONS:
                with self.subTest(bank=bank, account_type=account_type):
                    self.assertIs(engine.get_dedicated_extractor(bank, account_type), parser)
            self.assertIsNone(engine.get_dedicated_extractor(bank, "Prepaid Credit Card"))
        self.assertIsNone(engine.get_dedicated_extractor("Scotiabank", "Business Credit Card"))

    def test_cibc_product_label_keeps_card_reconciliation_and_qbo_identity(self):
        account_type = "Business Credit Card"
        parser = engine.get_dedicated_extractor("CIBC", account_type)
        frame, info = parser(cibc_visa_statement(card="4321 0000 0000 1234"))
        self.assertTrue(engine.reconcile_credit_card(frame, info)[1])
        data, note = engine.make_qbo(frame, info, account_type)
        self.assertIsNone(note)
        self.assertIn("<CCACCTFROM><ACCTID>4321000000001234", data)
