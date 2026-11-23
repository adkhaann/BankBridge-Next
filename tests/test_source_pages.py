import csv
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import engine
from streamlit.testing.v1 import AppTest

import test_conversion


def multi_page_statement():
    fixture = test_conversion.UniversalDepositTests
    return test_conversion.statement_pdf(fixture.first, fixture.second)


class SourcePageTests(unittest.TestCase):
    def test_source_pages_follow_rows_and_stay_out_of_csv(self):
        frame, info = engine.extract_universal_transactions(
            multi_page_statement(), "Other Canadian Bank / Credit Union", "Personal Savings",
        )
        self.assertEqual(info["source_pages"], [1, 2])
        frame["SourcePage"] = info["source_pages"]
        self.assertTrue(engine.reconcile_universal_transactions(frame, info)[1])
        rows = list(csv.reader(io.StringIO(engine.generate_quickbooks_csv(frame))))
        self.assertEqual(rows[0], ["Date", "Description", "Amount"])

    def test_desktop_review_displays_one_based_pdf_pages(self):
        uploaded = SimpleNamespace(name="statement.pdf", file_id="source-pages", getvalue=multi_page_statement)
        app_path = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        with patch("streamlit.file_uploader", return_value=uploaded):
            ui = AppTest.from_file(str(app_path)).run()
            ui.selectbox(key="bb_bank").set_value("Other Canadian Bank / Credit Union")
            ui.selectbox(key="bb_type").set_value("Personal Savings").run()
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.dataframe[0].value["SourcePage"].tolist(), [1, 2])
            self.assertTrue(ui.get("download_button"))
