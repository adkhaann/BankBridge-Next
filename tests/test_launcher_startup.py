from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import run_app


class LauncherStartupTests(unittest.TestCase):
    def test_launcher_retries_once_and_opens_edge_at_ready_url(self):
        first = Mock()
        first.poll.return_value = None
        second = Mock()
        second.poll.return_value = None
        with (
            patch.dict(run_app.os.environ, {"BANKBRIDGE_WINDOW": "edge"}),
            patch.object(run_app, "free_port", side_effect=[12345, 12346]),
            patch.object(run_app, "start_engine", side_effect=[first, second]),
            patch.object(run_app, "wait_until_ready", side_effect=[False, True]) as ready,
            patch.object(run_app, "open_with_edge", return_value=True) as edge,
            patch.object(run_app, "log"),
        ):
            run_app.main()

        self.assertEqual(ready.call_count, 2)
        edge.assert_called_once_with("http://127.0.0.1:12346/")
        first.terminate.assert_called_once()
        second.terminate.assert_called_once()

    def test_edge_uses_a_fresh_profile_for_each_window_and_cleans_it_up(self):
        profiles = []

        def launch(command):
            profile = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--user-data-dir=")))
            profiles.append(profile)
            self.assertIn("--disable-background-mode", command)
            self.assertTrue((profile / "Default" / "Preferences").is_file())
            process = Mock()
            process.wait.return_value = 0
            return process

        with (
            TemporaryDirectory() as directory,
            patch.object(run_app, "DATA_DIR", directory),
            patch.object(run_app, "find_edge", return_value="msedge.exe"),
            patch.object(run_app.subprocess, "Popen", side_effect=launch),
            patch.object(run_app, "log"),
        ):
            for _ in range(2):
                self.assertTrue(run_app.open_with_edge("http://127.0.0.1:12345/"))
                self.assertFalse(profiles[-1].exists())

        self.assertNotEqual(*profiles)
