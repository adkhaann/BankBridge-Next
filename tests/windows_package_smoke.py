"""Smoke-test the built Windows executable on a loopback port."""

import csv
import os
from pathlib import Path
import subprocess
import tempfile

from playwright.sync_api import expect, sync_playwright

from run_app import free_port, wait_until_ready
from test_td_deposit import td_statement


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

            page.locator('input[type="file"]').set_input_files({
                "name": "Synthetic-TD-Business-Chequing.pdf",
                "mimeType": "application/pdf",
                "buffer": td_statement(),
            })
            convert.click()
            expect(page.get_by_text("✓ Reconciled", exact=True)).to_be_visible()
            with page.expect_download() as pending_download:
                page.get_by_role("button", name="Download CSV", exact=True).click()
            csv_path = pending_download.value.path()
            with Path(csv_path).open(newline="", encoding="utf-8") as downloaded:
                rows = list(csv.reader(downloaded))
            expected = [
                ["Date", "Description", "Amount"],
                ["05/01/2026", "Synthetic fee", "-10.0"],
                ["05/01/2026", "Synthetic fee", "-10.0"],
                ["08/01/2026", "Synthetic receipt", "35.0"],
            ]
            if rows != expected:
                raise RuntimeError(f"The synthetic CSV differed from the expected rows: {rows!r}.")


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
                print("The packaged BankBridgeNext app reconciled the TD statement and exported the expected CSV.")
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
