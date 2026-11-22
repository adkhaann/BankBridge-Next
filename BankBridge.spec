# PyInstaller recipe for BankBridge.exe  (run 2_Build_EXE.bat)
import os, sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

sys.path.insert(0, os.path.abspath("."))
import build_engine
build_engine.build()          # refresh engine.py from app.py

datas = [
    ("bankbridge_ui.py", "."),
    ("engine.py", "."),
    ("assets", "assets"),
]
binaries, hiddenimports = [], ["engine", "webview.platforms.winforms",
                               "webview.platforms.edgechromium", "clr"]

for pkg in ("streamlit", "pymupdf", "fitz", "webview", "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

datas += copy_metadata("streamlit")

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BankBridgeNext",
    console=False,                       # proper app: no black window
    icon="assets/bankbridge.ico",
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BankBridgeNext")
