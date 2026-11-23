import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsPackageConfigurationTests(unittest.TestCase):
    def test_build_script_and_shortcut_match_pyinstaller_output(self):
        spec = ast.parse((ROOT / "BankBridge.spec").read_text())
        names = {
            node.func.id: next(keyword.value.value for keyword in node.keywords if keyword.arg == "name")
            for node in ast.walk(spec)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"EXE", "COLLECT"}
        }
        script = (ROOT / "2_Build_EXE.bat").read_text()
        self.assertIn(f'set "BB_PACKAGE=dist\\{names["COLLECT"]}"', script)
        self.assertIn(f'set "BB_EXE=%BB_PACKAGE%\\{names["EXE"]}.exe"', script)
        self.assertIn("$s.TargetPath=$target", script)
        self.assertLess(script.index('if not exist "%BB_EXE%"'), script.index(".CreateShortcut("))
        setup = (ROOT / "1_Setup.bat").read_text()
        self.assertEqual(re.findall(r"\w+\.lnk", script), re.findall(r"\w+\.lnk", setup))
        self.assertIn(f'dist\\{names["COLLECT"]}\\{names["EXE"]}.exe', (ROOT / "README.md").read_text())
