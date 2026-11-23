import csv
import io
import unittest

import engine
from test_conversion import statement_pdf


def posting_statement(posting="2026-01-09", *, signed=False):
    header = "Amount    Balance" if signed else "Charges    Credits    Balance"
    rows = ("30.00     130.00", "-20.00    110.00") if signed else (
        "30.00      -          130.00",
        "-          20.00      110.00",
    )
    return statement_pdf(
        [
            "Previous balance: 100.00", "New balance: 110.00", "Total charges: 30.00",
            "Total payments and credits: 20.00",
            f"Transaction date  Posting date  Description          {header}",
            f"2026-01-05        2026-01-06    Synthetic purchase   {rows[0]}",
        ],
        [
            f"Transaction date  Posting date  Description          {header}",
            f"2026-01-08        {posting:<14}Synthetic payment    {rows[1]}",
        ],
    )


class PostingDateTests(unittest.TestCase):
    def convert(self, *args, **kwargs):
        return engine.extract_universal_transactions(
            posting_statement(*args, **kwargs), "Other", "Credit Card"
        )

    def test_exports_transaction_dates_for_split_and_signed_card_columns(self):
        for signed in (False, True):
            with self.subTest(signed=signed):
                frame, info = self.convert(signed=signed)
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
                rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
                self.assertEqual(rows[1:], [
                    ["05/01/2026", "Synthetic purchase", "-30.0"],
                    ["08/01/2026", "Synthetic payment", "20.0"],
                ])

    def test_invalid_posting_date_blocks_extraction(self):
        with self.assertRaisesRegex(ValueError, "Invalid card posting date"):
            self.convert("2026-02-30")
