import unittest

import engine
from test_conversion import statement_pdf


class BalanceForwardTests(unittest.TestCase):
    def convert(self, heading="Balance forward: 90.00", *, footer=None, page_label=None):
        pdf = statement_pdf(
            ([page_label] if page_label else []) + [
                "Opening balance: 100.00", "Closing balance: 115.00",
                "Total debits: 10.00", "Total credits: 25.00",
                "Date          Description         Debit    Credit",
                "2026-01-05    Synthetic fee       10.00    -",
            ] + ([footer] if footer is not None else []),
            [heading, "2026-01-08    Synthetic deposit   -        25.00"],
        )
        return engine.extract_universal_transactions(pdf, "Other", "Personal Savings")

    def test_balance_forward_is_a_control_and_still_checked_after_edits(self):
        frame, info = self.convert("Solde reporté  90.00")
        self.assertEqual(len(frame), 2)
        rows, ok = engine.reconcile_statement(frame, info)
        self.assertTrue(ok)
        self.assertIn(("Balance forward on page 2", 90.0, 90.0, "$"), rows)
        self.assertFalse(engine.reconcile_statement(frame.iloc[::-1], info)[1])

    def test_contradictory_balance_forward_blocks_conversion(self):
        with self.assertRaisesRegex(ValueError, "printed balance forward on page 2"):
            self.convert("Balance brought forward: 90.01")

    def test_marked_balances_use_the_statement_account_direction(self):
        for account, opening, closing in (
            ("Personal Savings", "10.00 CR", "5.00 DR"),
            ("Credit Card", "10.00 DR", "5.00 CR"),
        ):
            with self.subTest(account=account):
                card = account == "Credit Card"
                pdf = statement_pdf(
                    [
                        f"Opening balance: {opening}", f"Closing balance: {closing}",
                        "Total charges: 0.00" if card else "Total debits: 15.00",
                        "Total credits: 15.00" if card else "Total credits: 0.00",
                        "Date          Description         Amount    Balance",
                        f"2026-01-05    Synthetic entry     -15.00    {closing}",
                    ],
                    [f"Balance forward: {closing}"],
                )
                frame, info = engine.extract_universal_transactions(pdf, "Other", account)
                self.assertEqual(info["control"]["opening"], 10.0)
                self.assertEqual(info["control"]["closing"], -5.0)
                self.assertEqual(info["running_balances"], [-5.0])
                self.assertTrue(engine.reconcile_statement(frame, info)[1])

    def test_page_end_carry_matches_the_next_page_opening(self):
        for footer in ("Balance carried forward: 90.00", "Solde à reporter : 90,00 $"):
            with self.subTest(footer=footer):
                frame, info = self.convert(footer=footer)
                self.assertEqual(info["source_pages"], [1, 2])
                rows, ok = engine.reconcile_statement(frame, info)
                self.assertTrue(ok)
                self.assertIn(("Balance forward on page 1", 90.0, 90.0, "$"), rows)
                self.assertIn(("Balance forward on page 2", 90.0, 90.0, "$"), rows)

        with self.assertRaisesRegex(ValueError, "printed balance forward on page 1"):
            self.convert(footer="Balance carried forward: 90.01")

    def test_printed_totals_accept_only_matching_direction_markers(self):
        for account, labels in (
            ("Personal Savings", ("Total debits", "Total credits")),
            ("Credit Card", ("Total charges", "Total payments and credits")),
        ):
            for debit_marker in ("DR", "CR"):
                with self.subTest(account=account, debit_marker=debit_marker):
                    card = account == "Credit Card"
                    pdf = statement_pdf([
                        "Opening balance: 100.00", f"Closing balance: {'85.00' if card else '115.00'}",
                        f"{labels[0]}: 10.00 {debit_marker}", f"{labels[1]}: 25.00 CR",
                        "Date          Description         Amount",
                        "2026-01-05    Synthetic debit     10.00 DR",
                        "2026-01-08    Synthetic credit    25.00 CR",
                    ])
                    if debit_marker == "DR":
                        frame, info = engine.extract_universal_transactions(pdf, "Other", account)
                        self.assertTrue(engine.reconcile_statement(frame, info)[1])
                    else:
                        with self.assertRaisesRegex(ValueError, "marker conflicts with the printed"):
                            engine.extract_universal_transactions(pdf, "Other", account)

    def test_standalone_page_labels_do_not_interrupt_reconciliation(self):
        for header, footer in (("1 of 2", "Page 1 of 2"), ("1 sur 2", "Page 1 sur 2")):
            with self.subTest(header=header, footer=footer):
                frame, info = self.convert(footer=footer, page_label=header)
                self.assertEqual(info["source_pages"], [1, 2])
                self.assertTrue(engine.reconcile_statement(frame, info)[1])

        with self.assertRaisesRegex(ValueError, "Unrecognized transaction columns"):
            self.convert(footer="2026-01-06    Synthetic fee")
