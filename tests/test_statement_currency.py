import unittest

import fitz

import engine
from test_rbc_deposit import rbc_statement
from test_conversion import statement_pdf


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

    def test_written_currency_names_feed_export_checks_on_both_routes(self):
        pdf = rbc_statement_with_currency("Account currency / Devise du compte: US Dollars (USD)", "Currency: USD")
        frame, info = engine.extract_rbc_business_chequing_transactions(pdf)
        self.assertEqual(info["currency"], "USD")
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])

        pdf = statement_pdf([
            "Devise du relevé / Statement currency : CAD (dollars canadiens)",
            "Opening balance: 100.00", "Closing balance: 90.00",
            "Total debits: 10.00", "Total credits: 0.00",
            "Date          Description         Debit    Credit",
            "2026-01-05    Synthetic fee       10.00    -",
        ])
        frame, info = engine.extract_universal_transactions(pdf, "Other", "Personal Savings")
        self.assertEqual(info["currency"], "CAD")
        self.assertTrue(engine.reconcile_statement(frame, info)[1])

    def test_currency_names_and_codes_can_conflict(self):
        with self.assertRaisesRegex(ValueError, "conflicting currencies"):
            engine.statement_currency("Currency:US Dollars\nDevise: CAD")
        self.assertIsNone(engine.statement_currency("Transaction in US dollars"))

    def test_conflicting_name_and_code_on_one_label_stop_conversion(self):
        pdf = rbc_statement_with_currency("Currency / Devise: CAD (US Dollars)")
        with self.assertRaisesRegex(ValueError, "conflicting currencies in one label"):
            engine.extract_rbc_business_chequing_transactions(pdf)
