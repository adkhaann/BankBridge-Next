import csv
import io
import re
import unittest

import fitz

import engine


def rbc_statement(account="987-6543", *, printed_debit="10.00"):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((32, 40), "\n".join([
            "SYNTHETIC RBC BUSINESS CHEQUING SAMPLE",
            "Bank: RBC Royal Bank",
            "Account type: Business Chequing",
            "January 1 to January 31, 2026",
            f"Account number: 12345 {account}",
            "Total deposits & credits (1) + 25.00",
            f"Total cheques & debits (1) - {printed_debit}",
            "Closing balance on January 31 = $115.00",
        ]), fontsize=10)
        for y, fields in (
            (145, [(32, "Date"), (95, "Description"), (330, "Debit"), (430, "Credit")]),
            (167, [(32, "5 Jan"), (95, "Synthetic expense"), (330, "10.00")]),
            (189, [(32, "8 Jan"), (95, "Synthetic deposit"), (430, "25.00")]),
        ):
            for x, label in fields:
                page.insert_text((x, y), label, fontsize=10)
        return document.tobytes()


class RbcDepositFixtureTests(unittest.TestCase):
    def test_pdf_transactions_match_printed_controls_and_export(self):
        frame, info = engine.extract_rbc_business_chequing_transactions(rbc_statement())
        self.assertEqual(frame.values.tolist(), [
            ["2026-01-05", "Synthetic expense", 10.0, 0.0],
            ["2026-01-08", "Synthetic deposit", 0.0, 25.0],
        ])
        self.assertEqual(info["control"], {
            "debit_count": 1, "debit_total": 10.0, "credit_count": 1, "credit_total": 25.0,
        })
        self.assertEqual(info["ending_balance"], 115.0)
        csv_rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual([row[2] for row in csv_rows[1:]], ["-10.0", "25.0"])

        qbo, note = engine.make_qbo(frame, info, "Business Chequing")
        self.assertIsNone(note)
        self.assertIn("<BRANCHID>12345\n<ACCTID>9876543", qbo)
        self.assertIn("<BALAMT>115.00", qbo)
        self.assertEqual(re.findall(r"<TRNAMT>([^\n]+)", qbo), ["-10.00", "25.00"])
        repeated, _ = engine.make_qbo(frame, info, "Business Chequing")
        ids = re.findall(r"<FITID>([^\n]+)", qbo)
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(ids, re.findall(r"<FITID>([^\n]+)", repeated))
