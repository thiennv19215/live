import asyncio
import unittest
from pathlib import Path

import tiktok_obs_controller as core


class TestTikTokObsEndToEnd(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.app = core.TikTokObsApp(mock_mode=True)

    async def test_priority_queue_ordering(self) -> None:
        """Kiểm tra hàng đợi ưu tiên các quà có priority cao hơn được lấy ra trước."""
        job_low = core.GiftJob("rose", Path("cho_1_sui.mp4"), priority=1)
        job_med = core.GiftJob("tiktok", Path("3_cho_nhay_tiktok.mp4"), priority=3)
        job_high = core.GiftJob("lion", Path("3_cho_bien_su_tu.mp4"), priority=5)

        queue = core.PriorityGiftQueue()
        await queue.put(job_low)
        await queue.put(job_med)
        await queue.put(job_high)

        self.assertEqual(len(queue), 3)

        # Priority 5 (Lion) phải được lấy đầu tiên
        first = await queue.get()
        self.assertEqual(first.gift_name, "lion")

        # Priority 3 (TikTok) lấy tiếp theo
        second = await queue.get()
        self.assertEqual(second.gift_name, "tiktok")

        # Priority 1 (Rose) lấy cuối cùng
        third = await queue.get()
        self.assertEqual(third.gift_name, "rose")

        self.assertEqual(len(queue), 0)

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

    async def test_gift_mapping_resolution(self) -> None:
        """Kiểm tra tra cứu mapping quà từ dictionary."""
        mapping = core.GIFT_MAPPING.get("rose")
        self.assertIsNotNone(mapping)

        filename, priority = mapping
        self.assertTrue(filename.startswith("cho_1_sui"))
        self.assertEqual(priority, 1)

    async def test_idle_video_configuration(self) -> None:
        """Kiểm tra cấu hình Video Chờ (Idle Loop Video)."""
        test_path = Path("custom_idle_video.mp4")
        await self.app.obs.set_idle_video(test_path)
        self.assertTrue(self.app.obs.mock_mode)

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
