"""Smoke-test the built Windows executable on a loopback port."""

import os
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen

from run_app import free_port, wait_until_ready


def main():
    executable = Path("dist/BankBridgeNext/BankBridgeNext.exe").resolve(strict=True)
    port = free_port()
    with tempfile.TemporaryDirectory() as local_app_data:
        env = {**os.environ, "LOCALAPPDATA": local_app_data}
        with subprocess.Popen([str(executable), "--serve", str(port)], env=env) as process:
            try:
                if not wait_until_ready(port, process):
                    raise RuntimeError("The packaged BankBridgeNext server did not become ready.")
                with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    if b"Streamlit" not in response.read():
                        raise RuntimeError("The packaged server did not return the Streamlit page.")
                print("The packaged BankBridgeNext server started and served its local page.")
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
