import csv
import io
import unittest

import fitz

import engine


def easyweb_printout(printed_debit="10.00", zero_balance="115.00"):
    with fitz.open() as document:
        page = document.new_page()
        for y, fields in (
            (40, [(32, "Account Activity")]),
            (70, [(32, "Your transactions for Jan 1, 2026 to Jan 31, 2026")]),
            (110, [(32, "Date"), (93, "Transaction Description"), (235, "Withdrawals"),
                   (300, "Deposits"), (371, "Balance")]),
            (130, [(32, "Jan 9, 2026"), (93, "Synthetic zero"), (249, "0.00"), (371, zero_balance)]),
            (150, [(32, "Jan 8, 2026"), (93, "Synthetic deposit"), (314, "25.00"), (371, "115.00")]),
        ):
            for x, text in fields:
                page.insert_text((x, y), text, fontsize=8)
        page = document.new_page()
        for x, text in ((32, "Jan 5, 2026"), (93, "Synthetic debit"), (249, "10.00"), (371, "90.00")):
            page.insert_text((x, 70), text, fontsize=8)
        page.insert_text((194, 110), f"Total :      ${printed_debit}        $25.00", fontsize=8)
        return document.tobytes()


class TdEasyWebTests(unittest.TestCase):
    def test_newest_first_activity_is_reconciled_and_zero_rows_are_omitted(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout())
        self.assertTrue(info["td_easyweb"])
        self.assertEqual(info["source_pages"], [2, 1])
        self.assertTrue(engine.reconcile_dedicated_deposit(frame, info)[1])
        csv_rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(csv_rows[1:], [
            ["05/01/2026", "Synthetic debit", "-10.0"],
            ["08/01/2026", "Synthetic deposit", "25.0"],
        ])
        self.assertIsNone(engine.make_qbo(frame, info, "Business Chequing")[0])

    def test_printed_total_mismatch_blocks_reconciliation(self):
        frame, info = engine.extract_td_chequing_transactions(easyweb_printout(printed_debit="10.01"))
        self.assertFalse(engine.reconcile_dedicated_deposit(frame, info)[1])

    def test_even_zero_rows_must_match_printed_running_balances(self):
        with self.assertRaisesRegex(ValueError, "printed running balance"):
            engine.extract_td_chequing_transactions(easyweb_printout(zero_balance="115.01"))
