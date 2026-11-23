import unittest

import engine
from test_conversion import statement_pdf


def row(date, effective, description, funds_out="", funds_in="", balance=""):
    return f"{date:<11}{effective:<11}{description:<29}{funds_out:>9}  {funds_in:>8}  {balance:>7}"


def simplii_table(forward="90.00"):
    heading = row("trans.", "eff.", "transaction", "funds out", "funds in", "balance")
    return statement_pdf(
        [
            "Simplii Financial",
            "statement period: September 28, 2026 - October 28, 2026",
            "Total funds out: 10.00",
            "Total funds in: 25.00",
            "Closing balance: 115.00",
            "details",
            heading,
            row("date", "date", ""),
            row("Sep 28", "Sep 28", "BALANCE FORWARD", balance="100.00"),
            row("Sep 29", "Sep 30", "Synthetic fee", funds_out="10.00", balance="90.00"),
        ],
        [
            heading,
            row("date", "date", ""),
            row("Sep 29", "Sep 30", "BALANCE FORWARD", balance=forward),
            row("Oct 27", "Oct 28", "Synthetic deposit", funds_in="25.00", balance="115.00"),
        ],
    )


class SimpliiTableTests(unittest.TestCase):
    def test_two_dates_and_funds_columns_reconcile_without_importing_balance_forward(self):
        frame, info = engine.extract_universal_transactions(
            simplii_table(), "Simplii Financial", "Personal Chequing",
        )
        self.assertEqual(frame.values.tolist(), [
            ["2026-09-29", "Synthetic fee", 10.0, 0.0],
            ["2026-10-27", "Synthetic deposit", 0.0, 25.0],
        ])
        self.assertEqual(info["source_pages"], [1, 2])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_conflicting_balance_forward_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "balance forward differs"):
            engine.extract_universal_transactions(simplii_table("90.01"), "Simplii Financial", "Personal Chequing")
