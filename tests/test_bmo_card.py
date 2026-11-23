import csv
import io
import unittest

import fitz

import engine


def bmo_mastercard_statement():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((32, 42), "\n".join([
            "Statement date Jan. 31, 2026",
            "Account number: 4321 XXXX XXXX 1234",
            "Previous total balance $100.00",
            "Payments and credits -$25.00",
            "Purchases and other charges $30.00",
            "Total interest charges +$2.00",
            "Fees $3.00",
            "Total balance $110.00",
        ]), fontsize=10)
        for y, date, posted, description, amount in (
            (180, "Dec. 31", "Jan. 2", "Synthetic purchase", "$30.00"),
            (200, "Jan. 5", "Jan. 6", "Synthetic payment", "-$20.00"),
            (220, "Jan. 7", "Jan. 8", "Synthetic refund", "$5.00 CR"),
            (240, "Jan. 8", "Jan. 9", "Synthetic interest", "$2.00"),
            (260, "Jan. 8", "Jan. 9", "Synthetic fee", "$3.00"),
        ):
            for x, value in ((32, date), (75, posted), (140, description), (390, amount)):
                page.insert_text((x, y), value, fontsize=10)
        return document.tobytes()


class BmoMastercardFixtureTests(unittest.TestCase):
    def test_summary_keeps_opening_and_closing_balances_distinct(self):
        _, info = engine.extract_bmo_credit_card_transactions(bmo_mastercard_statement())
        summary = info["summary"]
        self.assertEqual(summary["previous_balance"], 100.0)
        self.assertEqual(summary["new_balance"], 110.0)
        self.assertEqual(summary["payments_credits"], 25.0)

    def test_year_boundary_credits_and_csv(self):
        frame, info = engine.extract_bmo_credit_card_transactions(bmo_mastercard_statement())
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[1:], [
            ["31/12/2025", "Synthetic purchase", "-30.0"],
            ["05/01/2026", "Synthetic payment", "20.0"],
            ["07/01/2026", "Synthetic refund", "5.0"],
            ["08/01/2026", "Synthetic interest", "-2.0"],
            ["08/01/2026", "Synthetic fee", "-3.0"],
        ])
        summary = info["summary"]
        self.assertEqual(frame.Debit.sum(), summary["purchases_charges"] + summary["interest"] + summary["fees"])
        self.assertEqual(frame.Credit.sum(), summary["payments_credits"])
        self.assertEqual(summary["previous_balance"] + frame.Debit.sum() - frame.Credit.sum(), summary["new_balance"])
        self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])
