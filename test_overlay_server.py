import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.request import Request, urlopen
from websocket import create_connection

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
        self.assertRegex(idle_state["media_url"], r"^/media/[0-9a-f]{20}\.mp4$")
        self.assertIsInstance(idle_state["started_at_ms"], int)

        self.server.show_action(self.action_path, self.sound_path, label="rose")
        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            action_state = json.load(response)
        self.assertEqual(action_state["mode"], "action")
        self.assertEqual(action_state["label"], "rose")
        self.assertRegex(action_state["sound_url"], r"^/audio/[0-9a-f]{20}\.mp3$")
        self.assertGreaterEqual(action_state["started_at_ms"], idle_state["started_at_ms"])

        self.server.show_idle()
        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            returned_idle_state = json.load(response)
        self.assertEqual(returned_idle_state["mode"], "idle")
        self.assertEqual(returned_idle_state["started_at_ms"], idle_state["started_at_ms"])

    def test_overlay_uses_websocket_instead_of_periodic_state_poll(self) -> None:
        with urlopen(self.server.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        self.assertIn(f":{self.server.ws_port}`", html)
        self.assertNotIn("setInterval(refresh", html)
        self.assertNotIn("syncToSharedClock(activeMedia, state)", html)

    def test_action_to_idle_transition_never_fades_a_black_terminal_frame(self) -> None:
        with urlopen(self.server.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        self.assertIn("function hideActionImmediately(element)", html)
        self.assertIn("if (returningToIdle) hideActionImmediately(previous);", html)
        self.assertIn("hideActionImmediately(next);", html)

    def test_websocket_pushes_snapshot_and_action_state(self) -> None:
        socket = create_connection(f"ws://{self.server.host}:{self.server.ws_port}", timeout=2)
        try:
            snapshot = json.loads(socket.recv())
            self.assertEqual(snapshot["type"], "playback_state")
            self.assertEqual(snapshot["state"]["mode"], "idle")

            self.server.show_action(self.action_path, label="rose")
            pushed = json.loads(socket.recv())
            self.assertEqual(pushed["state"]["mode"], "action")
            self.assertEqual(pushed["state"]["label"], "rose")
        finally:
            socket.close()

    def test_supports_http_range_requests_for_video(self) -> None:
        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            media_url = json.load(response)["media_url"]
        request = Request(
            f"http://{self.server.host}:{self.server.port}{media_url}",
            headers={"Range": "bytes=2-5"},
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes 2-5/{self.idle_path.stat().st_size}")
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
            self.assertEqual(response.read(), b"le-v")

    def test_supports_suffix_range_used_for_mp4_metadata(self) -> None:
        with urlopen(f"http://{self.server.host}:{self.server.port}/api/state", timeout=2) as response:
            media_url = json.load(response)["media_url"]
        request = Request(
            f"http://{self.server.host}:{self.server.port}{media_url}",
            headers={"Range": "bytes=-4"},
        )
        with urlopen(request, timeout=2) as response:
            size = self.idle_path.stat().st_size
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes {size - 4}-{size - 1}/{size}")
            self.assertEqual(response.read(), b"data")

    def test_media_url_is_stable_until_file_changes(self) -> None:
        first, _, _ = self.server.state.snapshot()
        second, _, _ = self.server.state.snapshot()
        self.assertEqual(first["media_url"], second["media_url"])

        self.idle_path.write_bytes(b"updated-idle-video-data")
        changed, _, _ = self.server.state.snapshot()
        self.assertNotEqual(first["media_url"], changed["media_url"])

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
