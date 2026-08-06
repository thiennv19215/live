import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tiktok_backend import BackendApiServer, BackendRuntime


class FakeRuntime:
    def __init__(self) -> None:
        self.started = None
        self.saved_items = None
        self.log_handler = SimpleNamespace(snapshot=lambda after: [{"id": after + 1, "message": "ready"}])

    def status(self):
        return {"running": bool(self.started), "overlay_url": "http://127.0.0.1:8765/overlay"}

    def config(self):
        return {"output_ratio": "9:16"}

    def mappings(self):
        return [{"gift": "rose", "action": "action_rose", "action_id": "action_rose", "priority": 1, "sound": ""}]

    def actions(self):
        return [{"id": "action_rose", "name": "Rose action", "videos": ["rose.mp4"], "sound": ""}]

    def start_system(self, payload):
        self.started = payload

    def stop_system(self):
        self.started = None

    def enqueue_gift(self, gift):
        self.gift = gift

    def enqueue_gifts(self, gift, count):
        self.gift = gift
        self.count = count
        return count

    def skip(self):
        self.skipped = True

    def clear_queue(self):
        return 2

    def update_config(self, payload):
        return payload

    def save_mappings(self, items):
        self.saved_items = items
        return items

    def save_actions(self, items):
        self.saved_actions = items
        return items

    def set_idle_video(self, path):
        return path


class TestBackendApi(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.server = BackendApiServer(("127.0.0.1", 0), self.runtime)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get_json(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return json.load(response)

    def post_json(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_status_and_logs(self) -> None:
        self.assertFalse(self.get_json("/api/status")["running"])
        self.assertEqual(self.get_json("/api/logs?after=4")[0]["id"], 5)

    def test_start_and_queue_actions(self) -> None:
        result = self.post_json("/api/system/start", {"mock_mode": True})
        self.assertTrue(result["running"])
        self.post_json("/api/queue/test", {"gift": "rose"})
        self.assertEqual(self.runtime.gift, "rose")
        self.assertEqual(self.post_json("/api/queue/clear", {})["cleared"], 2)

    def test_mapping_save(self) -> None:
        items = [{"gift": "lion", "action": "lion.mp4", "priority": 5}]
        self.assertEqual(self.post_json("/api/mappings", {"items": items}), items)
        self.assertEqual(self.runtime.saved_items, items)

    def test_action_library_read_and_save(self) -> None:
        self.assertEqual(self.get_json("/api/actions")[0]["id"], "action_rose")
        items = [{"id": "action_lion", "name": "Lion", "videos": ["lion.mp4"], "sound": ""}]
        self.assertEqual(self.post_json("/api/actions", {"items": items}), items)
        self.assertEqual(self.runtime.saved_actions, items)

    def test_batch_queue_action_is_clamped(self) -> None:
        result = self.post_json("/api/queue/test-batch", {"gift": "rose", "count": 99})
        self.assertEqual(result["enqueued"], 20)
        self.assertEqual((self.runtime.gift, self.runtime.count), ("rose", 20))

    def test_missing_route_returns_json_404(self) -> None:
        with self.assertRaises(HTTPError) as error:
            self.get_json("/missing")
        self.assertEqual(error.exception.code, 404)

    def test_mapping_save_uses_portable_media_paths(self) -> None:
        from tiktok_backend import core

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos = root / "videos"
            videos.mkdir()
            media = videos / "rose.mp4"
            media.write_bytes(b"video")
            config = root / "gift_config.json"
            with patch.object(core, "VIDEO_DIRECTORY", videos), patch.object(core, "CONFIG_FILE", config):
                core.save_gift_mapping({"rose": (str(media), 1, "", "main")})
            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 2)
            self.assertEqual(saved["mappings"][0]["gift_name"], "rose")
            self.assertEqual(saved["mappings"][0]["action_id"], "rose.mp4")

    def test_legacy_direct_media_mapping_migrates_to_action_preset(self) -> None:
        from tiktok_backend import core

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos = root / "videos"
            videos.mkdir()
            media = videos / "rose.mp4"
            media.write_bytes(b"video")
            runtime = BackendRuntime.__new__(BackendRuntime)
            with (
                patch.object(core, "VIDEO_DIRECTORY", videos),
                patch.object(core, "CONFIG_FILE", root / "gift_config.json"),
                patch.object(core, "ACTION_PRESETS_FILE", root / "action_presets.json"),
                patch.object(core, "ACTION_PRESETS", {}),
                patch.object(core, "GIFT_MAPPING", {}),
            ):
                result = runtime.save_mappings(
                    [{"gift": "rose", "action": str(media), "priority": 1, "sound": ""}]
                )
                self.assertEqual(result[0]["action_id"], "gift_rose")
                self.assertEqual(core.ACTION_PRESETS["gift_rose"].videos, [str(media)])
                saved_actions = json.loads((root / "action_presets.json").read_text(encoding="utf-8"))
                self.assertEqual(saved_actions["actions"]["gift_rose"]["videos"], ["rose.mp4"])
                saved_mapping = json.loads((root / "gift_config.json").read_text(encoding="utf-8"))
                self.assertEqual(saved_mapping["mappings"][0]["action_id"], "gift_rose")


if __name__ == "__main__":
    unittest.main()
