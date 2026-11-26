"""
BankBridge desktop launcher.

Opens BankBridge in its own application window (no browser). Behind the
scenes it starts the BankBridge engine as a hidden background process on a
private port, shows a loading screen, and shuts the engine down when the
window is closed.
"""
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import datetime


def _bundle_hints():
    """Never called. Lists the libraries PyInstaller must pack into the .exe,
    without slowing down the window opening."""
    import re, hashlib                # noqa: F401,E401
    import pandas                     # noqa: F401
    import fitz                       # noqa: F401
    import pymupdf                    # noqa: F401
    import streamlit                  # noqa: F401
    import streamlit.web.cli          # noqa: F401
    import engine                     # noqa: F401
    import build_engine               # noqa: F401

APP_NAME = "BankBridgeNext"
FROZEN = getattr(sys, "frozen", False)
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
LOG_FILE = os.path.join(DATA_DIR, "bankbridge.log")
CREATE_NO_WINDOW = 0x08000000


def log(msg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Engine (Streamlit server) - runs in its own hidden process
# ---------------------------------------------------------------------------
def watch_parent(parent_pid):
    """Exit the engine when the BankBridge window process ends.
    Uses the process handle (not a pipe), which is safe on Windows."""
    if not parent_pid:
        return
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
        if handle:
            kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
    else:
        while os.getppid() == parent_pid:
            time.sleep(2)
    os._exit(0)


def serve(port, parent_pid=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    out = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = out
    sys.stdin = open(os.devnull, "r")
    threading.Thread(target=watch_parent, args=(parent_pid,), daemon=True).start()

    if not FROZEN:
        import build_engine
        if build_engine.needs_rebuild():
            build_engine.build()

    cred_dir = os.path.join(os.path.expanduser("~"), ".streamlit")
    os.makedirs(cred_dir, exist_ok=True)
    cred = os.path.join(cred_dir, "credentials.toml")
    if not os.path.exists(cred):
        with open(cred, "w") as f:
            f.write('[general]\nemail = ""\n')

    # BankBridge never needs Streamlit's git lookup (it starts git.exe
    # in the background on first page load). Switch it off.
    try:
        from streamlit.runtime import app_session
        app_session.AppSession._handle_git_information_request = lambda self: None
    except Exception as e:
        log(f"Could not disable git lookup: {e!r}")

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", os.path.join(HERE, "bankbridge_ui.py"),
        "--global.developmentMode=false",
        "--server.headless=true",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--server.maxUploadSize=50",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
        "--theme.base=light",
        "--theme.primaryColor=#1F6FB2",
    ]
    sys.exit(stcli.main())


def start_engine(port):
    if FROZEN:
        cmd = [sys.executable, "--serve", str(port), str(os.getpid())]
    else:
        cmd = [sys.executable, os.path.abspath(__file__), "--serve", str(port), str(os.getpid())]
    flags = CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=flags, cwd=HERE,
    )


def wait_until_ready(port, proc, timeout=90):
    url = f"http://127.0.0.1:{port}/_stcore/health"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            return False
        try:
            with opener.open(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
SPLASH = """<!doctype html><html><head><meta charset="utf-8"><title>BankBridgeNext</title><link rel="icon" href="__ICON__"><style>
html,body{margin:0;height:100%;background:#0E2A47;font-family:"Segoe UI",system-ui,sans-serif;color:#fff}
.w{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
.n{font-size:30px;font-weight:700;letter-spacing:.3px}.t{color:#A9BCD3;font-size:14px}
.bar{width:220px;height:4px;border-radius:4px;background:rgba(255,255,255,.12);overflow:hidden}
.bar i{display:block;width:40%;height:100%;background:#13A89E;border-radius:4px;animation:m 1.1s ease-in-out infinite}
@keyframes m{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}
</style></head><body><div class="w">
<svg width="72" height="72" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#1B5A92"/><stop offset="1" stop-color="#13A89E"/></linearGradient></defs>
<rect width="64" height="64" rx="14" fill="url(#g)"/><g stroke="#fff" stroke-linecap="round" fill="none">
<path d="M10 44H54" stroke-width="4"/><path d="M22 18V50M42 18V50" stroke-width="4"/>
<path d="M10 27L22 19Q32 40 42 19L54 27" stroke-width="3" stroke-linejoin="round"/>
<path d="M27 25.6V44M32 29.5V44M37 25.6V44" stroke-width="2"/></g></svg>
<div class="n">BankBridgeNext</div><div class="bar"><i></i></div><div class="t">Starting up…</div>
</div></body></html>"""

ERROR_PAGE = """<!doctype html><html><body style="font-family:Segoe UI,sans-serif;padding:40px;color:#1B2B3F">
<h2>BankBridge could not start</h2><p>Please send this file to support:</p>
<p><code>{log}</code></p></body></html>"""


SPLASH_ICON = "data:image/png;base64,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"


def splash_html():
    return SPLASH.replace("__ICON__", SPLASH_ICON)


# --- Option 1: built-in window (needs Microsoft WebView2) -------------------
def open_with_webview(port, proc):
    """Returns 'ok', 'unavailable' or 'failed'."""
    try:
        import webview
        if os.name == "nt":
            from webview.platforms import winforms
            renderer = getattr(winforms, "renderer", "unknown")
            log(f"pywebview renderer: {renderer}")
            if renderer != "edgechromium":
                return "unavailable"   # old IE engine cannot show BankBridge
    except Exception as e:
        log(f"pywebview unavailable: {e!r}")
        return "unavailable"

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        APP_NAME, html=splash_html(), width=1320, height=900, min_size=(980, 680),
        background_color="#0E2A47", text_select=True,
    )
    loaded = threading.Event()
    window.events.loaded += lambda *a: loaded.set()
    outcome = {"result": "ok"}

    def load_app():
        if not loaded.wait(10):
            log("Built-in window did not paint the splash; switching")
            outcome["result"] = "failed"
            window.destroy()
            return
        if not wait_until_ready(port, proc):
            log("Engine failed to start")
            window.load_html(ERROR_PAGE.format(log=LOG_FILE))
            return
        loaded.clear()
        window.load_url(f"http://127.0.0.1:{port}")
        if not loaded.wait(25):
            log("Built-in window did not load the page; switching to Edge app window")
            outcome["result"] = "failed"
            window.destroy()

    icon = os.path.join(HERE, "assets", "bankbridge.ico")
    try:
        webview.start(load_app, gui="edgechromium", private_mode=False,
                      storage_path=os.path.join(DATA_DIR, "webview"),
                      icon=icon if os.path.exists(icon) else None)
    except Exception as e:
        log(f"pywebview failed: {e!r}")
        return "failed"
    return outcome["result"]


