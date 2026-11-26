import csv
import io
import unittest

import fitz

import engine


def td_card_statement():
    with fitz.open() as document:
        first = document.new_page()
        first.insert_text((32, 42), "\n".join([
            "TD Business Cash Back Visa",
            "STATEMENT DATE: January 31, 2026",
            "Account Number: 4321 XXXX XXXX 1234",
            "Previous Balance $100.00",
            "Payments & Credits -$25.00",
            "Purchases & Other Charges $20.00",
            "Interest $2.00",
            "Fees $3.00",
            "NEW BALANCE $100.00",
        ]), fontsize=10)
        document.new_page()
        for page, y, month, day, description, amount in (
            (0, 180, "DEC", "31", "Synthetic purchase", "$10.00"),
            (0, 200, "DEC", "31", "Synthetic purchase", "$10.00"),
            (1, 120, "JAN", "5", "Synthetic payment", "-$25.00"),
            (1, 140, "JAN", "6", "Synthetic interest", "$2.00"),
            (1, 160, "JAN", "7", "Synthetic fee", "$3.00"),
        ):
            for x, value in ((42, month), (68, day), (135, description), (315, amount)):
                document[page].insert_text((x, y), value, fontsize=10)
        return document.tobytes()


class TdCardFixtureTests(unittest.TestCase):
    def test_duplicate_looking_charges_and_year_boundary_reconcile(self):
        frame, info = engine.extract_td_credit_card_transactions(td_card_statement())
        summary = info["summary"]
        self.assertEqual(frame.Debit.sum(), summary["purchases_charges"] + summary["interest"] + summary["fees"])
        self.assertEqual(frame.Credit.sum(), summary["payments_credits"])
        self.assertEqual(summary["previous_balance"] + frame.Debit.sum() - frame.Credit.sum(), summary["new_balance"])
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[1:], [
            ["31/12/2025", "Synthetic purchase", "-10.0"],
            ["31/12/2025", "Synthetic purchase", "-10.0"],
            ["05/01/2026", "Synthetic payment", "25.0"],
            ["06/01/2026", "Synthetic interest", "-2.0"],
            ["07/01/2026", "Synthetic fee", "-3.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])
