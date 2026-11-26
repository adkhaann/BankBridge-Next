"""Smoke-test the built Windows executable on a loopback port."""

import csv
import os
from pathlib import Path
import re
import subprocess
import tempfile

from playwright.sync_api import expect, sync_playwright

from run_app import free_port, wait_until_ready
from test_rbc_deposit import rbc_statement
from test_td_deposit import td_statement
from test_td_easyweb import easyweb_printout
from test_universal_card import card_statement


def convert_pdf(page, name, data):
    page.locator('input[type="file"]').set_input_files({
        "name": name,
        "mimeType": "application/pdf",
        "buffer": data,
    })
    page.get_by_role("button", name="Convert statement", exact=True).click()


def download_path(page, name):
    with page.expect_download() as pending:
        page.get_by_role("button", name=name, exact=True).click()
    return Path(pending.value.path())


def check_rbc_exports(page):
    page.get_by_role("combobox", name="Bank", exact=True).click()
    page.get_by_role("option", name="RBC Royal Bank", exact=True).click()
    convert_pdf(page, "Synthetic-RBC-mismatched.pdf", rbc_statement(printed_debit="10.01"))
    expect(page.get_by_text("✕ Not reconciled", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Download CSV", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Download QBO", exact=True)).to_have_count(0)

    page.reload()
    page.get_by_role("combobox", name="Bank", exact=True).click()
    page.get_by_role("option", name="RBC Royal Bank", exact=True).click()
    convert_pdf(page, "Synthetic-RBC-Business-Chequing.pdf", rbc_statement())
    expect(page.get_by_text("✓ Reconciled", exact=True)).to_be_visible()
    first = download_path(page, "Download QBO").read_text(encoding="cp1252")
    repeated = download_path(page, "Download QBO").read_text(encoding="cp1252")
    amounts = re.findall(r"<TRNAMT>([^\r\n<]+)", first)
    if amounts != ["-10.00", "25.00"] or "<ACCTID>9876543" not in first:
        raise RuntimeError("The RBC QBO did not contain the expected account and signed amounts.")
    ids = re.findall(r"<FITID>([^\r\n<]+)", first)
    if len(ids) != 2 or len(set(ids)) != 2 or ids != re.findall(r"<FITID>([^\r\n<]+)", repeated):
        raise RuntimeError("The RBC QBO did not retain two unique IDs across repeat downloads.")


def download_iif_postings(page, register_label, register_name):
    expect(page.get_by_text("✓ Reconciled", exact=True)).to_be_visible()
    page.get_by_text("QuickBooks Desktop IIF", exact=True).click()
    button_name = "Download IIF for QuickBooks Desktop"
    expect(page.get_by_role("button", name=button_name)).to_be_disabled()
    for label, account in (
        (register_label, register_name),
        ("QuickBooks clearing account", "Bank Imports Clearing"),
    ):
        field = page.get_by_role("textbox", name=label)
        field.fill(account)
        field.press("Enter")
    page.get_by_text("I confirmed the statement and all QuickBooks accounts used here are in CAD.", exact=True).click()
    rows = download_path(page, button_name).read_text(encoding="ascii").splitlines()
    return [line.split("\t")[1:5] for line in rows if line.startswith(("TRNS\t", "SPL\t"))]


def check_iif_exports(page):
    convert_pdf(page, "Synthetic-TD-EasyWeb.pdf", easyweb_printout())
    if download_iif_postings(page, "QuickBooks bank account", "TD Chequing") != [
        ["CHECK", "01/05/2026", "TD Chequing", "-10.00"],
        ["CHECK", "01/05/2026", "Bank Imports Clearing", "10.00"],
        ["DEPOSIT", "01/08/2026", "TD Chequing", "25.00"],
        ["DEPOSIT", "01/08/2026", "Bank Imports Clearing", "-25.00"],
    ]:
        raise RuntimeError("The downloaded EasyWeb IIF did not contain the expected balanced postings.")

    page.reload()
    page.get_by_role("combobox", name="Account type", exact=True).click()
    page.get_by_role("option", name="Credit Card", exact=True).click()
    page.get_by_text("Try experimental statement parser", exact=True).click()
    convert_pdf(page, "Synthetic-Credit-Card.pdf", card_statement())
    if download_iif_postings(page, "QuickBooks credit card account", "Visa") != [
        ["GENERAL JOURNAL", "01/05/2026", "Visa", "-30.00"],
        ["GENERAL JOURNAL", "01/05/2026", "Bank Imports Clearing", "30.00"],
        ["GENERAL JOURNAL", "01/08/2026", "Visa", "20.00"],
        ["GENERAL JOURNAL", "01/08/2026", "Bank Imports Clearing", "-20.00"],
    ]:
        raise RuntimeError("The downloaded card IIF did not contain the expected balanced postings.")


def check_dashboard(port, *, executable_path=None):
    with sync_playwright() as playwright:
        launch_options = {"executable_path": executable_path} if executable_path else {"channel": "msedge"}
        with playwright.chromium.launch(**launch_options) as browser:
            page = browser.new_page(accept_downloads=True)
            page.set_default_timeout(30_000)
            page.goto(f"http://127.0.0.1:{port}/")
            convert = page.get_by_role("button", name="Convert statement", exact=True)
            expect(convert).to_be_disabled()
            if commit := os.environ.get("GITHUB_SHA"):
                expect(page.get_by_text(f"Build {commit[:7]}", exact=False)).to_be_visible()

            convert_pdf(page, "Synthetic-TD-Business-Chequing.pdf", td_statement())
            expect(page.get_by_text("✓ Reconciled", exact=True)).to_be_visible()
            with download_path(page, "Download CSV").open(newline="", encoding="utf-8") as downloaded:
                rows = list(csv.reader(downloaded))
            expected = [
                ["Date", "Description", "Amount"],
                ["05/01/2026", "Synthetic fee", "-10.0"],
                ["05/01/2026", "Synthetic fee", "-10.0"],
                ["08/01/2026", "Synthetic receipt", "35.0"],
            ]
            if rows != expected:
                raise RuntimeError(f"The synthetic CSV differed from the expected rows: {rows!r}.")
            iif_page = browser.new_page(accept_downloads=True)
            iif_page.set_default_timeout(30_000)
            iif_page.goto(f"http://127.0.0.1:{port}/")
            check_iif_exports(iif_page)
            rbc_page = browser.new_page(accept_downloads=True)
            rbc_page.set_default_timeout(30_000)
            rbc_page.goto(f"http://127.0.0.1:{port}/")
            check_rbc_exports(rbc_page)


def main():
    executable = Path("dist/BankBridgeNext/BankBridgeNext.exe").resolve(strict=True)
    port = free_port()
    with tempfile.TemporaryDirectory() as local_app_data:
        env = {**os.environ, "LOCALAPPDATA": local_app_data}
        with subprocess.Popen([str(executable), "--serve", str(port)], env=env) as process:
            try:
                if not wait_until_ready(port, process):
                    raise RuntimeError("The packaged BankBridgeNext server did not become ready.")
                check_dashboard(port)
                print("The packaged app verified TD CSV, EasyWeb IIF, RBC QBO, and the export gate for a mismatched statement.")
            except Exception:
                log = Path(local_app_data) / "BankBridgeNext" / "bankbridge.log"
                if log.exists():
                    print(log.read_text(encoding="utf-8", errors="replace"))
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
