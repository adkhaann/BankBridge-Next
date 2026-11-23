from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import engine
from test_bmo_card import bmo_mastercard_statement
from test_bmo_deposit import bmo_statement
from test_cibc_credit_card import cibc_visa_statement
from test_deposit_reconciliation import cibc_statement
from test_rbc_card import rbc_mastercard_statement
from test_rbc_deposit import rbc_statement
from test_scotiabank_deposit import scotiabank_statement
from test_td_card import td_card_statement
from test_td_deposit import td_statement


class ReleaseExportTests(unittest.TestCase):
    def test_desktop_routes_reconcile_and_expose_expected_downloads(self):
        fixtures = {
            ("TD Canada Trust", "Business Chequing"): (td_statement, False),
            ("TD Canada Trust", "Credit Card"): (td_card_statement, False),
            ("RBC Royal Bank", "Business Chequing"): (rbc_statement, True),
            ("RBC Royal Bank", "Credit Card"): (rbc_mastercard_statement, False),
            ("BMO Bank of Montreal", "Business Chequing"): (bmo_statement, False),
            ("BMO Bank of Montreal", "Credit Card"): (bmo_mastercard_statement, False),
            ("Scotiabank", "Business Chequing"): (scotiabank_statement, False),
            ("CIBC", "Credit Card"): (cibc_visa_statement, False),
        }
        for account in ("Personal Chequing", "Business Chequing", "Personal Savings", "Business Savings"):
            fixtures[("CIBC", account)] = (cibc_statement, True)

        self.assertEqual(set(fixtures), engine.SUPPORTED_COMBINATIONS)
        app = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        for (bank, account_type), (fixture, qbo) in fixtures.items():
            with self.subTest(bank=bank, account=account_type):
                uploaded = SimpleNamespace(name="sample.pdf", file_id="release-sample", getvalue=fixture)
                with patch("streamlit.file_uploader", return_value=uploaded):
                    ui = AppTest.from_file(str(app)).run()
                    ui.selectbox(key="bb_bank").set_value(bank)
                    ui.selectbox(key="bb_type").set_value(account_type).run()
                    next(button for button in ui.button if button.label == "Convert statement").click().run()
                    self.assertFalse(ui.exception)
                    self.assertFalse(ui.error)
                    expected = ["Download CSV", "Download QBO"] if qbo else ["Download CSV"]
                    self.assertEqual([button.label for button in ui.get("download_button")], expected)

    def test_rbc_repeat_export_and_overlapping_transactions_keep_the_same_ids(self):
        frame, info = engine.extract_rbc_business_chequing_transactions(rbc_statement())

        def fitids(rows):
            qbo, note = engine.make_qbo(rows, info, "Business Chequing")
            self.assertIsNone(note)
            return re.findall(r"<FITID>([^\r\n<]+)", qbo)

        first = fitids(frame)
        self.assertEqual(len(set(first)), len(frame))
        self.assertEqual(fitids(frame), first)
        self.assertEqual(fitids(frame.iloc[1:]), first[1:])

    def test_dedicated_card_qbo_writers_preserve_rows_signs_and_repeat_ids(self):
        for bank, fixture in (
            ("TD Canada Trust", td_card_statement),
            ("RBC Royal Bank", rbc_mastercard_statement),
            ("BMO Bank of Montreal", bmo_mastercard_statement),
            ("CIBC", cibc_visa_statement),
        ):
            with self.subTest(bank=bank):
                frame, info = engine.get_dedicated_extractor(bank, "Credit Card")(fixture())
                self.assertTrue(engine.reconcile_credit_card(frame, info)[1])
                info["account_id"] = "4321000000001234"  # Synthetic full ID for testing the writer.
                qbo, note = engine.make_qbo(frame, info, "Credit Card")
                self.assertIsNone(note)
                self.assertIn("<CREDITCARDMSGSRSV1>", qbo)
                self.assertIn("<ACCTID>4321000000001234", qbo)
                expected = [f"{credit - debit:.2f}" for debit, credit in zip(frame.Debit, frame.Credit)]
                self.assertEqual(re.findall(r"<TRNAMT>([^\r\n<]+)", qbo), expected)
                ids = re.findall(r"<FITID>([^\r\n<]+)", qbo)
                self.assertEqual(len(set(ids)), len(frame))
                repeated, _ = engine.make_qbo(frame, info, "Credit Card")
                self.assertEqual(re.findall(r"<FITID>([^\r\n<]+)", repeated), ids)
