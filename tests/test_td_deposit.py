import csv
import io
import unittest

import fitz

import engine


def td_statement():
    with fitz.open() as document:
        first = document.new_page()
        first.insert_text((32, 42), "\n".join([
            "SYNTHETIC TD BUSINESS CHEQUING SAMPLE",
            "Bank: TD Canada Trust",
            "Account type: Business Chequing",
            "JAN 1/26 - JAN 31/26",
            "1234 5678-9876543",
            "Credits 1 35.00",
            "Debits 2 20.00",
        ]), fontsize=10)
        for page, y, date, description, amount_x, amount, balance in (
            (first, 135, "JAN05", "Synthetic fee", 300, "10.00", "90.00"),
            (first, 158, "JAN05", "Synthetic fee", 300, "10.00", "80.00"),
        ):
            for x, value in ((32, date), (100, description), (amount_x, amount), (510, balance)):
                page.insert_text((x, y), value, fontsize=10)
        second = document.new_page()
        for x, value in ((32, "JAN08"), (100, "Synthetic receipt"), (425, "35.00"), (510, "115.00")):
            second.insert_text((x, 135), value, fontsize=10)
        return document.tobytes()


class TdDepositFixtureTests(unittest.TestCase):
    def test_identical_printed_debits_are_preserved_for_reconciliation_and_csv(self):
        frame, info = engine.extract_td_chequing_transactions(td_statement())
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[1:], [
            ["05/01/2026", "Synthetic fee", "-10.0"],
            ["05/01/2026", "Synthetic fee", "-10.0"],
            ["08/01/2026", "Synthetic receipt", "35.0"],
        ])
        self.assertEqual(info["account_id"], "9876543")
        for side in ("Debit", "Credit"):
            self.assertEqual(info["control"][f"{side.lower()}_count"], int((frame[side] > 0).sum()))
            self.assertEqual(info["control"][f"{side.lower()}_total"], frame[side].sum())
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])
