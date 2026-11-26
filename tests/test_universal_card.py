from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import engine
from test_conversion import statement_pdf


def card_statement(closing="110.00", *, payment="20.00", charge="30.00"):
    return statement_pdf(
        [
            "Bank: TD Canada Trust",
            "Account type: Credit Card",
            "Previous balance: 100.00",
            f"New balance: {closing}",
            "Total charges: 30.00",
            "Total payments and credits: -20.00",
            "Transaction count: 2",
            "Date          Description         Charges    Payments and credits    Balance",
            f"2026-01-05    Synthetic purchase  {charge:<11}-                       130.00",
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
            next(box for box in ui.checkbox if box.label == "Try experimental statement parser").check().run()
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertFalse(ui.exception)
            self.assertEqual([button.label for button in ui.get("download_button")], ["Download CSV", "Download IIF for QuickBooks Desktop"])

    def test_french_purchase_and_payment_columns_reconcile_independent_counts(self):
        for charge_count in (1, 2):
            with self.subTest(charge_count=charge_count):
                pdf = statement_pdf([
                    "Solde précédent : 100,00 $",
                    "Nouveau solde : 110,00 $",
                    "Total des achats et autres frais : 30,00 $",
                    "Total des paiements et crédits : 20,00 $",
                    f"Nombre d'achats et autres frais : {charge_count}",
                    "Nombre de paiements et crédits : 1",
                    "Date    Description    Achats et autres frais    Paiements et crédits    Solde",
                    "5 janvier 2026    Achat synthétique    30,00 $    -    130,00 $",
                    "8 janvier 2026    Paiement synthétique    -    20,00 $    110,00 $",
                ])
                frame, info = engine.extract_universal_transactions(pdf, "Other", "Credit Card")
                self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 20.0]])
                self.assertEqual(engine.reconcile_statement(frame, info)[1], charge_count == 1)

    def test_split_columns_validate_debit_and_credit_markers(self):
        def convert(charge, payment):
            return engine.extract_universal_transactions(
                card_statement(charge=charge, payment=payment), "Other", "Credit Card"
            )

        frame, info = convert("30.00 DR", "20.00CR")
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 20.0]])
        self.assertTrue(engine.reconcile_statement(frame, info)[1])
        for charge, payment in (("30.00 CR", "20.00"), ("30.00", "20.00 DR")):
            with self.subTest(charge=charge, payment=payment):
                with self.assertRaisesRegex(ValueError, "conflicts with its transaction column"):
                    convert(charge, payment)

    def test_expanded_table_headings_still_require_independent_charge_total(self):
        for summary in ("Total charges: 30.00", "Purchases and other charges: 30.00"):
            with self.subTest(summary=summary):
                pdf = statement_pdf([
                    "Previous balance: 100.00", "New balance: 110.00",
                    summary, "Total payments and credits: 20.00",
                    "Date    Transaction description    Purchases & other charges    Credits    Running balance",
                    "2026-01-05    Synthetic purchase    30.00    -    130.00",
                    "2026-01-08    Synthetic payment    -    20.00    110.00",
                ])
                if summary.startswith("Total"):
                    frame, info = engine.extract_universal_transactions(pdf, "Other", "Credit Card")
                    self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[30.0, 0.0], [0.0, 20.0]])
                    self.assertTrue(engine.reconcile_statement(frame, info)[1])
                else:
                    with self.assertRaisesRegex(ValueError, "total charges"):
                        engine.extract_universal_transactions(pdf, "Other", "Credit Card")