# --- Option 2: Microsoft Edge app window (no tabs, no address bar) ----------
def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            path = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(path):
                return path
    return None


def open_with_edge(url):
    edge = find_edge()
    if not edge:
        log("Microsoft Edge not found")
        return False

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # A shared profile can hand the window to an existing Edge process.
        # The launching process then exits while the app window is still open.
        with tempfile.TemporaryDirectory(
            prefix="edge-session-", dir=DATA_DIR, ignore_cleanup_errors=True,
        ) as profile:
            prefs_dir = os.path.join(profile, "Default")
            os.makedirs(prefs_dir)
            with open(os.path.join(prefs_dir, "Preferences"), "w", encoding="utf-8") as f:
                f.write('{"download":{"prompt_for_download":true},'
                        '"browser":{"has_seen_welcome_page":true}}')

            log("Opening Edge app window with a fresh profile")
            edge_proc = subprocess.Popen([
                edge, f"--app={url}",
                f"--user-data-dir={profile}", "--window-size=1320,900",
                "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
                "--disable-features=Translate,msEdgeSidebarV2",
            ])
            status = edge_proc.wait()
            log(f"Edge app process exited with status {status}")
            return status == 0
    except OSError as error:
        log(f"Could not open Edge app window: {error!r}")
        return False


# --- Option 3: default browser ------------------------------------------------
def open_with_browser(port, proc):
    import webbrowser
    log("Opening default browser")
    if wait_until_ready(port, proc):
        webbrowser.open(f"http://127.0.0.1:{port}")
    proc.wait()


def stop_engine(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main():
    import webbrowser

    # Check readiness in Python so Edge can open the local app directly.
    for attempt in range(1, 3):
        port = free_port()
        log(f"Starting {APP_NAME} on port {port}, attempt {attempt}")
        try:
            proc = start_engine(port)
        except OSError as error:
            log(f"Could not launch engine: {error!r}")
            continue
        try:
            if not wait_until_ready(port, proc):
                log(f"Engine did not become ready on attempt {attempt}; exit status {proc.poll()}")
                continue
            mode = os.environ.get("BANKBRIDGE_WINDOW", "edge").lower()
            if mode == "builtin" and open_with_webview(port, proc) == "ok":
                return
            if open_with_edge(f"http://127.0.0.1:{port}/"):
                return
            if mode != "builtin" and open_with_webview(port, proc) == "ok":
                return
            open_with_browser(port, proc)
            return
        finally:
            stop_engine(proc)
            log("Closed engine")

    import html
    from pathlib import Path

    error_page = Path(DATA_DIR, "startup-error.html")
    error_page.parent.mkdir(parents=True, exist_ok=True)
    error_page.write_text(ERROR_PAGE.format(log=html.escape(LOG_FILE)), encoding="utf-8")
    if not open_with_edge(error_page.as_uri()):
        webbrowser.open(error_page.as_uri())


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None)
    else:
        main()
