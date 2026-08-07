"""End-to-End Simulator Test for TikTok Live Stream System.

Simulates real-time gift events, queue processing, action preloading,
WebSocket overlay state sync, and HTTP API triggers.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import tiktok_backend as backend_mod
import tiktok_obs_controller as core
from tiktok_overlay import LocalOverlayServer


class TestTikTokLiveStreamSimulator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = Path("./tmp_sim_test")
        self.tmp_dir.mkdir(exist_ok=True)
        self.video_dir = self.tmp_dir / "videos"
        self.video_dir.mkdir(exist_ok=True)

        # Create dummy video/sound files
        (self.video_dir / "idle_loop.mp4").write_bytes(b"dummy_idle")
        (self.video_dir / "rose_dance.mp4").write_bytes(b"dummy_rose")
        (self.video_dir / "lion_transform.mp4").write_bytes(b"dummy_lion")

        self.original_app_dir = core.APP_DIRECTORY
        self.original_video_dir = core.VIDEO_DIRECTORY
        core.APP_DIRECTORY = self.tmp_dir
        core.VIDEO_DIRECTORY = self.video_dir

        self.overlay = LocalOverlayServer(host="127.0.0.1", port=0)
        self.app = core.TikTokObsApp(mock_mode=True, enable_tiktok=False, enable_obs=False, overlay=self.overlay)

    async def asyncTearDown(self) -> None:
        core.APP_DIRECTORY = self.original_app_dir
        core.VIDEO_DIRECTORY = self.original_video_dir
        if self.tmp_dir.exists():
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    async def test_full_gift_burst_simulation_flow(self) -> None:
        """Giả lập luồng nhận quà dồn dập, nạp trước (preload) và nối phát liên tục."""
        # Setup gift mapping
        core.GIFT_MAPPING.clear()
        core.GIFT_MAPPING["rose"] = ("rose_dance.mp4", 1, "", "main")
        core.GIFT_MAPPING["lion"] = ("lion_transform.mp4", 5, "", "main")

        app_task = asyncio.create_task(self.app.run())
        await asyncio.sleep(0.05)

        # 1. Giả lập người xem 1 tặng quà Rose
        await self.app.enqueue_gift("rose")
        await asyncio.sleep(0.05)

        # Kiểm tra quà Rose đang phát
        self.assertIsNotNone(self.app.current_job)
        self.assertEqual(self.app.current_job.gift_name, "rose")

        # 2. Trong lúc Rose đang phát, người xem 2 tặng quà Lion -> Lion vào queue
        await self.app.enqueue_gift("lion")
        await asyncio.sleep(0.05)

        self.assertEqual(len(self.app.queue), 1)
        queued_items = self.app.queue.get_items()
        self.assertEqual(queued_items[0].gift_name, "lion")

        # 3. Bấm Skip quà Rose -> Hệ thống lập tức nhảy sang quà Lion
        self.app.skip_current()
        await asyncio.sleep(0.05)

        self.assertIsNotNone(self.app.current_job)
        self.assertEqual(self.app.current_job.gift_name, "lion")

        # 4. Bấm Skip quà Lion -> Kết thúc queue và tự quay về Idle
        self.app.skip_current()
        await asyncio.sleep(0.05)

        self.assertIsNone(self.app.current_job)
        self.assertEqual(len(self.app.queue), 0)

        # Stop app
        self.app._stop_event.set()
        await app_task

    async def test_backend_http_api_simulator_control(self) -> None:
        """Giả lập điều khiển từ giao diện điều khiển Electron thông qua REST API."""
        runtime = backend_mod.BackendRuntime()
        runtime.app = self.app
        runtime.app_task = asyncio.create_task(asyncio.sleep(10))
        
        # Test API trạng thái hệ thống
        status = runtime.status()
        self.assertTrue(status["running"])
        self.assertTrue(status["mock_mode"])

        # Test API thêm quà bằng thủ công (Test Gift Button)
        res = runtime.enqueue_gifts("rose", 2)
        self.assertEqual(res, 2)
        self.assertEqual(len(self.app.queue), 2)

        # Test API xóa hàng chờ (Clear Queue)
        cleared_res = runtime.clear_queue()
        self.assertEqual(cleared_res, 2)
        self.assertEqual(len(self.app.queue), 0)

        runtime.app_task.cancel()


if __name__ == "__main__":
    unittest.main()
