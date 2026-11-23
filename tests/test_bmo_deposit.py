import csv
import io
import unittest

import fitz

import engine


def bmo_statement(item_count=2, closing="115.00"):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((35, 42), "\n".join([
            "Period ending January 31, 2026",
            f"# 1234 123-456 100.00 10.00 25.00 {closing}",
            f"Number of items processed {item_count}",
        ]), fontsize=10)
        for y, fields in (
            (145, [(35, "Jan 5"), (100, "Synthetic expense"), (350, "10.00"), (515, "90.00")]),
            (170, [(35, "Jan 8"), (100, "Synthetic deposit"), (440, "25.00"), (515, "115.00")]),
        ):
            for x, value in fields:
                page.insert_text((x, y), value, fontsize=10)
        return document.tobytes()


class BmoDepositFixtureTests(unittest.TestCase):
    def test_printed_summary_reconciles_and_exports_csv(self):
        frame, info = engine.extract_bmo_business_chequing_transactions(bmo_statement())
        self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
        self.assertIsNone(info["control"]["debit_count"])
        self.assertIsNone(info["control"]["credit_count"])
        self.assertEqual(info["control"]["item_count"], 2)
        csv_rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(csv_rows[1:], [
            ["05/01/2026", "Synthetic expense", "-10.0"],
            ["08/01/2026", "Synthetic deposit", "25.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])

    def test_wrong_printed_count_or_balance_fails(self):
        for changes in ({"item_count": 3}, {"closing": "115.01"}):
            with self.subTest(changes=changes):
                frame, info = engine.extract_bmo_business_chequing_transactions(bmo_statement(**changes))
                self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])

    def test_edited_debit_cannot_be_hidden_by_a_matching_credit(self):
        frame, info = engine.extract_bmo_business_chequing_transactions(bmo_statement())
        frame.loc[0, "Credit"] = 25.0
        frame.loc[1, "Credit"] = 0.0
        self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])
