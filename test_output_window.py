import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tiktok_output_window import ElectronOutputWindow, get_output_dimensions


class TestElectronOutputWindow(unittest.TestCase):
    def test_output_presets(self) -> None:
        self.assertEqual(get_output_dimensions("9:16"), (1080, 1920))
        self.assertEqual(get_output_dimensions("4:5"), (1080, 1350))
        self.assertEqual(get_output_dimensions("invalid"), (1080, 1920))

    def test_launches_packaged_executable_with_selected_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            executable = app_dir / "TikTokLiveOutput.exe"
            executable.touch()
            fake_process = Mock()
            fake_process.poll.return_value = None
            manager = ElectronOutputWindow(app_dir)
            with patch("tiktok_output_window.subprocess.Popen", return_value=fake_process) as popen:
                manager.start("http://127.0.0.1:8765/overlay", "1:1")

            command = popen.call_args.args[0]
            self.assertEqual(command[0], str(executable))
            self.assertIn("1:1", command)
            self.assertIn("1080", command)
            self.assertIn("--control-port", command)

    def test_rejects_non_local_overlay(self) -> None:
        manager = ElectronOutputWindow()
        with self.assertRaises(ValueError):
            manager.start("https://example.com/overlay", "9:16")


if __name__ == "__main__":
    unittest.main()
