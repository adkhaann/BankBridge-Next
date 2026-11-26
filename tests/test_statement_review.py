from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_td_deposit import td_statement
from test_td_card import td_card_statement
from test_conversion import statement_pdf


class StatementReviewTests(unittest.TestCase):
    def test_both_interfaces_clear_downloads_when_input_changes(self):
        for filename, convert_label, result_key in (
            ("app.py", "Process Statement", "transactions"),
            ("bankbridge_ui.py", "Convert statement", "bb_df"),
        ):
            with self.subTest(interface=filename):
                original = SimpleNamespace(name="statement.pdf", file_id="original", getvalue=td_statement)
                replacement = SimpleNamespace(name=original.name, file_id="replacement", getvalue=lambda: b"invalid")
                with patch("streamlit.file_uploader", return_value=original) as uploader:
                    ui = AppTest.from_file(str(Path(__file__).resolve().parents[1] / filename)).run()
                    convert = lambda: next(button for button in ui.button if button.label == convert_label)
                    convert().click().run()
                    self.assertFalse(ui.exception)
                    self.assertIn(result_key, ui.session_state)
                    self.assertTrue(ui.get("download_button"))

                    if filename == "app.py":
                        ui.selectbox[1].set_value("Credit Card").run()
                        self.assertNotIn(result_key, ui.session_state)
                        self.assertFalse(ui.get("download_button"))
                        ui.selectbox[1].set_value("Business Chequing").run()
                        convert().click().run()
                        self.assertIn(result_key, ui.session_state)

                    uploader.return_value = replacement
                    ui.run()
                    self.assertNotIn(result_key, ui.session_state)
                    self.assertFalse(ui.get("download_button"))
                    if filename == "bankbridge_ui.py":
                        self.assertTrue(convert().disabled)
                    else:
                        convert().click().run()
                    self.assertFalse(ui.exception)
                    self.assertTrue(ui.error)
                    self.assertFalse(ui.get("download_button"))

    def test_auto_detects_td_card_and_clears_selection_for_unrecognized_upload(self):
        uploaded = SimpleNamespace(name="statement.pdf", file_id="card", getvalue=td_card_statement)
        path = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        with patch("streamlit.file_uploader", return_value=uploaded) as uploader:
            ui = AppTest.from_file(str(path)).run()
            self.assertEqual(ui.text_input[0].value, "Auto-Detect (All Canadian Banks)")
            self.assertFalse(ui.selectbox)
            self.assertIn("Using TD Canada Trust · Business Credit Card", [c.value for c in ui.caption])
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertEqual(ui.session_state["bb_type_done"], "Business Credit Card")
            self.assertTrue(ui.get("download_button"))

            uploader.return_value = SimpleNamespace(
                name=uploaded.name, file_id="unknown", getvalue=lambda: statement_pdf(["Unrecognized"]),
            )
            ui.run()
            self.assertFalse(ui.get("download_button"))
            self.assertTrue(next(button for button in ui.button if button.label == "Convert statement").disabled)
            self.assertIn("Could not detect the institution and account type.", ui.warning[0].value)
