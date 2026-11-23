import unittest

import fitz

import engine
from test_rbc_deposit import rbc_statement


def rbc_statement_with_currency(*declarations):
    with fitz.open(stream=rbc_statement(), filetype="pdf") as document:
        for declaration in declarations:
            document.new_page().insert_text((32, 42), declaration)
        return document.tobytes()


class StatementCurrencyTests(unittest.TestCase):
    def test_foreign_currency_preserves_csv_and_blocks_cad_qbo(self):
        for currency in ("USD", "EUR"):
            with self.subTest(currency=currency):
                pdf = rbc_statement_with_currency(f"Devise : {currency}")
                frame, info = engine.extract_rbc_business_chequing_transactions(pdf)
                self.assertEqual(info["currency"], currency)
                self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
                self.assertIn("Synthetic expense,-10.0", engine.generate_quickbooks_csv(frame))
                qbo, note = engine.make_qbo(frame, info, "Business Chequing")
                self.assertIsNone(qbo)
                self.assertIn(currency, note)

    def test_cad_is_eligible_and_conflicting_codes_fail(self):
        parser = engine.extract_rbc_business_chequing_transactions
        frame, info = parser(rbc_statement_with_currency("Currency: CAD", "Devise : CAD"))
        qbo, note = engine.make_qbo(frame, info, "Business Chequing")
        self.assertIsNone(note)
        self.assertIn("<CURDEF>CAD", qbo)
        with self.assertRaisesRegex(ValueError, "conflicting currencies"):
            parser(rbc_statement_with_currency("Currency: CAD", "Currency: USD"))
