import csv
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import fitz

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
            with patch("streamlit.image") as preview:
                preview_toggle = next(box for box in ui.checkbox if box.label == "Preview original PDF")
                preview_toggle.check().run()
                ui.selectbox(key="bb_preview_page_1").set_value(2).run()
                image, = preview.call_args.args
                self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertIn("page 2", preview.call_args.kwargs["caption"])
                self.assertTrue(ui.get("download_button"))

    def test_page_preview_is_bounded_and_one_based(self):
        image = engine.render_statement_page(multi_page_statement(), 2)
        pixmap = fitz.Pixmap(image)
        self.assertLessEqual(max(pixmap.width, pixmap.height), 1600)
        for page in (0, 3):
            with self.subTest(page=page):
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    engine.render_statement_page(multi_page_statement(), page)

    def test_failed_conversion_allows_preview_without_enabling_exports(self):
        def unfamiliar_statement():
            return test_conversion.statement_pdf(["Unfamiliar summary"], ["Unfamiliar transaction layout"])

        uploaded = SimpleNamespace(name="unfamiliar.pdf", file_id="unfamiliar", getvalue=unfamiliar_statement)
        app_path = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        with patch("streamlit.file_uploader", return_value=uploaded), patch("streamlit.image") as preview:
            ui = AppTest.from_file(str(app_path)).run()
            ui.selectbox(key="bb_bank").set_value("Other Canadian Bank / Credit Union")
            ui.selectbox(key="bb_type").set_value("Personal Savings").run()
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertTrue(ui.error)
            self.assertFalse(ui.get("download_button"))
            ui.checkbox(key="bb_preview_failed").check().run()
            ui.selectbox(key="bb_preview_page_failed").set_value(2).run()
            self.assertIn("page 2", preview.call_args.kwargs["caption"])
            self.assertFalse(ui.exception)
            self.assertFalse(ui.get("download_button"))

    def test_failed_preview_starts_on_the_page_named_in_the_parser_error(self):
        fixture = test_conversion.UniversalDepositTests
        app_path = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        for second, error in (
            ([line.replace("25.00", "25.OO") for line in fixture.second], "PDF page 2"),
            (["2026-01-08    Synthetic credit"], "Unrecognized transaction columns on page 2"),
            (["Balance forward: 99.99", *fixture.second], "printed balance forward on page 2"),
            ([], "Page 2 has no readable text"),
        ):
            with self.subTest(error=error):
                pdf = test_conversion.statement_pdf(fixture.first, second)
                uploaded = SimpleNamespace(name="invalid.pdf", file_id="invalid", getvalue=lambda: pdf)
                with patch("streamlit.file_uploader", return_value=uploaded), patch("streamlit.image") as preview:
                    ui = AppTest.from_file(str(app_path)).run()
                    ui.selectbox(key="bb_bank").set_value("Other Canadian Bank / Credit Union")
                    ui.selectbox(key="bb_type").set_value("Personal Savings").run()
                    next(button for button in ui.button if button.label == "Convert statement").click().run()
                    self.assertIn(error, ui.error[0].value)
                    ui.checkbox(key="bb_preview_failed").check().run()
                    self.assertEqual(ui.selectbox(key="bb_preview_page_failed").value, 2)
                    self.assertIn("page 2", preview.call_args.kwargs["caption"])
                    self.assertFalse(ui.get("download_button"))

    def test_password_protected_pdf_has_clear_recovery_instructions(self):
        with fitz.open(stream=multi_page_statement(), filetype="pdf") as document:
            locked = document.tobytes(
                encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="synthetic-user", owner_pw="synthetic-owner",
            )
        for operation in (
            engine.detect_statement_selection,
            engine.extract_td_chequing_transactions,
            lambda pdf: engine.extract_universal_transactions(pdf, "Other", "Personal Savings"),
            lambda pdf: engine.render_statement_page(pdf, 1),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "password-protected.*save an unlocked copy"):
                    operation(locked)

    def test_empty_and_unreadable_pdfs_have_clear_recovery_instructions(self):
        for data, error in (
            (b"", "uploaded file is empty"),
            (b"%PDF-1.7\ntruncated statement", "could not be opened as a PDF"),
        ):
            for operation in (
                engine.detect_statement_selection,
                engine.extract_td_chequing_transactions,
                lambda pdf: engine.extract_universal_transactions(pdf, "Other", "Personal Savings"),
                lambda pdf: engine.render_statement_page(pdf, 1),
            ):
                with self.subTest(data=data, operation=operation):
                    with self.assertRaisesRegex(ValueError, error):
                        operation(data)

    def test_upload_error_shows_file_recovery_and_clears_after_replacement(self):
        uploaded = SimpleNamespace(name="statement.pdf", file_id="unreadable", getvalue=lambda: b"")
        app_path = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        with patch("streamlit.file_uploader", return_value=uploaded) as uploader:
            ui = AppTest.from_file(str(app_path)).run()
            ui.selectbox(key="bb_bank").set_value("Other Canadian Bank / Credit Union")
            ui.selectbox(key="bb_type").set_value("Personal Savings").run()
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertIn("The uploaded file is empty", ui.error[0].value)
            self.assertNotIn("account type", ui.error[0].value)
            self.assertFalse(any(box.label == "Preview original PDF" for box in ui.checkbox))
            self.assertFalse(ui.get("download_button"))

            uploader.return_value = SimpleNamespace(
                name="statement.pdf", file_id="replacement", getvalue=multi_page_statement,
            )
            ui.run()
            self.assertFalse(ui.error)
            next(button for button in ui.button if button.label == "Convert statement").click().run()
            self.assertFalse(ui.error)
            self.assertTrue(ui.get("download_button"))
