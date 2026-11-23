import csv
import io
import unittest

import fitz

import engine


def scotiabank_statement(debit_count=1, debit_total="10.00"):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((32, 40), "\n".join([
            "No. of Debits Total Amount - Debits No. of Credits Total Amount - Credits",
            f"{debit_count} ${debit_total} 1 $25.00",
        ]), fontsize=10)
        for y, fields in (
            (145, [(32, "01/03/2026"), (115, "BALANCE FORWARD"), (510, "100.00")]),
            (167, [(32, "01/05/2026"), (115, "Synthetic expense"), (330, "10.00"), (510, "90.00")]),
        ):
            for x, value in fields:
                page.insert_text((x, y), value, fontsize=10)
        page = document.new_page()
        for x, value in ((32, "01/08/2026"), (115, "Synthetic receipt"), (430, "25.00"), (510, "115.00")):
            page.insert_text((x, 145), value, fontsize=10)
        return document.tobytes()


class ScotiabankDepositFixtureTests(unittest.TestCase):
    def test_two_page_statement_reconciles_and_exports_csv(self):
        frame, info = engine.extract_scotiabank_business_chequing_transactions(scotiabank_statement())
        _, reconciled = engine.reconcile_dedicated_deposit(frame, info)
        self.assertTrue(reconciled)
        csv_rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(csv_rows[1:], [
            ["05/01/2026", "Synthetic expense", "-10.0"],
            ["08/01/2026", "Synthetic receipt", "25.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])

    def test_one_cent_or_one_transaction_mismatch_fails_reconciliation(self):
        for printed in ({"debit_count": 2}, {"debit_total": "10.01"}):
            with self.subTest(printed=printed):
                frame, info = engine.extract_scotiabank_business_chequing_transactions(
                    scotiabank_statement(**printed)
                )
                self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])
