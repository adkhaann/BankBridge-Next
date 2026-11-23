import unittest

import fitz

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


    def test_proportional_pdf_text_uses_real_column_positions(self):
        with fitz.open() as document:
            page = document.new_page(width=700)
            page.insert_text((20, 25), "\n".join([
                "Statement period: September 28, 2026 - October 28, 2026",
                "Total funds out: 10.00", "Total funds in: 25.00", "Closing balance: 115.00",
            ]), fontsize=10)
            for y, fields in (
                (108, [(20, "trans."), (74, "eff."), (128, "transaction"), (450, "funds out"),
                       (540, "funds in"), (620, "balance")]),
                (120, [(20, "date"), (74, "date")]),
                (140, [(20, "Sep 28"), (74, "Sep 28"), (128, "BALANCE FORWARD"), (628, "100.00")]),
                (160, [(20, "Sep 29"), (74, "Sep 30"), (128, "Synthetic fee"),
                       (466, "10.00"), (631, "90.00")]),
                (180, [(20, "Oct 27"), (74, "Oct 28"), (128, "Synthetic deposit"),
                       (549, "25.00"), (628, "115.00")]),
            ):
                for x, text in fields:
                    page.insert_text((x, y), text, fontsize=10)
            pdf = document.tobytes()
        frame, info = engine.extract_universal_transactions(pdf, "Simplii Financial", "Personal Chequing")
        self.assertEqual(frame[["Debit", "Credit"]].values.tolist(), [[10.0, 0.0], [0.0, 25.0]])
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
