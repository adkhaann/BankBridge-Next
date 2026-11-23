from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import build_engine


class GeneratedEngineTests(unittest.TestCase):
    def test_checked_in_engine_matches_source(self):
        with TemporaryDirectory() as directory:
            generated = Path(directory) / "engine.py"
            build_engine.build(target=generated)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                Path(build_engine.TARGET).read_text(encoding="utf-8"),
            )
