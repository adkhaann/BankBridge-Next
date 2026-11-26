import csv
import io
import unittest

import engine
from test_conversion import statement_pdf


def cibc_visa_statement(card="4321 XXXX XXXX 1234", closing="118.00", refund="5.00 CR"):
    return statement_pdf(
        [
            "CIBC Dividend Visa Infinite", "Visa", "Your account at a glance", "Statement Date January 31, 2026",
            f"Account number {card}", "Previous balance", "100.00",
            "Total charges", "33.00", "Total credits", "15.00 CR",
            "Total balance", closing,
        ],
        [
            "Your payments", "Jan 5", "Jan 6", "Synthetic payment", "10.00",
            "Total payments", "Your new charges and credits",
            "Dec 31", "Jan 2", "Synthetic purchase", "30.00",
        ],
        [
            "Jan 8", "Jan 9", "Synthetic refund", refund,
            "Total for card", "Your interest", "Jan 30", "Jan 31", "Synthetic interest", "3.00",
        ],
    )


class CibcCreditCardFixtureTests(unittest.TestCase):
    def test_continuations_refunds_interest_and_year_boundary(self):
        frame, info = engine.extract_cibc_credit_card_transactions(cibc_visa_statement())
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[1:], [
            ["05/01/2026", "Synthetic payment", "10.0"],
            ["31/12/2025", "Synthetic purchase", "-30.0"],
            ["08/01/2026", "Synthetic refund", "5.0"],
            ["30/01/2026", "Synthetic interest", "-3.0"],
        ])
        self.assertEqual(info["summary"]["new_balance"], 118)
        self.assertIsNone(engine.make_qbo(frame, info, "Credit Card")[0])

    def test_printed_closing_balance_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "balance"):
            engine.extract_cibc_credit_card_transactions(cibc_visa_statement(closing="118.01"))

    def test_row_without_amount_cannot_borrow_from_a_later_row(self):
        with self.assertRaisesRegex(ValueError, "transaction totals mismatch"):
            engine.extract_cibc_credit_card_transactions(cibc_visa_statement(refund=""))

    def test_full_identity_is_used_when_printed(self):
        frame, info = engine.extract_cibc_credit_card_transactions(
            cibc_visa_statement(card="4321 0000 0000 1234")
        )
        qbo, note = engine.make_qbo(frame, info, "Credit Card")
        self.assertIsNone(note)
        self.assertIn("<ACCTID>4321000000001234", qbo)
