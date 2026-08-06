import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.request import Request, urlopen

import tiktok_obs_controller as core
from tiktok_overlay import LocalOverlayServer


class TestLocalOverlayServer(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.idle_path = root / "idle.mp4"
        self.action_path = root / "action.mp4"
        self.sound_path = root / "sound.mp3"
        self.idle_path.write_bytes(b"idle-video-data")
        self.action_path.write_bytes(b"action-video-data")
        self.sound_path.write_bytes(b"sound-data")
        self.server = LocalOverlayServer(self.idle_path, port=0)
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self.temp_dir.cleanup()

    def test_serves_overlay_and_switches_media_state(self) -> None:
        with urlopen(self.server.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        self.assertIn("TikTok Live Overlay", html)
        self.assertIn("object-fit: var(--media-fit, cover)", html)

        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            idle_state = json.load(response)
        self.assertEqual(idle_state["mode"], "idle")
        self.assertEqual(idle_state["media_url"], "/media/current")
        self.assertIsInstance(idle_state["started_at_ms"], int)

        self.server.show_action(self.action_path, self.sound_path, label="rose")
        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            action_state = json.load(response)
        self.assertEqual(action_state["mode"], "action")
        self.assertEqual(action_state["label"], "rose")
        self.assertEqual(action_state["sound_url"], "/audio/current")
        self.assertGreaterEqual(action_state["started_at_ms"], idle_state["started_at_ms"])

    def test_supports_http_range_requests_for_video(self) -> None:
        request = Request(
            f"http://{self.server.host}:{self.server.port}/media/current",
            headers={"Range": "bytes=2-5"},
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes 2-5/{self.idle_path.stat().st_size}")
            self.assertEqual(response.read(), b"le-v")

    def test_supports_suffix_range_used_for_mp4_metadata(self) -> None:
        request = Request(
            f"http://{self.server.host}:{self.server.port}/media/current",
            headers={"Range": "bytes=-4"},
        )
        with urlopen(request, timeout=2) as response:
            size = self.idle_path.stat().st_size
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes {size - 4}-{size - 1}/{size}")
            self.assertEqual(response.read(), b"data")

    def test_second_instance_uses_a_different_port(self) -> None:
        second = LocalOverlayServer(self.idle_path, port=self.server.port)
        try:
            second.start()
            self.assertNotEqual(second.port, self.server.port)
        finally:
            second.stop()


class TestOverlayPlaybackIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_overlay_continues_when_obs_is_unavailable(self) -> None:
        overlay = SimpleNamespace(
            show_action=Mock(),
            show_idle=Mock(),
        )
        app = core.TikTokObsApp(mock_mode=False, overlay=overlay)
        app.obs = SimpleNamespace(
            play_action=AsyncMock(side_effect=RuntimeError("OBS offline")),
            wait_for_action_end=AsyncMock(),
            stop_action=AsyncMock(),
            update_queue_text=AsyncMock(),
        )
        job = core.GiftJob("rose", Path(__file__), priority=1)

        with patch.object(core, "get_video_duration", return_value=0.001):
            await app._play_job(job)

        overlay.show_action.assert_called_once_with(job.file_path, sound_path=None, label="rose")
        overlay.show_idle.assert_called_once_with()
        app.obs.wait_for_action_end.assert_not_awaited()
        # Do not reconnect just to stop a source that never started. This keeps
        # direct TikTok Studio playback gapless when OBS is offline.
        app.obs.stop_action.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
