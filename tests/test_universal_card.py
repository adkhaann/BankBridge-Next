from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import engine
from test_conversion import statement_pdf


def card_statement(closing="110.00", *, payment="20.00"):
    return statement_pdf(
        [
            "Previous balance: 100.00",
            f"New balance: {closing}",
            "Total charges: 30.00",
            "Total payments and credits: -20.00",
            "Transaction count: 2",
            "Date          Description         Charges    Payments and credits    Balance",
            "2026-01-05    Synthetic purchase  30.00      -                       130.00",
        ],
        [
            "Date          Description         Charges    Payments and credits    Balance",
            f"2026-01-08    Synthetic payment   -          {payment:<24}110.00",
        ],
    )


class UniversalCardTests(unittest.TestCase):
    def test_card_balance_math_and_csv_for_unlisted_issuer(self):
        frame, info = engine.extract_universal_transactions(card_statement(), "Other", "Credit Card")
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 20.0]])
        csv_data = engine.generate_quickbooks_csv(frame)
        self.assertIn("Synthetic purchase,-30.0", csv_data)
        self.assertIn("Synthetic payment,20.0", csv_data)
        self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])
        lines = engine.generate_statement_iif(frame, info, "Visa", "Clearing").decode("ascii").splitlines()
        self.assertEqual([line.split("\t")[:5] for line in lines if line.startswith(("TRNS\t", "SPL\t"))], [
            ["TRNS", "GENERAL JOURNAL", "01/05/2026", "Visa", "-30.00"],
            ["SPL", "GENERAL JOURNAL", "01/05/2026", "Clearing", "30.00"],
            ["TRNS", "GENERAL JOURNAL", "01/08/2026", "Visa", "20.00"],
            ["SPL", "GENERAL JOURNAL", "01/08/2026", "Clearing", "-20.00"],
        ])

    def test_explicit_credit_column_accepts_accounting_signs_and_cr(self):
        for payment in ("-20.00", "(20.00)", "20.00 CR"):
            with self.subTest(payment=payment):
                frame, info = engine.extract_universal_transactions(
                    card_statement(payment=payment), "Other", "Credit Card"
                )
                self.assertEqual(frame["Credit"].tolist(), [0.0, 20.0])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_mismatch_blocks_export(self):
        frame, info = engine.extract_universal_transactions(card_statement("110.01"), "Other", "Credit Card")
        self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])
        with self.assertRaisesRegex(ValueError, "Reconcile"):
            engine.generate_statement_iif(frame, info, "Visa", "Clearing")

    def test_desktop_fallback_works_for_an_issuer_with_a_dedicated_parser(self):
        pdf = SimpleNamespace(name="card.pdf", file_id="card-fallback", getvalue=card_statement)
        app = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        with patch("streamlit.file_uploader", return_value=pdf):
            ui = AppTest.from_file(str(app)).run()
            ui.selectbox(key="bb_type").set_value("Credit Card").run()
            next(box for box in ui.checkbox if box.label == "Try experimental statement parser").check().run()
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertFalse(ui.exception)
            self.assertEqual([button.label for button in ui.get("download_button")], ["Download CSV", "Download IIF for QuickBooks Desktop"])
