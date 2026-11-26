import unittest

import engine
from test_conversion import statement_pdf


def bmo_loc_statement(payment="20,00CR"):
    return statement_pdf([
        "VOTRE MARGE-CREDIT PERSONNELLE", "www.bmo.com",
        "Date relevØ : 13janv. 2026",
        "Solde prØcØdent,13dØc.", "100,00 $",
        "- Paiement - Merci", "20,00 $CR",
        "- Redressement des crØdits", "0,00 $",
        "+ Achats portØs sur la carte", "0,00 $",
        "+ Avances de fonds/ChÛques", "0,00 $",
        "+ IntØrÙt", "5,00 $",
        "+ Frais", "0,00 $",
        "+ Redressement des dØbits", "0,00 $",
        "Nouveau solde, 13 janv.", "85,00 $",
        "TRANSACTIONS POUR LE COMPTE - XXXX",
        "20dØc.", "1", "Synthetic payment", payment,
        "13janv.", "2", "Synthetic interest", "5,00",
        "13janv.", "3", "Synthetic zero interest", "0,00",
        ".",
    ])


class BmoLineOfCreditTests(unittest.TestCase):
    def test_detects_and_reconciles_loc_rollover(self):
        pdf = bmo_loc_statement()
        self.assertEqual(engine.detect_statement_selection(pdf), {
            "bank": "BMO Bank of Montreal", "account type": "Personal Line of Credit",
        })
        frame, info = engine.extract_bmo_personal_line_of_credit(pdf)
        self.assertEqual(frame["Date"].tolist(), ["2025-12-20", "2026-01-13"])
        self.assertTrue(engine.reconcile_statement(frame, info)[1])
        self.assertIsNone(engine.make_qbo(frame, info, "Personal Line of Credit")[0])
        with self.assertRaisesRegex(ValueError, "line-of-credit"):
            engine.generate_statement_iif(frame, info, "LOC", "Uncategorized Expenses")

    def test_payment_mismatch_blocks_reconciliation(self):
        frame, info = engine.extract_bmo_personal_line_of_credit(bmo_loc_statement("20,01CR"))
        self.assertFalse(engine.reconcile_statement(frame, info)[1])
