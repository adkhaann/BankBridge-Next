"""Smoke-test the built Windows executable on a loopback port."""

import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect

from run_app import free_port, wait_until_ready


def check_dashboard(port):
    origin = f"http://127.0.0.1:{port}"
    request = BackMsg()
    request.rerun_script.SetInParent()
    expected = {("selectbox", "Bank"), ("selectbox", "Account type"), ("button", "Convert statement")}
    seen = set()
    deadline = time.monotonic() + 30
    with connect(f"ws://127.0.0.1:{port}/_stcore/stream", origin=origin,
                 subprotocols=["streamlit"], open_timeout=5, close_timeout=2) as session:
        session.send(request.SerializeToString())
        while (remaining := deadline - time.monotonic()) > 0:
            message = ForwardMsg.FromString(session.recv(timeout=remaining))
            if message.HasField("delta") and message.delta.HasField("new_element"):
                element = message.delta.new_element
                kind = element.WhichOneof("type")
                if kind == "exception":
                    raise RuntimeError(f"The dashboard raised an exception: {element.exception.message}")
                if kind in ("selectbox", "button"):
                    seen.add((kind, getattr(element, kind).label))
            if message.HasField("script_finished"):
                if message.script_finished != ForwardMsg.FINISHED_SUCCESSFULLY:
                    raise RuntimeError(f"Dashboard script finished with status {message.script_finished}.")
                if missing := expected - seen:
                    raise RuntimeError(f"Dashboard controls missing: {sorted(missing)}.")
                return
    raise RuntimeError("The dashboard did not finish loading.")


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
                check_dashboard(port)
                print("The packaged BankBridgeNext server started and rendered its dashboard controls.")
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
