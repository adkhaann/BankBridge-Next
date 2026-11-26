import csv
import io
import unittest

import fitz

import engine


def rbc_mastercard_statement(include_purchase_amount=True, *, heading="RBC Cash Back Mastercard"):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((32, 42), "\n".join([
            heading,
            "STATEMENT FROM DEC 29 TO JAN 31, 2026",
            "Account Number: 4321 XXXX XXXX 1234",
            "Previous Statement Balance $100.00",
            "Payments & credits -$15.00",
            "Purchases & debits $30.00",
            "Interest $3.00",
            "Fees $2.00",
            "NEW BALANCE $120.00",
        ]), fontsize=10)
        entries = [
            (180, "DEC 31", "JAN 2", "Synthetic purchase $30.00", "$30.00" if include_purchase_amount else ""),
            (200, "JAN 5", "JAN 6", "Synthetic payment", "-$15.00"),
            (220, "JAN 8", "JAN 9", "Synthetic interest", "$3.00"),
            (240, "JAN 8", "JAN 9", "Synthetic fee", "$2.00"),
        ]
        for y, date, posted, description, amount in entries:
            for x, value in ((30, date), (75, posted), (125, description), (325, amount)):
                if value:
                    page.insert_text((x, y), value, fontsize=10)
        return document.tobytes()


class RbcMastercardFixtureTests(unittest.TestCase):
    def test_year_boundary_payments_fees_interest_and_csv(self):
        frame, info = engine.extract_rbc_mastercard_transactions(rbc_mastercard_statement())
        summary = info["summary"]
        self.assertEqual(frame.Debit.sum(), summary["purchases_charges"] + summary["interest"] + summary["fees"])
        self.assertEqual(frame.Credit.sum(), summary["payments_credits"])
        self.assertEqual(summary["previous_balance"] + frame.Debit.sum() - frame.Credit.sum(), summary["new_balance"])
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[1:], [
            ["31/12/2025", "Synthetic purchase $30.00", "-30.0"],
            ["05/01/2026", "Synthetic payment", "15.0"],
            ["08/01/2026", "Synthetic interest", "-3.0"],
            ["08/01/2026", "Synthetic fee", "-2.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])

    def test_memo_amount_never_substitutes_for_missing_transaction_amount(self):
        frame, info = engine.extract_rbc_mastercard_transactions(
            rbc_mastercard_statement(include_purchase_amount=False)
        )
        self.assertEqual(frame.Debit.sum(), 5.0)
        self.assertEqual(info["summary"]["purchases_charges"], 30.0)
