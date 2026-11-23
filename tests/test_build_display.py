from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class BuildDisplayTests(unittest.TestCase):
    def test_desktop_displays_only_a_valid_package_marker(self):
        app = Path(__file__).resolve().parents[1] / "bankbridge_ui.py"
        original_read = Path.read_text
        for marker, expected in (("abcdef0" + "1" * 33, "Build abcdef0"), ("<invalid>", None)):
            with self.subTest(marker=marker):
                def read(path, *args, **kwargs):
                    if path.name == "BankBridgeNext.build":
                        return marker
                    return original_read(path, *args, **kwargs)

                with patch.object(Path, "read_text", read):
                    ui = AppTest.from_file(str(app)).run()
                self.assertFalse(ui.exception)
                header = next(item.value for item in ui.markdown if 'class="bb-appbar"' in item.value)
                if expected:
                    self.assertIn(expected, header)
                else:
                    self.assertNotIn(" · Build ", header)
                    self.assertNotIn(marker, header)
