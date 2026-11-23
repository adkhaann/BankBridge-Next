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


class DepositDateColumnTests(unittest.TestCase):
    def convert(self, heading, secondary_date=None):
        extra = f"{secondary_date}    " if secondary_date is not None else ""
        pdf = statement_pdf([
            "Opening balance: 100.00", "Closing balance: 90.00",
            "Total debits: 10.00", "Total credits: 0.00",
            f"{heading}    Description    Debit    Credit    Balance",
            f"2026-01-05    {extra}Synthetic fee    10.00    -    90.00",
        ])
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_one_date_or_two_explicit_dates_keep_the_transaction_date(self):
        for heading, secondary in (
            ("Transaction date", None),
            ("Transaction date    Posting date", "2026-01-06"),
            ("Date de transaction    Date d'effet", "2026-01-07"),
        ):
            with self.subTest(heading=heading):
                frame, info = self.convert(heading, secondary)
                self.assertEqual(frame["Date"].tolist(), ["2026-01-05"])
                self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_invalid_effective_date_blocks_conversion(self):
        with self.assertRaisesRegex(ValueError, "Invalid deposit posting or effective date"):
            self.convert("Transaction date    Effective date", "2026-02-30")
