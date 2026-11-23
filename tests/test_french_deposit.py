import unittest

import fitz

import engine


def french_statement(count=2):
    lines = [
        "Devise : CAD",
        "Période du relevé : 1 janvier 2026 au 31 janvier 2026",
        "Solde d'ouverture : 1 000,00 $",
        "Total des débits : 10,25 $",
        "Total des crédits : 25,75 $",
        "Solde de clôture : 1 015,50 $",
        f"Nombre de transactions : {count}",
        "Date                    Description       Débit      Crédit     Solde",
        "5 janvier 2026          Frais de service  10,25 $    -          989,75 $",
        "8 janvier 2026          Dépôt             -          25,75 $    1 015,50 $",
    ]
    with fitz.open() as document:
        document.new_page().insert_text((32, 42), "\n".join(lines), fontname="cour", fontsize=10)
        return document.tobytes()


class FrenchDepositFixtureTests(unittest.TestCase):
    def test_french_labels_amounts_period_and_dates(self):
        frame, info = engine.extract_universal_transactions(french_statement(), "Other", "Personal Savings")
        self.assertEqual(frame.values.tolist(), [
            ["2026-01-05", "Frais de service", 10.25, 0.0],
            ["2026-01-08", "Dépôt", 0.0, 25.75],
        ])
        self.assertEqual(info["currency"], "CAD")
        self.assertEqual(info["period"], ("2026-01-01", "2026-01-31"))
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])

    def test_french_printed_count_mismatch_blocks_reconciliation(self):
        frame, info = engine.extract_universal_transactions(french_statement(3), "Other", "Personal Savings")
        self.assertFalse(engine.reconcile_universal_transactions(frame, info)[1])
