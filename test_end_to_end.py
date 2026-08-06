import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from websocket import WebSocketConnectionClosedException

import tiktok_obs_controller as core


class FakeGift:
    def __init__(self, *, streakable: bool) -> None:
        self.name = "rose"
        self.streakable = streakable


class FakeGiftEvent:
    def __init__(self, *, streakable: bool, streaking: object = None, repeat_end: object = None) -> None:
        self.gift = FakeGift(streakable=streakable)
        self.streaking = streaking
        self.repeat_end = repeat_end


class TestTikTokObsEndToEnd(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._original_character_count = core.CHARACTER_COUNT
        core.set_character_count(4)
        self.app = core.TikTokObsApp(mock_mode=True)

    async def asyncTearDown(self) -> None:
        core.set_character_count(self._original_character_count)

    async def test_fifo_queue_ordering(self) -> None:
        """Kiểm tra quà đến trước được phát trước, không phụ thuộc priority."""
        job_low = core.GiftJob("rose", Path("cho_1_sui.mp4"), priority=1)
        job_med = core.GiftJob("tiktok", Path("3_cho_nhay_tiktok.mp4"), priority=3)
        job_high = core.GiftJob("lion", Path("3_cho_bien_su_tu.mp4"), priority=5)

        queue = core.PriorityGiftQueue()
        await queue.put(job_low)
        await queue.put(job_med)
        await queue.put(job_high)

        self.assertEqual(len(queue), 3)

        # Rose đến trước nên được lấy đầu tiên dù priority thấp nhất.
        first = await queue.get()
        self.assertEqual(first.gift_name, "rose")

        # TikTok đến thứ hai nên được lấy tiếp theo.
        second = await queue.get()
        self.assertEqual(second.gift_name, "tiktok")

        # Lion đến sau cùng nên nằm cuối hàng chờ dù priority cao nhất.
        third = await queue.get()
        self.assertEqual(third.gift_name, "lion")

        self.assertEqual(len(queue), 0)

    async def test_regular_gift_is_not_suppressed_by_false_repeat_default(self) -> None:
        event = FakeGiftEvent(streakable=False, repeat_end=0)
        self.assertTrue(core.should_enqueue_gift_event(event))

    async def test_streak_gift_only_enqueues_after_streak_finishes(self) -> None:
        self.assertFalse(core.should_enqueue_gift_event(FakeGiftEvent(streakable=True, streaking=True)))
        self.assertTrue(core.should_enqueue_gift_event(FakeGiftEvent(streakable=True, streaking=False)))

    async def test_legacy_repeat_end_accepts_integer_flags(self) -> None:
        self.assertFalse(core.should_enqueue_gift_event(FakeGiftEvent(streakable=True, repeat_end=0)))
        self.assertTrue(core.should_enqueue_gift_event(FakeGiftEvent(streakable=True, repeat_end=1)))

    async def test_direct_studio_mode_never_calls_obs_for_action(self) -> None:
        class Overlay:
            def __init__(self) -> None:
                self.states: list[str] = []

            def show_action(self, *_args: object, **_kwargs: object) -> None:
                self.states.append("action")

            def show_idle(self) -> None:
                self.states.append("idle")

        overlay = Overlay()
        app = core.TikTokObsApp(mock_mode=False, enable_obs=False, overlay=overlay)
        job = core.GiftJob("rose", Path("rose.mp4"), priority=1)
        with (
            patch.object(core, "get_video_duration", return_value=0.01),
            patch.object(app.obs, "play_action", new=AsyncMock()) as play,
            patch.object(app.obs, "stop_action", new=AsyncMock()) as stop,
        ):
            await app._play_job(job)

        play.assert_not_awaited()
        stop.assert_not_awaited()
        self.assertEqual(overlay.states, ["action", "idle"])

    async def test_queue_clear(self) -> None:
        """Kiểm tra tính năng xóa queue."""
        job1 = core.GiftJob("rose", Path("cho_1_sui.mp4"), priority=1)
        job2 = core.GiftJob("lion", Path("3_cho_bien_su_tu.mp4"), priority=5)

        queue = core.PriorityGiftQueue()
        await queue.put(job1)
        await queue.put(job2)
        self.assertEqual(len(queue), 2)

        cleared_count = queue.clear()
        self.assertEqual(cleared_count, 2)
        self.assertEqual(len(queue), 0)

    async def test_clear_all_stops_current_action_and_returns_to_idle(self) -> None:
        class Overlay:
            def __init__(self) -> None:
                self.states: list[str] = []

            def show_action(self, *_args: object, **_kwargs: object) -> None:
                self.states.append("action")

            def show_idle(self) -> None:
                self.states.append("idle")

        overlay = Overlay()
        app = core.TikTokObsApp(mock_mode=True, enable_obs=False, overlay=overlay)
        worker = asyncio.create_task(app.worker())
        try:
            with patch.object(core, "get_video_duration", return_value=30.0):
                await app.queue.put(core.GiftJob("rose", Path(__file__), priority=1))
                for _ in range(100):
                    if app.current_job is not None:
                        break
                    await asyncio.sleep(0.01)
                self.assertIsNotNone(app.current_job)
                self.assertEqual(await app.clear_all_playback(), 1)
                self.assertIsNone(app.current_job)
                self.assertEqual(len(app.queue), 0)
                self.assertEqual(overlay.states[-1], "idle")
        finally:
            worker.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await worker

    async def test_gift_mapping_resolution(self) -> None:
        """Kiểm tra tra cứu mapping quà từ dictionary."""
        mapping = core.GIFT_MAPPING.get("rose")
        self.assertIsNotNone(mapping)

        filename, priority, *rest = mapping
        self.assertTrue(len(filename) > 0)
        self.assertEqual(priority, 1)

    async def test_multi_video_random_selection(self) -> None:
        """Kiểm tra tách danh sách nhiều video và bốc ngẫu nhiên khi gán cho quà."""
        multi_str = "dance1.mp4, dance2.mp4, dance3.mp4"
        files = core.parse_video_filenames(multi_str)
        self.assertEqual(files, ["dance1.mp4", "dance2.mp4", "dance3.mp4"])

        picked = core.select_random_video_filename(multi_str)
        self.assertIn(picked, files)

    async def test_action_preset_resolution(self) -> None:
        """Kiểm tra tra cứu quà gán qua Kho Hành Động (Action Presets)."""
        preset_id = "action_dance_rose"
        self.assertIn(preset_id, core.ACTION_PRESETS)

        preset = core.ACTION_PRESETS[preset_id]
        vids, sound, name = core.resolve_gift_action_media(preset_id)
        self.assertEqual(vids, preset.videos)
        self.assertEqual(name, preset.name)

        # Enqueue quà Rose gán với Action Preset
        core.GIFT_MAPPING["rose_action_test"] = (preset_id, 1, "", "char1")
        await self.app.enqueue_gift("rose_action_test")
        self.assertEqual(len(self.app.queue), 1)

        job = await self.app.queue.get()
        self.assertIn(job.file_path.name, [Path(v).name for v in preset.videos])

    async def test_action_preset_preview_uses_shared_action_source(self) -> None:
        preset_id = next(iter(core.ACTION_PRESETS))
        with patch.object(core, "resolve_existing_media_path", return_value=Path(__file__)):
            queued = await self.app.enqueue_action_preset(preset_id, "char3")
        self.assertTrue(queued)
        job = await self.app.queue.get()
        self.assertEqual(job.target_char, "main")

    async def test_sound_file_execution(self) -> None:
        """Kiểm tra GiftJob hỗ trợ đường dẫn sound_path."""
        job = core.GiftJob("rose", Path("cho_1_sui.png"), priority=1, sound_path=Path("cho_sui.mp3"), target_char="char1")
        self.assertEqual(job.sound_path, Path("cho_sui.mp3"))
        self.assertEqual(job.target_char, "char1")

    async def test_missing_real_media_is_not_added_to_queue(self) -> None:
        """Kiểm tra file đã mất không tạo một job giả khiến người dùng tưởng đang phát."""
        app = core.TikTokObsApp(mock_mode=False)
        with patch.dict(core.GIFT_MAPPING, {"missing_test": ("missing-video.mp4", 1, "", "char1")}):
            await app.enqueue_gift("missing_test")
        self.assertEqual(len(app.queue), 0)

    async def test_all_targets_route_to_shared_sources(self) -> None:
        """Mọi quà đều dùng chung một cặp Idle_Source/Action_Source."""
        expected = (core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME)
        for target in ("main", "char1", "char2", "char3", "all"):
            self.assertEqual(self.app.obs._get_sources_for_target(target), expected)

    async def test_legacy_character_target_still_routes_to_shared_sources(self) -> None:
        original_count = core.CHARACTER_COUNT
        try:
            core.set_character_count(6)
            obs = core.ObsController(mock_mode=True)
            self.assertEqual(
                obs._get_sources_for_target("char6"),
                (core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME),
            )
            self.assertIn("char6", core.get_character_ids())
            self.assertEqual(core.CHAR_SHORT_TAGS["char6"], "[NV 6]")
        finally:
            core.set_character_count(original_count)

    async def test_remove_character_layer_removes_idle_and_action_scene_items(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True

        async def refresh() -> dict[str, int]:
            obs.existing_inputs = ["Idle_Source_5", "Action_Source_5"]
            obs._scene_items_cache = {"Idle_Source_5": 51, "Action_Source_5": 52}
            return obs._scene_items_cache

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", new=AsyncMock()) as request,
        ):
            removed = await obs.remove_character_layer(5)

        self.assertEqual(removed, ["Idle_Source_5", "Action_Source_5"])
        removed_ids = [
            call.kwargs["item_id"]
            for call in request.await_args_list
            if call.args and call.args[0] == "remove_scene_item"
        ]
        self.assertEqual(removed_ids, [51, 52])

    async def test_sync_idle_video_only_sends_shared_background(self) -> None:
        original_count = core.CHARACTER_COUNT
        original_paths = dict(core.IDLE_VIDEO_PATHS)
        try:
            core.set_character_count(3)
            core.IDLE_VIDEO_PATHS[1] = Path(__file__)
            obs = core.ObsController(mock_mode=False)
            obs._client = object()
            obs.is_connected = True
            with (
                patch.object(obs, "set_idle_video", new=AsyncMock()) as set_idle,
            ):
                result = await obs.sync_all_idle_videos()

            self.assertEqual(result["synced"], ["main"])
            self.assertEqual(result["skipped"], [])
            self.assertEqual(result["errors"], [])
            set_idle.assert_awaited_once_with(Path(__file__), "main")
        finally:
            core.IDLE_VIDEO_PATHS.clear()
            core.IDLE_VIDEO_PATHS.update(original_paths)
            core.set_character_count(original_count)

    async def test_incomplete_character_pair_falls_back_to_legacy_sources(self) -> None:
        """Kiểm tra thiếu một source trong cặp thì không bật nhầm chế độ layer."""
        obs = core.ObsController(mock_mode=False)
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
            "Idle_Source_1": 3,
        }
        self.assertEqual(
            obs._get_sources_for_target("char1"),
            (core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME),
        )

    async def test_all_target_with_no_complete_pair_uses_legacy_action(self) -> None:
        """A stale Action_Source_All must not receive media when the legacy action is displayed."""
        obs = core.ObsController(mock_mode=False)
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
            "Idle_Source_1": 3,
            "Action_Source_All": 4,
        }
        self.assertEqual(
            obs._get_sources_for_target("all"),
            (core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME),
        )

    async def test_default_source_existing_globally_is_added_to_selected_scene(self) -> None:
        """Source có sẵn trong OBS nhưng thiếu ở scene hiện tại phải được gắn lại."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.existing_inputs = [core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME]
        obs._scene_items_cache = {core.IDLE_SOURCE_NAME: 1}

        async def refresh() -> dict[str, int]:
            return obs._scene_items_cache or {}

        async def request(method_name: str, **kwargs: object) -> None:
            if method_name == "create_scene_item":
                obs._scene_items_cache[core.ACTION_SOURCE_NAME] = 2

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", side_effect=request) as mocked_request,
        ):
            await obs.ensure_default_sources_exist()

        create_call = next(
            call for call in mocked_request.await_args_list
            if call.args and call.args[0] == "create_scene_item"
        )
        self.assertEqual(create_call.kwargs["scene_name"], core.SCENE_NAME)
        self.assertEqual(create_call.kwargs["source_name"], core.ACTION_SOURCE_NAME)
        self.assertFalse(create_call.kwargs["enabled"])

    async def test_idle_video_configuration(self) -> None:
        """Kiểm tra cấu hình Video Chờ (Idle Loop Video)."""
        test_path = Path("custom_idle_video.mp4")
        await self.app.obs.set_idle_video(test_path)
        self.assertTrue(self.app.obs.mock_mode)

    async def test_shared_background_path_can_be_replaced(self) -> None:
        original_path = core.get_idle_video_path("main")
        replacement = Path("replacement-background.mp4")
        try:
            core.set_idle_video_path("main", replacement)
            self.assertEqual(core.get_idle_video_path("main"), replacement)
            self.assertEqual(core.IDLE_VIDEO_PATH, replacement)
        finally:
            core.set_idle_video_path("main", original_path)

    async def test_idle_video_always_targets_shared_source(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True

        async def refresh() -> dict[str, int]:
            obs.existing_inputs = [core.IDLE_SOURCE_NAME]
            obs._scene_items_cache = {core.IDLE_SOURCE_NAME: 1}
            return obs._scene_items_cache

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core, "resolve_existing_media_path", return_value=Path(__file__)),
        ):
            await obs.set_idle_video(Path(__file__), "char2")

        settings_call = next(
            call for call in request.await_args_list
            if call.args and call.args[0] == "set_input_settings"
        )
        self.assertEqual(settings_call.kwargs["name"], core.IDLE_SOURCE_NAME)

    async def test_idle_video_readback_mismatch_is_reported(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True

        class Readback:
            input_settings = {"local_file": "C:/wrong-file.mp4"}

        async def refresh() -> dict[str, int]:
            obs.existing_inputs = [core.IDLE_SOURCE_NAME]
            obs._scene_items_cache = {core.IDLE_SOURCE_NAME: 1}
            return obs._scene_items_cache

        async def request(method_name: str, **kwargs: object) -> object:
            return Readback() if method_name == "get_input_settings" else None

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", side_effect=request),
            patch.object(core, "resolve_existing_media_path", return_value=Path(__file__)),
        ):
            with self.assertRaisesRegex(RuntimeError, "khong xac nhan"):
                await obs.set_idle_video(Path(__file__), "char1")

    async def test_clear_idle_video_clears_obs_input_file(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True

        class Readback:
            input_settings = {"local_file": "", "file": ""}

        async def refresh() -> dict[str, int]:
            obs.existing_inputs = [core.IDLE_SOURCE_NAME]
            obs._scene_items_cache = {core.IDLE_SOURCE_NAME: 1}
            return obs._scene_items_cache

        async def request(method_name: str, **kwargs: object) -> object:
            return Readback() if method_name == "get_input_settings" else None

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", side_effect=request) as mocked_request,
        ):
            await obs.clear_idle_video("char1")

        clear_call = next(
            call for call in mocked_request.await_args_list
            if call.args and call.args[0] == "set_input_settings"
        )
        self.assertEqual(clear_call.kwargs["settings"]["local_file"], "")

    async def test_new_obs_source_refreshes_stale_cache(self) -> None:
        """Kiểm tra source mới thêm vào OBS được tìm thấy sau khi làm mới cache."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs._scene_items_cache = {"Action_Source_1": 10}

        async def refresh_cache() -> dict[str, int]:
            obs._scene_items_cache = {
                "Action_Source_1": 10,
                "Action_Source_2": 20,
            }
            return obs._scene_items_cache

        with patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh_cache) as refresh:
            item_id = await obs._get_scene_item_id("Action_Source_2")

        self.assertEqual(item_id, 20)
        refresh.assert_awaited_once()

    async def test_character_layer_source_setup(self) -> None:
        """Kiểm tra công cụ setup tạo đủ source idle/action cho bốn nhân vật."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True

        with (
            patch.object(obs, "_refresh_scene_items_cache", new=AsyncMock(return_value={})),
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(obs, "reset_obs_display_state", new=AsyncMock()),
        ):
            created = await obs.ensure_character_layer_sources_exist([1, 2, 3, 4])

        self.assertEqual(len(created), 9)
        created_names = {
            call.kwargs["inputName"]
            for call in request.await_args_list
            if call.args and call.args[0] == "create_input"
        }
        self.assertIn("Idle_Source_1", created_names)
        self.assertIn("Action_Source_4", created_names)
        self.assertIn("Action_Source_All", created_names)

    async def test_character_layer_sync_removes_characters_without_video(self) -> None:
        """Full sync only keeps numbered scene items for characters with real media."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._scene_items_cache = {
            "Idle_Source_1": 11,
            "Action_Source_1": 12,
            "Idle_Source_2": 21,
            "Action_Source_2": 22,
            "Action_Source_All": 30,
        }

        async def refresh() -> dict[str, int]:
            return obs._scene_items_cache

        async def request(method_name: str, **kwargs: object) -> None:
            if method_name == "remove_scene_item":
                removed_id = kwargs["item_id"]
                obs._scene_items_cache = {
                    name: item_id
                    for name, item_id in obs._scene_items_cache.items()
                    if item_id != removed_id
                }

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", side_effect=request) as mocked_request,
            patch.object(obs, "reset_obs_display_state", new=AsyncMock()),
        ):
            await obs.ensure_character_layer_sources_exist([1], remove_inactive=True)

        removed_ids = [
            call.kwargs["item_id"]
            for call in mocked_request.await_args_list
            if call.args and call.args[0] == "remove_scene_item"
        ]
        self.assertEqual(removed_ids, [21, 22])
        self.assertIn("Idle_Source_1", obs._scene_items_cache)
        self.assertNotIn("Idle_Source_2", obs._scene_items_cache)

    async def test_obs_socket_disconnect_reconnects_and_retries(self) -> None:
        """Kiểm tra WebSocket đóng giữa chừng sẽ kết nối lại và gửi lại lệnh."""
        obs = core.ObsController(mock_mode=False)

        class ClosedClient:
            def ping(self) -> None:
                raise WebSocketConnectionClosedException("socket closed")

        class ConnectedClient:
            def ping(self) -> str:
                return "ok"

        clients = [ClosedClient(), ConnectedClient()]

        async def connect(reset_display: bool = True) -> None:
            if obs._client is None:
                obs._client = clients.pop(0)
                obs._connection_generation += 1
            obs.is_connected = True

        async def drop_connection() -> None:
            obs.is_connected = False
            obs._client = None
            obs._scene_items_cache = None
            obs.existing_inputs = []

        with (
            patch.object(obs, "connect", side_effect=connect) as reconnect,
            patch.object(obs, "_drop_connection", side_effect=drop_connection) as disconnect,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await obs._request("ping")

        self.assertEqual(result, "ok")
        self.assertEqual(reconnect.await_count, 2)
        disconnect.assert_awaited_once()

    async def test_obs_request_reuses_connected_client_without_deadlock(self) -> None:
        """Kiểm tra setup OBS không gọi connect lần hai khi khóa kết nối đang được giữ."""
        obs = core.ObsController(mock_mode=False)

        class ConnectedClient:
            def ping(self) -> str:
                return "ok"

        obs._client = ConnectedClient()
        obs.is_connected = True

        with patch.object(obs, "connect", new=AsyncMock()) as reconnect:
            result = await obs._request("ping")

        self.assertEqual(result, "ok")
        reconnect.assert_not_awaited()

    async def test_app_shutdown_clears_queue_and_resets_obs(self) -> None:
        """Kiểm tra đóng app sẽ xóa queue và đưa OBS về trạng thái chờ."""
        app = core.TikTokObsApp(mock_mode=True)
        await app.queue.put(core.GiftJob("rose", Path("rose.mp4"), priority=1))

        with (
            patch.object(app, "tiktok_loop", new=AsyncMock(return_value=None)),
            patch.object(app.obs, "reset_obs_display_state", new=AsyncMock()) as reset_display,
        ):
            await app.run()

        self.assertEqual(len(app.queue), 0)
        reset_display.assert_awaited_once()

    async def test_shared_action_temporarily_replaces_background(self) -> None:
        """Kích hoạt action sẽ ẩn nền chung, rồi khôi phục nền khi kết thúc."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs.existing_inputs = [core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME]
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 11,
            core.ACTION_SOURCE_NAME: 12,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
        }
        obs._scene_item_count = 3

        with (
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs._set_action_visible(True, "char1")
            await obs._set_action_visible(False, "char1")

        visibility_calls = [
            (call.kwargs.get("item_id"), call.kwargs.get("enabled"))
            for call in request.await_args_list
            if call.args and call.args[0] == "set_scene_item_enabled"
        ]
        requested_methods = [call.args[0] for call in request.await_args_list if call.args]

        self.assertIn((11, False), visibility_calls)
        self.assertIn((11, True), visibility_calls)
        self.assertIn((12, True), visibility_calls)
        self.assertIn((12, False), visibility_calls)
        action_off_index = visibility_calls.index((12, False))
        idle_return_index = len(visibility_calls) - 1 - visibility_calls[::-1].index((11, True))
        self.assertLess(action_off_index, idle_return_index)
        self.assertIn("set_scene_item_index", requested_methods)
        self.assertNotIn("set_scene_item_transform", requested_methods)
        self.assertNotIn("trigger_studio_mode_transition", requested_methods)

    async def test_action_is_preloaded_behind_idle_before_reveal(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 11,
            core.ACTION_SOURCE_NAME: 12,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
        }
        obs._scene_item_count = 3

        class PlayingStatus:
            media_state = "OBS_MEDIA_STATE_PLAYING"

        async def request(method_name: str, **kwargs: object) -> object:
            return PlayingStatus() if method_name == "get_media_input_status" else None

        with patch.object(obs, "_request", side_effect=request) as mocked_request:
            ready = await obs._preload_action_source()

        self.assertTrue(ready)
        index_call = next(
            call for call in mocked_request.await_args_list
            if call.args and call.args[0] == "set_scene_item_index"
        )
        self.assertEqual(index_call.kwargs["item_index"], 0)
        restart_calls = [
            call for call in mocked_request.await_args_list
            if call.args
            and call.args[0] == "trigger_media_input_action"
            and call.kwargs.get("action") == "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        ]
        self.assertEqual(len(restart_calls), 1)

    async def test_revealing_preloaded_action_does_not_restart_decoder(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 11,
            core.ACTION_SOURCE_NAME: 12,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 0,
        }
        obs._scene_item_count = 2

        with patch.object(obs, "_request", new=AsyncMock()) as request:
            await obs._set_action_visible(True, "main", restart_media=False)

        restart_calls = [
            call for call in request.await_args_list
            if call.args
            and call.args[0] == "trigger_media_input_action"
            and call.kwargs.get("action") == "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        ]
        self.assertEqual(restart_calls, [])

    @unittest.skip("Chế độ layer nhiều nhân vật đã được thay bằng một video nền chung")
    async def test_reset_uses_numbered_videos_without_legacy_overlay(self) -> None:
        """Layered mode disables the shared idle source so Video 1 stays visible."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
            "Idle_Source_1": 11,
            "Action_Source_1": 12,
            "Idle_Source_2": 21,
            "Action_Source_2": 22,
        }

        async def refresh() -> dict[str, int]:
            return obs._scene_items_cache or {}

        with (
            patch.object(obs, "_refresh_scene_items_cache", side_effect=refresh),
            patch.object(obs, "_request", new=AsyncMock()) as request,
        ):
            await obs.reset_obs_display_state()

        visibility_calls = [
            (call.kwargs.get("item_id"), call.kwargs.get("enabled"))
            for call in request.await_args_list
            if call.args and call.args[0] == "set_scene_item_enabled"
        ]
        self.assertIn((1, False), visibility_calls)
        self.assertIn((11, True), visibility_calls)
        self.assertIn((21, True), visibility_calls)

    @unittest.skip("Chế độ layer nhiều nhân vật đã được thay bằng một video nền chung")
    async def test_starting_numbered_video_disables_stale_legacy_idle(self) -> None:
        """A Video 1 donation cannot be covered by the old shared source."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs.existing_inputs = [
            core.IDLE_SOURCE_NAME,
            core.ACTION_SOURCE_NAME,
            "Idle_Source_1",
            "Action_Source_1",
        ]
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
            "Idle_Source_1": 11,
            "Action_Source_1": 12,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 0,
            "Idle_Source_1": 1,
            "Action_Source_1": 2,
        }
        obs._scene_item_count = 3

        with (
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs._set_action_visible(True, "char1")

        visibility_calls = [
            (call.kwargs.get("item_id"), call.kwargs.get("enabled"))
            for call in request.await_args_list
            if call.args and call.args[0] == "set_scene_item_enabled"
        ]
        self.assertIn((1, False), visibility_calls)
        self.assertIn((11, False), visibility_calls)
        self.assertIn((12, True), visibility_calls)
        restart_calls = [
            call
            for call in request.await_args_list
            if call.args
            and call.args[0] == "trigger_media_input_action"
            and call.kwargs.get("name") == "Action_Source_1"
            and call.kwargs.get("action") == "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        ]
        self.assertEqual(len(restart_calls), 1)

    @unittest.skip("Chế độ layer nhiều nhân vật đã được thay bằng một video nền chung")
    async def test_legacy_fallback_restores_numbered_layers_without_shared_idle(self) -> None:
        """An incomplete target can use the shared action without corrupting layered idle state."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs.existing_inputs = [
            core.IDLE_SOURCE_NAME,
            core.ACTION_SOURCE_NAME,
            "Idle_Source_1",
            "Action_Source_1",
            "Idle_Source_2",
        ]
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            core.ACTION_SOURCE_NAME: 2,
            "Idle_Source_1": 11,
            "Action_Source_1": 12,
            "Idle_Source_2": 21,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 0,
            "Idle_Source_1": 1,
            "Action_Source_1": 2,
            "Idle_Source_2": 3,
            core.ACTION_SOURCE_NAME: 4,
        }
        obs._scene_item_count = 5

        with (
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs._set_action_visible(True, "char2")
            await obs._set_action_visible(False, "char2")

        visibility_calls = [
            (call.kwargs.get("item_id"), call.kwargs.get("enabled"))
            for call in request.await_args_list
            if call.args and call.args[0] == "set_scene_item_enabled"
        ]
        self.assertIn((1, False), visibility_calls)
        self.assertNotIn((1, True), visibility_calls)
        self.assertIn((11, False), visibility_calls)
        self.assertIn((11, True), visibility_calls)
        self.assertNotIn((21, True), visibility_calls)

    @unittest.skip("Chế độ layer nhiều nhân vật đã được thay bằng một video nền chung")
    async def test_all_target_ignores_incomplete_numbered_idle_sources(self) -> None:
        """The all action only hides and restores complete character layers."""
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._scene_items_cache = {
            core.IDLE_SOURCE_NAME: 1,
            "Idle_Source_1": 11,
            "Action_Source_1": 12,
            "Idle_Source_2": 21,
            "Action_Source_All": 30,
        }
        obs._scene_item_indices = {
            core.IDLE_SOURCE_NAME: 0,
            "Idle_Source_1": 1,
            "Action_Source_1": 2,
            "Idle_Source_2": 3,
            "Action_Source_All": 4,
        }
        obs._scene_item_count = 5

        with (
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs._set_action_visible(True, "all")
            await obs._set_action_visible(False, "all")

        visibility_calls = [
            (call.kwargs.get("item_id"), call.kwargs.get("enabled"))
            for call in request.await_args_list
            if call.args and call.args[0] == "set_scene_item_enabled"
        ]
        self.assertIn((11, False), visibility_calls)
        self.assertIn((11, True), visibility_calls)
        self.assertNotIn((21, False), visibility_calls)
        self.assertNotIn((21, True), visibility_calls)

    async def test_missing_obs_source_fails_instead_of_using_first_input(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs.existing_inputs = ["Camera", "Microphone"]

        with self.assertRaisesRegex(RuntimeError, "tranh ghi nham source"):
            obs._resolve_real_source_name("Action_Source_1", core.ACTION_SOURCE_NAME)

    async def test_connect_only_reports_ready_after_source_validation(self) -> None:
        obs = core.ObsController(mock_mode=False)

        class SceneResponse:
            scenes = [{"sceneName": core.SCENE_NAME}]

        class Client:
            def get_scene_list(self) -> SceneResponse:
                return SceneResponse()

            def disconnect(self) -> None:
                return None

        with (
            patch.object(core, "ReqClient", return_value=Client()),
            patch.object(obs, "ensure_default_sources_exist", new=AsyncMock()),
            patch.object(obs, "_validate_obs_setup", new=AsyncMock(side_effect=RuntimeError("missing source"))),
        ):
            with self.assertRaises(ConnectionError):
                await obs.connect()

        self.assertFalse(obs.is_connected)
        self.assertIsNone(obs._client)

    async def test_connect_reset_request_can_reconnect_without_lock_deadlock(self) -> None:
        obs = core.ObsController(mock_mode=False)

        class SceneResponse:
            scenes = [{"sceneName": core.SCENE_NAME}]

        class FirstClient:
            def get_scene_list(self) -> SceneResponse:
                return SceneResponse()

            def ping(self) -> None:
                raise WebSocketConnectionClosedException("socket closed during reset")

            def disconnect(self) -> None:
                return None

        class SecondClient(FirstClient):
            def ping(self) -> str:
                return "ok"

        async def reset_display() -> None:
            self.assertEqual(await obs._request("ping"), "ok")

        with (
            patch.object(core, "ReqClient", side_effect=[FirstClient(), SecondClient()]),
            patch.object(obs, "ensure_default_sources_exist", new=AsyncMock()),
            patch.object(obs, "_validate_obs_setup", new=AsyncMock()),
            patch.object(obs, "reset_obs_display_state", side_effect=reset_display),
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await asyncio.wait_for(obs.connect(), timeout=0.5)

        self.assertTrue(obs.is_connected)
        self.assertIsInstance(obs._client, SecondClient)

    async def test_connect_validation_socket_failure_does_not_reenter_connect_lock(self) -> None:
        obs = core.ObsController(mock_mode=False)

        class SceneResponse:
            scenes = [{"sceneName": core.SCENE_NAME}]

        class Client:
            def get_scene_list(self) -> SceneResponse:
                return SceneResponse()

            def ping(self) -> None:
                raise WebSocketConnectionClosedException("socket closed during validation")

            def disconnect(self) -> None:
                return None

        async def validate() -> None:
            await obs._request("ping")

        with (
            patch.object(core, "ReqClient", return_value=Client()),
            patch.object(obs, "ensure_default_sources_exist", new=AsyncMock()),
            patch.object(obs, "_validate_obs_setup", side_effect=validate),
        ):
            with self.assertRaises(ConnectionError):
                await asyncio.wait_for(obs.connect(), timeout=0.5)

        self.assertFalse(obs.is_connected)
        self.assertIsNone(obs._client)

    async def test_display_transition_replays_after_mid_sequence_reconnect(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs._connection_generation = 1
        obs.existing_inputs = [core.IDLE_SOURCE_NAME, core.ACTION_SOURCE_NAME]
        obs._scene_items_cache = {core.IDLE_SOURCE_NAME: 1, core.ACTION_SOURCE_NAME: 2}
        obs._scene_item_count = 2
        obs._scene_item_indices = {core.IDLE_SOURCE_NAME: 0, core.ACTION_SOURCE_NAME: 1}
        calls: list[tuple[int | None, bool | None]] = []
        physical_state = {1: True, 2: False}
        failed_once = False

        async def request(method_name: str, **kwargs: object) -> None:
            nonlocal failed_once
            if method_name == "set_scene_item_enabled":
                calls.append((kwargs.get("item_id"), kwargs.get("enabled")))
                item_id = int(kwargs["item_id"])
                physical_state[item_id] = bool(kwargs["enabled"])
                if kwargs.get("item_id") == 1 and not failed_once:
                    failed_once = True
                    # Simulate OBS reconnect restoring its startup state.
                    physical_state.update({1: True, 2: False})
                    obs._connection_generation += 1

        with (
            patch.object(obs, "_request", side_effect=request),
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs._set_action_visible(True, "char1")

        self.assertGreaterEqual(calls.count((2, True)), 2)
        self.assertGreaterEqual(calls.count((1, False)), 2)
        self.assertEqual(physical_state, {1: False, 2: True})

    async def test_wait_for_action_end_ignores_stale_stopped_until_playback_started(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs.existing_inputs = [core.ACTION_SOURCE_NAME]
        obs._scene_items_cache = {}
        states = iter([
            "OBS_MEDIA_STATE_STOPPED",
            "OBS_MEDIA_STATE_OPENING",
            "OBS_MEDIA_STATE_PLAYING",
            "OBS_MEDIA_STATE_ENDED",
        ])

        class Status:
            def __init__(self, media_state: str) -> None:
                self.media_state = media_state

        async def request(method_name: str, **kwargs: object) -> Status:
            self.assertEqual(method_name, "get_media_input_status")
            self.assertEqual(kwargs["name"], core.ACTION_SOURCE_NAME)
            return Status(next(states))

        with (
            patch.object(obs, "_request", side_effect=request) as status_request,
            patch.object(core.asyncio, "sleep", new=AsyncMock()),
        ):
            await obs.wait_for_action_end("char1", 30.0)

        self.assertEqual(status_request.await_count, 4)

    async def test_looping_image_keeps_original_duration_fallback(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs.existing_inputs = [core.ACTION_SOURCE_NAME]
        obs._looping_action_sources.add(core.ACTION_SOURCE_NAME)

        with patch.object(core.asyncio, "sleep", new=AsyncMock()) as sleep:
            await obs.wait_for_action_end("char1", 3.0)

        sleep.assert_awaited_once_with(3.0)

    async def test_play_action_never_writes_to_unrelated_obs_input(self) -> None:
        obs = core.ObsController(mock_mode=False)
        obs._client = object()
        obs.is_connected = True
        obs.existing_inputs = ["Camera", "Microphone"]
        obs._scene_items_cache = {}

        with (
            patch.object(obs, "_refresh_scene_items_cache", new=AsyncMock(return_value={})),
            patch.object(obs, "_request", new=AsyncMock()) as request,
            patch.object(core, "resolve_existing_media_path", return_value=Path(__file__)),
        ):
            with self.assertRaises(RuntimeError):
                await obs.play_action(Path(__file__), target_char="char1")

        request.assert_not_awaited()

    async def test_e2e_mock_app_execution(self) -> None:
        """Kiểm tra chạy toàn bộ app ở Mock Mode với luồng phát quà."""
        run_task = asyncio.create_task(self.app.run())
        await asyncio.sleep(0.1)

        self.assertTrue(self.app.obs.is_connected)
        self.assertTrue(self.app.is_tiktok_connected)

        # Enqueue quà Rose
        await self.app.enqueue_gift("rose")
        await asyncio.sleep(0.1)

        self.assertIsNotNone(self.app.current_job)
        self.assertEqual(self.app.current_job.gift_name, "rose")

        # Bấm Skip để kết thúc video Rose
        self.app.skip_current()
        await asyncio.sleep(0.1)
        self.assertIsNone(self.app.current_job)

        # Stop app
        self.app._stop_event.set()
        await run_task

    async def test_manual_skip_and_queue_flow(self) -> None:
        """Kiểm tra quà mới vào queue mượt mà và nút Skip ngắt thủ công."""
        run_task = asyncio.create_task(self.app.run())
        await asyncio.sleep(0.1)

        # Enqueue Rose
        await self.app.enqueue_gift("rose")
        await asyncio.sleep(0.1)

        self.assertIsNotNone(self.app.current_job)
        self.assertEqual(self.app.current_job.gift_name, "rose")

        # Enqueue Lion trong khi Rose đang phát -> Lion vào Queue
        await self.app.enqueue_gift("lion")
        await asyncio.sleep(0.1)

        self.assertEqual(self.app.current_job.gift_name, "rose")
        self.assertEqual(len(self.app.queue), 1)

        # Bấm Skip thủ công -> Rose dừng và Lion từ queue phát tiếp
        self.app.skip_current()
        await asyncio.sleep(0.1)

        self.assertIsNotNone(self.app.current_job)
        self.assertEqual(self.app.current_job.gift_name, "lion")

        # Dừng app
        self.app._stop_event.set()
        await run_task


if __name__ == "__main__":
    unittest.main()
